# HALPIS Intercom Beltpack for Raspberry Pi
# Copyright (c) 2024, Niclas Hallgren
# All rights reserved.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from flask import Flask, render_template
from flask_socketio import SocketIO
import paho.mqtt.client as mqtt
import ssl
import re
import threading
import json
import os
import copy

"""
HALPIS INTCM Web Server

Flask app with MQTT + Socket.IO for monitoring and configuring devices.
Ensure 'ca.crt' and 'roles.json' exist in the working directory.

To test locally (after stopping the systemd service):
    ../.intcm-venv/bin/gunicorn --worker-class eventlet -w 1 \
        --bind 0.0.0.0:5000 --log-level warning main:app
"""

# ====== Configuration ======
# Configuration for MQTT broker, TLS, and topic structure.
ROLES_FILE = "roles.json"
BROKER = "127.0.0.1"  # MQTT broker address
PORT = 8883  # MQTT TLS port
USERNAME = "intercom"
PASSWORD = "Intercom16"
MQTT_PREFIX = 'halpis_intcm/'
TOPIC = f"{MQTT_PREFIX}status/#"
TOPIC_TALK = f"{MQTT_PREFIX}broadcast/+/talk"
TLS_CERT_PATH = "ca.crt"  # Path to CA cert for secure MQTT

# ====== Make sure TLS certificate exists ======
if not os.path.exists(TLS_CERT_PATH):
    raise FileNotFoundError(
        f"\n[ERROR] Required file '{TLS_CERT_PATH}' is missing.\n"
        "Please make sure it exists before starting the server.\n"
    )

# ====== Make sure roles.json exists ======
if not os.path.exists(ROLES_FILE):
    raise FileNotFoundError(
        f"\n[ERROR] Required file '{ROLES_FILE}' is missing.\n"
        "Please make sure it exists before starting the server.\n"
    )

with open(ROLES_FILE, "r") as f:
    roles = json.load(f)

# ====== Flask + Socket.IO Setup ======
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ====== Global Device Storage ======
devices = {}
last_device_states = {}

# ====== Utility Functions ======
def natural_sort_key(s: str) -> list:
    """
    Generate a natural sort key for strings with numeric parts.

    Args:
        s (str): Input string.

    Returns:
        list: Components for natural sorting (ints and lowercase strings).
    """
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', s)]

# ====== MQTT Handlers ======
def on_connect(client, userdata, flags, reason_code, properties):
    """
    Handle MQTT connection event.

    Subscribes to device status and talk broadcast topics.

    Args:
        client: MQTT client instance.
        userdata: User-defined data.
        flags: Connection flags.
        reason_code: Return code for connection result.
        properties: MQTT properties (v5).
    """
    if reason_code == 0:
        client.subscribe(TOPIC)
        client.subscribe(TOPIC_TALK)
    else:
        print(f"Failed to connect to MQTT broker, return code {reason_code}")


def emit_if_device_changed(device_id):
    """
    Emit a device update event if its state has changed.

    Args:
        device_id (str): Unique identifier for the device.
    """
    new_state = devices[device_id]
    old_state = last_device_states.get(device_id)

    if old_state != new_state:
        last_device_states[device_id] = copy.deepcopy(new_state)
        socketio.start_background_task(
            lambda: socketio.emit("update", {device_id: new_state})
        )


def on_message(client, userdata, msg):
    """
    Handle incoming MQTT messages.

    Updates device states or emits talk messages based on topic.

    Args:
        client: MQTT client instance.
        userdata: User-defined data.
        msg: MQTT message instance.
    """
    if not msg.topic.startswith(MQTT_PREFIX):
        return  # Ignore unrelated topics

    # Remove prefix, then split
    topic_suffix = msg.topic[len(MQTT_PREFIX):]
    topic_parts = topic_suffix.split("/")
    if not topic_parts:
        return

    value = msg.payload.decode("utf-8")

    # Handle talk broadcast messages
    if (
        topic_parts[0] == "broadcast"
        and len(topic_parts) >= 3
        and topic_parts[2] == "talk"
    ):
        device_role = topic_parts[1]
        for device_id, data in devices.items():
            if data.get("device_role", "").lower() == device_role.lower():
                devices[device_id]["talk"] = value
                emit_if_device_changed(device_id)
        return

    # Handle standard device status messages
    if topic_parts[0] == "status" and len(topic_parts) >= 2:
        device_id = topic_parts[1]
        key = "/".join(topic_parts[2:])

    if device_id not in devices:
        devices[device_id] = {}

    if key.startswith("channel/"):
        channel_number = key.split("/")[1]
        devices[device_id].setdefault("channels", {})
        devices[device_id]["channels"][channel_number] = value
    else:
        devices[device_id][key] = value

    if "state" not in devices[device_id]:
        devices[device_id]["state"] = "unknown"

    emit_if_device_changed(device_id)


# ====== MQTT Client Setup ======
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.username_pw_set(USERNAME, PASSWORD)
mqtt_client.tls_set(ca_certs=TLS_CERT_PATH, cert_reqs=ssl.CERT_REQUIRED)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

# Start MQTT client loop in a separate thread


def mqtt_loop():
    """
    Start and run the MQTT client loop in a background thread.
    """
    mqtt_client.connect(BROKER, PORT, 60)
    mqtt_client.loop_forever()


mqtt_thread = threading.Thread(target=mqtt_loop, daemon=True)
mqtt_thread.start()

# ====== Flask Web Routes ======
@app.route('/')
def index() -> str:
    """
    Serve the main web interface.

    Returns:
        str: Rendered HTML page.
    """
    return render_template('index.html')

# ====== Socket.IO Events ======
@socketio.on('connect')
def handle_connect():
    """
    Handle new client WebSocket connection.

    Sends current device states and role definitions.
    """
    socketio.emit("update", dict(
        sorted(devices.items(), key=lambda x: natural_sort_key(x[0]))
    ))
    socketio.emit("roles", roles)


@socketio.on('set_mic_level')
def handle_set_mic_level(data):
    """
    Handle mic level adjustment from client.

    Args:
        data (dict): Contains 'device' and 'level' keys.
    """
    device = data.get('device')
    level = data.get('level')

    if not device or level is None:
        return

    topic = f"{MQTT_PREFIX}setup/{device}/mic_level"
    mqtt_client.publish(topic, str(level), retain=True)


@socketio.on("save_device_config")
def handle_device_config(data):
    """
    Handle saving device role and channel configuration.

    Args:
        data (dict): Should include 'device', 'role', and 'channels'.
    """
    device = data.get("device")
    role = data.get("role")
    channels = data.get("channels")

    if not device or not role or channels is None:
        return

    mqtt_client.publish(
        f"{MQTT_PREFIX}setup/{device}/device_role",
        role,
        retain=True
    )

    for channel, roles in channels.items():
        topic = f"{MQTT_PREFIX}setup/{device}/channel/{channel}"
        payload = ",".join(roles)
        mqtt_client.publish(topic, payload, retain=True)


# ====== Run App ======
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
