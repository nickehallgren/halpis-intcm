# HALPIS Intercom Beltpack for Raspberry Pi
# Copyright (c) 2024, Niclas Hallgren
# All rights reserved.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import fnmatch
from time import time, sleep
import copy
import os
import re
import inspect
import socket
import sys
import ssl
import signal
import logging
import subprocess
from typing import Dict, List, Tuple
from threading import Thread
import errno
import pyautogui
import RPi.GPIO as GPIO
import paho.mqtt.client as mqtt
from paho.mqtt.client import (
    Client,
    MQTTMessage,
    DisconnectFlags,
    ReasonCode,
    Properties
)
from typing import List
from ic import Intercom
from ic_ads1115 import IntercomADS1115
from ic_config import IntercomConfig
from ic_display import IntercomDisplay
from ic_button import IntercomButton
from ic_encoder import IntercomEncoder
from ic_menu_bp import menu


def is_mumble_window_visible():
    try:
        result = subprocess.run(
            ["xdotool", "search", "--onlyvisible", "--name", "Mumble"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        logger.critical(f"xdotool is not installed!")
        raise RuntimeError("xdotool is not installed")


def wait_for_mumble(timeout=60, interval=1):
    logger.debug(f"Waiting for Mumble window to appear...")
    start_time = time()
    while time() - start_time < timeout:
        if is_mumble_window_visible():
            logger.debug(f"Mumble window detected.")
            return True
        render_text_lines(
            0,
            [
                "WAITING",
                "FOR MUMBLE",
                "TO START..."
            ]
        )
        sleep(interval)
    logger.warning(f"Timeout: Mumble window not found.")
    return False

def mqtt_publish(topic: str, message: str) -> None:
    """
    Publish a message to an MQTT topic.

    Args:
        topic (str): The MQTT topic to publish to.
        message (str): The message to publish.
    """
    try:
        client.publish(topic, message, qos=1, retain=True)
    except ValueError as e:
        logger.warning(f"MQTT Publish ValueError occurred: {e}")
    except Exception as e:
        logger.warning(f"MQTT Publish An unexpected error occurred: {e}")


def mqtt_subscribe(topic: str) -> None:
    """
    Subscribe to an MQTT topic.

    Args:
        topic (str): The MQTT topic to subscribe to.
    """
    try:
        client.subscribe(topic, qos=1)
    except ValueError as e:
        logger.warning(f"MQTT Subscribe ValueError occurred: {e}")
    except Exception as e:
        logger.warning(f"MQTT Subscribe An unexpected error occurred: {e}")


def connect_mqtt() -> None:
    """
    Try to connect to MQTT
    """
    try:
        client.connect(intercom.mqtt_server, intercom.mqtt_port,
                       intercom.mqtt_keepalive)
    except ConnectionResetError as e:
        logger.warning(f"MQTT ConnectionResetError occurred: {e}")
        render_text_lines(
            0,
            [
                intercom.host_name,
                intercom.device_ip,
                intercom.mqtt_status_codes[3]
            ]
        )
        client.loop_stop()
        return
    except ConnectionRefusedError as e:
        logger.warning(f"MQTT ConnectionRefusedError occurred: {e}")
        render_text_lines(
            0,
            [
                intercom.host_name,
                intercom.device_ip,
                intercom.mqtt_status_codes[3]
            ]
        )
        client.loop_stop()
        return
    except socket.gaierror as e:
        logger.warning(
            f"MQTT Server not found (socket.gaierror) occurred: {e}")
        render_text_lines(
            0,
            [
                intercom.host_name,
                intercom.device_ip,
                intercom.mqtt_status_codes[98]
            ]
        )
        client.loop_stop()
        return
    except socket.timeout as e:
        logger.warning(f"MQTT Timeout occurred: {e}")
        render_text_lines(
            0,
            [
                intercom.host_name,
                intercom.device_ip,
                intercom.mqtt_status_codes[99]
            ]
        )
        client.loop_stop()
        return
    except ssl.SSLCertVerificationError as e:
        logger.warning(f"MQTT SSL Certification Error occurred: {e}")
        render_text_lines(
            0,
            [
                intercom.host_name,
                intercom.device_ip,
                "INVALID CERT"
            ]
        )
        client.loop_stop()
        return
    except OSError as e:
      if e.errno in {errno.EHOSTUNREACH, errno.ENETUNREACH, errno.ECONNABORTED}:
        logger.warning(f"MQTT network unreachable or host unreachable: {e}")
        render_text_lines(
            0,
            [
                intercom.host_name,
                intercom.device_ip,
                intercom.mqtt_status_codes[98]
            ]
        )
        client.loop_stop()
        return
    except Exception as e:
        logger.warning(f"MQTT Unknown Error occurred: {e}")
        render_text_lines(
            0,
            [
                intercom.host_name,
                intercom.device_ip,
                "UNKNOWN ERR"
            ]
        )
        client.loop_stop()
        return
    client.loop_start()


def on_connect(client: Client,
    userdata: None,
    flags: any,
    reason_code: any,
    properties: any,
) -> None:
    """
    MQTT connect, publish device information and subscribe to device 
    settings.
    
    Args:
        client (Client): The MQTT client instance.
        userdata (None): User-defined data of any type.
        flags (any): Response flags sent by the broker.
        reason_code (any): The connection result.
        properties (any): The properties associated with the connection.
    """
    if reason_code.is_failure:
        client.connected_flag = False
        if 'identifier rejected' in str(reason_code).lower():
            logger.warning(
                f"MQTT error: {str(reason_code).lower()}")
            render_text_lines(
                0,
                [
                    intercom.host_name,
                    intercom.device_ip,
                    intercom.mqtt_status_codes[2]
                ]
            )
        if 'broker unavailable' in str(reason_code).lower():
            logger.warning(
                f"MQTT error: {str(reason_code).lower()}")
            render_text_lines(
                0,
                [
                    intercom.host_name,
                    intercom.device_ip,
                    intercom.mqtt_status_codes[3]
                ]
            )
        if 'bad user name' in str(reason_code).lower():
            logger.warning(
                f"MQTT error: {str(reason_code).lower()}")
            render_text_lines(
                0,
                [
                    intercom.host_name,
                    intercom.device_ip,
                    intercom.mqtt_status_codes[4]
                ]
            )
        if 'not authorized' in str(reason_code).lower():
            logger.warning(
                f"MQTT error: {str(reason_code).lower()}")
            render_text_lines(
                0,
                [
                    intercom.host_name,
                    intercom.device_ip,
                    intercom.mqtt_status_codes[5]
                ]
            )
    else:
        logger.debug("MQTT connected")
        render_text_lines(
            0,
            [
                intercom.host_name,
                intercom.device_ip,
                intercom.mqtt_status_codes[0]
            ]
        )
        intercom.system_control = True
        client.connected_flag = True
    mqtt_publish(intercom.mqtt_prefix + "status/" +
                 intercom.host_name + "/state", "online")
    mqtt_publish(intercom.mqtt_prefix + "status/" +
                 intercom.host_name + "/device_channels",
                 intercom.channel_count)
    mqtt_publish(intercom.mqtt_prefix + "status/" +
                 intercom.host_name + "/device_type",
                 intercom.device_type)
    mqtt_publish(intercom.mqtt_prefix + "status/" +
                 intercom.host_name + "/allow_mic_level_change",
                 str(int(intercom.allow_mic_level_change)))
    mqtt_publish(intercom.mqtt_prefix + "status/" +
                 intercom.host_name + "/hs_audio_level",
                 intercom.get_audio_level())
    mqtt_publish(intercom.mqtt_prefix + "status/" +
                 intercom.host_name + "/mic_level",
                 intercom.get_mic_level())
    mqtt_publish(intercom.mqtt_prefix + "status/" +
                 intercom.host_name + "/in_menu",
                 "0")
    # SUBSCRIBE TO ROLE
    mqtt_subscribe(intercom.mqtt_prefix + "setup/" +
                   intercom.host_name + "/device_role")
    # SUBSCRIBE TO MIC LEVEL
    if intercom.allow_mic_level_change:
        mqtt_subscribe(intercom.mqtt_prefix + "setup/" +
                       intercom.host_name + "/mic_level")
    # SUBSCRIBE TO TALK
    mqtt_subscribe(intercom.mqtt_prefix + "broadcast/+/talk")
    # SUBSCRIBE TO CHANNEL SETUP
    for i in range(1, intercom.channel_count + 1):
        mqtt_subscribe(intercom.mqtt_prefix + "setup/" +
                       intercom.host_name + "/channel/" + str(i))

def on_disconnect(client: Client,
    userdata: None,
    rc: DisconnectFlags,
    properties: ReasonCode,
    reason_code: Properties
) -> None:
    """MQTT disconnected"""
    sleep(2)
    intercom.system_control = False
    clear_all_displays()
    clear_buttons()
    render_text_lines(
        0,
        [
            intercom.host_name,
            intercom.device_ip,
            "MQTT DISCNTD"
        ]
    )
    client.connected_flag = False


def update_talking_status(message: str, talks_to_me: str) -> None:
    """
    Update the talking status based on the message.

    Args:
        message (str): The message containing the talking status.
        talks_to_me (str): The entity that is talking to me.
    """
    if intercom.user in message:
        intercom.add_talking_to_me(talks_to_me, True)
    else:
        if "not talking" in message:
            if intercom.is_user_talking(talks_to_me):
                intercom.add_talking_to_me(talks_to_me, False)


def clear_display(index: int) -> None:
    """
    Clear the display at the given index.

    Args:
        index (int): The index of the display to clear.
    """
    displays[index].clear_display()


def render_text_display(index: int,
                        text: str,
                        font_path: str,
                        font_size: int,
                        freeze: bool = False,
                        freeze_start: int = None
                        ) -> None:
    current_time = int(time() * 1000)
    if freeze:
        displays[index].update_freeze = True
        if freeze_start != 0 or None:
            displays[index].update_freeze_start = current_time
        else:
            displays[index].update_freeze_start = 0
    displays[index].render_text(text, font_path, font_size)


def render_text_lines(
    display_id: int, 
    text: List[str], 
    font_path: str = None,
    font_size: int = None
) -> None:
    """
    Render text on the display.

    Args:
        index (int): The index of the display.
        text (str): The text to render on the display.
        font_path (str): The path to the font file.
        font_size (int): The size of the font.
        freeze (bool, optional): Whether to freeze the display. 
        Defaults to False.
        freeze_start (int, optional): The start time for freezing. 
        Defaults to None.
    """
    # Assign the default font path if not provided
    if font_path is None:
        font_path = intercom.font_path

    # Assign the default font size if not provided
    if font_size is None:
        font_size = intercom.small_font_size

    displays[display_id].render_text_lines(
        text,
        font_path,
        font_size
    )


def on_message(client: Client, userdata: None, 
               message: MQTTMessage) -> None:
    """
    Handle incoming MQTT messages and respond if needed.

    Args:
        client (Client): The MQTT client instance.
        userdata (Optional[None]): The private user data, not used in this 
                                   function.
        message (MQTTMessage): The message instance containing the topic and 
                               payload.
    """
    if message.topic == (intercom.mqtt_prefix
                         + "setup/"
                         + intercom.host_name
                         + "/device_role"
                         ):
        if str(message.payload.decode()) != "":
            intercom.user = str(message.payload.decode())
            mqtt_publish(intercom.mqtt_prefix
                         + "status/"
                         + intercom.host_name
                         + "/device_role",
                         intercom.user
                         )
            
    if message.topic == (intercom.mqtt_prefix
                         + "setup/"
                         + intercom.host_name
                         + "/mic_level"
                         ):
        if str(message.payload.decode()) != "":
            mic_level = str(message.payload.decode())
            if int(mic_level) >= 0 or int(mic_level) <= 150: 
                intercom.set_mic_level(int(mic_level))
                mqtt_publish(intercom.mqtt_prefix
                             + "status/"
                             + intercom.host_name
                             + "/mic_level",
                             str(intercom.get_mic_level())
                             )

    if (intercom.mqtt_prefix
        + "setup/"
        + intercom.host_name
        + "/channel/"
        ) in message.topic:
        for i in range(intercom.channel_count):
            if message.topic == (intercom.mqtt_prefix
                                 + "setup/"
                                 + intercom.host_name
                                 + "/channel/"
                                 + str(i + 1)
                                 ):
                intercom.talk_to[i] = str(message.payload.decode())
                mqtt_publish(
                    intercom.mqtt_prefix +
                    "status/" +
                    intercom.host_name +
                    "/channel/" +
                    str(i + 1),
                    intercom.talk_to[i]
                )

    if fnmatch.fnmatch(message.topic,
                       intercom.mqtt_prefix
                       + "broadcast/*/talk"
                       ):
        splitted_topic = message.topic.split('/')
        talks_to_me = splitted_topic[len(splitted_topic) - 2]
        if ',' in str(message.payload.decode()):
            # User is talking to many
            splitted_message = str(message.payload.decode()).split(',')
            for user in splitted_message:
                update_talking_status(user, talks_to_me)
        else:
            # User is only talking to me
            update_talking_status(str(message.payload.decode()), talks_to_me)


def publish_talking_to() -> None:
    """
    Publish the current talking status to MQTT.
    """
    talking_to = ""
    # Clear encoder lock
    buttons[intercom.channel_count].is_locked = False
    for i in buttons:
        if (buttons[i].is_locked
                or buttons[i].is_pressed
                and i <= (intercom.channel_count - 1)
                ):
            if talking_to:
                talking_to += ","
            talking_to += intercom.talk_to[i]

    if talking_to == "":
        mqtt_publish(intercom.mqtt_prefix + "broadcast/" +
                     intercom.user.lower() + "/talk", "not talking")
        intercom.published_talk_to = "not talking"
    else:
        if talking_to != intercom.published_talk_to:
            mqtt_publish(intercom.mqtt_prefix + "broadcast/" +
                         intercom.user.lower() + "/talk", talking_to)
            intercom.published_talk_to = talking_to


def show_menu(main: int, sub: int, active: int) -> None:
    """
    Display the menu on the screen.

    Args:
        main (int): The main menu index.
        sub (int): The sub menu index.
        active (int): The currently active menu item.
    """
    max_lines = displays[0].get_max_text_lines(font_path=intercom.font_path,
                                           font_size=intercom.small_font_size)
    lines = []
    total_lines = len(menu[main])

    if total_lines <= max_lines:
        lines = [menu[main][i]["name"] for i in range(total_lines)]
        start = 0
    else:
        # Make sure the active line is always within the displayed lines
        if active < max_lines // 2:
            start = 0
        elif active > total_lines - (max_lines // 2):
            start = total_lines - max_lines
        else:
            start = active - (max_lines // 2)

        end = start + max_lines
        lines = [menu[main][i]["name"] for i in range(start, end)]

    displays[0].update_freeze = True
    displays[0].update_freeze_start = 0
    displays[0].clear_display()
    displays[0].update_menu(
        lines=lines,
        active_line=active - start,
        max_lines=max_lines,
        font_path=intercom.font_path,
        font_size=intercom.small_font_size
    )


def hide_menu() -> None:
    """
    Hide the menu and disable update freeze.
    """
    intercom.in_menu = False
    displays[0].update_freeze = False
    mqtt_publish(intercom.mqtt_prefix
                 + "status/"
                 + intercom.host_name
                 + "/in_menu",
                 "0"
                 )
    


def button_long_press_callback(button: IntercomButton) -> None:
    """
    Callback function for handling long press on a button.

    Args:
        button (IntercomButton): The button that was long pressed.
    """
    intercom.last_interaction_time = int(time() * 1000)
    # Only listen for long press on button 2 to enter menu mode
    if button.num == 2 and not intercom.in_menu:
        intercom.in_menu = True
        intercom.menu_main = 0
        intercom.menu_sub = 0
        show_menu(intercom.menu_main, intercom.menu_sub, 0)
        mqtt_publish(intercom.mqtt_prefix
                     + "status/"
                     + intercom.host_name
                     + "/in_menu",
                     "1"
                     )
        # print("In menu mode")


def menu_logic(main: int, sub: int):
    """
    Handle the logic for displaying and interacting with the menu.

    Args:
        main (int): The main menu index.
        sub (int): The sub menu index.
    """
    global menu

    def show_menu_and_set_intercom(menu_main, menu_sub):
        show_menu(
            menu_main["main"],
            menu_main["sub"],
            menu_main["active"]
        )
        intercom.menu_main = menu_main["main"]
        intercom.menu_sub = menu_main["sub"]

    if main == 0:
        # Main menu
        if sub == 0:
            hide_menu()
        elif sub == 1:
            # Enter lock menu
            for i in range(intercom.channel_count):
                menu[1][i + 1]["name"] = (
                    f"LOCK {i + 1} "
                    f"{'ON' if intercom.lock_buttons[i] else 'OFF'}"
                )
            show_menu_and_set_intercom(menu[0][1], menu[0][1])
        elif sub == 2:
            # Enter Mic Level menu
            show_menu_and_set_intercom(menu[0][2], menu[0][2])
        elif sub == 3:
            # Enter Shut down menu
            show_menu_and_set_intercom(menu[0][3], menu[0][3])
    elif main == 1:
        # Button lock menu
        if sub == 0:
            show_menu_and_set_intercom(menu[1][0], menu[1][0])
        elif 1 <= sub <= intercom.channel_count:
            index = sub - 1
            intercom.lock_buttons[index] = not intercom.lock_buttons[index]
            menu[1][sub]["name"] = (
                f"LOCK {sub} "
                f"{'ON' if intercom.lock_buttons[index] else 'OFF'}"
            )
            show_menu_and_set_intercom(menu[1][sub], menu[1][sub])
    elif main == 2:
        # Mic level menu
        if sub == 0:
            show_menu_and_set_intercom(menu[2][0], menu[2][0])
        elif sub == 1:
            mic_level = intercom.get_mic_level()
            render_text_display(
                index=0,
                text=f"MIC: {mic_level}%",
                font_path=intercom.font_path,
                font_size=intercom.small_font_size,
                freeze=True,
                freeze_start=0
            )
    elif main == 3:
        # Shutdown menu
        if sub == 0:
            show_menu_and_set_intercom(menu[3][0], menu[3][0])
        elif sub == 1:
            intercom.system_active = False


def button_change_callback(button: IntercomButton) -> None:
    """
    Callback function for handling button state changes.

    Args:
        button (IntercomButton): The button that changed state.
    """
    intercom.last_interaction_time = int(time() * 1000)
    if intercom.lock_buttons[button.num] == False:
        button.is_locked = False

    if button.is_pressed:
        if button.num == 2: # Encoder button
            if intercom.in_menu:
                # Only listen for encoder button when in menu mode
                # print("Encoder pressed")
                menu_logic(intercom.menu_main, intercom.menu_sub)
            else:
                render_text_display(
                    index=0,
                    text=f"\n\nHOLD FOR MENU",
                    font_path=intercom.font_path,
                    font_size=intercom.small_font_size,
                    freeze=True
                )
        else:
            # Buttons 0-1
            publish_talking_to()
            gui_button_press(button.num + 1)
    else:
        if button.num == 2:
            # Encoder button
            if (intercom.menu_main == 2 and intercom.menu_sub == 1
                    and not intercom.encoder_adjust):
                # Main and sun must be the same as set mic level in menu_lines
                intercom.encoder_adjust = True
            elif (intercom.menu_main == 2 and intercom.menu_sub == 1
                  and intercom.encoder_adjust):
                show_menu(2, 1, 1)
                intercom.encoder_adjust = False
        else:
            # Buttons 0-1
            if button.is_locked == False:
                publish_talking_to()
                gui_button_release(button.num + 1)


def initialize_buttons(pins: list[int]) -> dict[int, IntercomButton]:
    """
    Initialize buttons with given pins and return a dictionary of buttons.

    Args:
        pins (List[int]): A list of GPIO pin numbers for the buttons.

    Returns:
        Dict[int, IntercomButton]: A dictionary mapping button indices to 
                                   IntercomButton instances.
    """
    buttons = {
        index: IntercomButton(
            pin=pin,
            num=index,
            on_button_change=button_change_callback,
            on_long_press=button_long_press_callback,
            )
            for index, pin in enumerate(pins)}
    return buttons


def get_ip() -> str:
    """
    Returns the IP address or 'NO IP' if it cannot be determined.

    Returns:
        str: The IP address or 'NO IP' if it cannot be determined.
    """
    try:
        ip = str(subprocess.check_output(
            ['hostname', '--all-ip-addresses']).strip().decode()
        )
        if ip.split(".")[0] == "169" or ip == "":
            return "N/A"
        return ip
    except:
        return "N/A"


def initialize_displays(i2c_port: int = 1) -> dict[int, IntercomDisplay]:
    """
    Initialize displays for each multiplexer port and return a dictionary 
    of displays.

    Args:
        i2c_port (int, optional): The I2C port number. Defaults to 1.

    Returns:
        Dict[int, IntercomDisplay]: A dictionary mapping display indices to 
                                    IntercomDisplay instances.
    """
    displays = {}

    # Initialize the display on the selected port
    display = IntercomDisplay(
        num=0, 
        i2c_address=0x3c,
        i2c_port=i2c_port,
        display_brightness=intercom.display_brightness,
        display_type="sh1106",
        width=128,
        height=64
    )

    # Store the display in the dictionary with the index as the key
    displays[0] = display

    return displays


def clear_all_displays() -> None:
    """
    Clear all displays by calling the clear_display function 
    for each display.
    """
    for i in displays:
        clear_display(i)


def clear_buttons() -> None:
    """
    Unlock all buttons.
    """
    # Unlock all buttons
    for i in buttons:
        buttons[i].is_locked = False


def get_wifi_status(interface: str) -> Dict[str, str]:
    """
    Return info about the WiFi link quality, signal level, and access point.
    
    Args:
        interface (str): The WiFi interface to query (e.g., 'wlan0').
    
    Returns:
        dict: A dictionary with keys 'link_quality', 'signal_level', 
        and 'active_ap'.
    """
    try:
        # Run the iwconfig command
        with subprocess.Popen(
            ["iwconfig", interface],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        ) as proc:
            output, err = proc.communicate()

            # Check if the command failed
            if proc.returncode != 0:
                raise RuntimeError(f"Error running iwconfig: {err.strip()}")

        # Initialize default values
        signal_level, active_ap = "N/A", "N/A"

        # Use regex to parse the required values
        match_signal = re.search(r"Signal level=(-?\d+ dBm)", output)
        match_ap = re.search(r"Access Point: ([0-9A-Fa-f:]+)", output)

        if match_signal:
            signal_level = match_signal.group(1)
        if match_ap:
            active_ap = match_ap.group(1)

        return {
            'signal_level': signal_level,
            'active_ap': active_ap
        }

    except Exception as e:
        return {
            'signal_level': "N/A",
            'active_ap': "N/A",
            'error': str(e)
        }


def gui_button_press(button_index: int) -> None:
    """
    Send CTRL + num to simulate shortcut in Mumble.

    Args:
        button_index (int): The number to press.
    """
    pyautogui.keyDown('ctrl')
    pyautogui.keyDown(str(button_index))


def gui_button_release(button_index: int) -> None:
    """
    Release CTRL + num in Mumble.

    Args:
        button_index (int): The number to release.
    """
    crtl_needed = False
    for i in buttons:
        if buttons[i].is_locked or buttons[i].is_pressed:
            crtl_needed = True
    if not crtl_needed:
        pyautogui.keyUp('ctrl')
    pyautogui.keyUp(str(button_index))

def encoder_changed(value: int, direction: str) -> None:
    """
    Handle encoder changes.

    Args:
        value (int): The current value of the encoder.
        direction (str): The direction of the encoder movement 
                        ('R' for right, 'L' for left).
    """
  
    intercom.last_interaction_time = int(time() * 1000)
    
    # Wake up the display if screensaver is active, don't change anything
    if intercom.screensaver_activated:
        return
    
    if not intercom.in_menu:
        # Not in menu, adjust audio level
        audio_level = intercom.get_audio_level()
        if audio_level != -1:
            if direction == "R":
                if audio_level < 150:
                    audio_level += 5
            else:
                if audio_level > 0:
                    audio_level -= 5
            intercom.set_audio_level(audio_level)
            mqtt_publish(intercom.mqtt_prefix
                         + "status/"
                         + intercom.host_name
                         + "/hs_audio_level",
                         str(audio_level)
                         )
    else:
        # In menu
        if intercom.encoder_adjust:
            # Adjust mic level
            if intercom.menu_main == 2 and intercom.menu_sub == 1:
                mic_level = intercom.get_mic_level()
                if mic_level != -1:
                    if direction == "R":
                        if mic_level < 150:
                            mic_level += 5
                    else:
                        if mic_level > 0:
                            mic_level -= 5
                    intercom.set_mic_level(mic_level)
                    mqtt_publish(intercom.mqtt_prefix
                                + "status/"
                                + intercom.host_name
                                + "/mic_level",
                                str(mic_level)
                                )
                    render_text_display(
                        index=0,
                        text=f"MIC: {mic_level}%",
                        font_path=intercom.font_path,
                        font_size=intercom.small_font_size,
                        freeze=True,
                        freeze_start=0
                    )
        else:
            if value > intercom.encoder_last:
                sub_max = max(
                    menu[intercom.menu_main].keys())
                if intercom.menu_sub + 1 <= sub_max:
                    intercom.menu_sub += 1
                    show_menu(main=intercom.menu_main,
                              sub=intercom.menu_sub, active=intercom.menu_sub)
            else:
                if intercom.menu_sub - 1 == 0:
                    intercom.menu_sub -= 1
                    show_menu(main=intercom.menu_main,
                              sub=intercom.menu_sub, active=intercom.menu_sub)
                elif intercom.menu_sub - 1 > 0:
                    intercom.menu_sub -= 1
                    show_menu(main=intercom.menu_main,
                              sub=intercom.menu_sub, active=intercom.menu_sub)

            # Update last encoder value
            intercom.encoder_last = value

def update_device_status():
    battery_mv = ads1115.measure_voltage(0, intercom.battery_correction)
    if battery_mv != None:
        intercom.battery_voltage = battery_mv
        # Set battery level
        if battery_mv >= 8000:
            intercom.battery_level = 5
        elif battery_mv >= 7675:
            intercom.battery_level = 4
        elif battery_mv >= 7350:
            intercom.battery_level = 3
        elif battery_mv >= 7025:
            intercom.battery_level = 2
        elif battery_mv >= 6700:
            intercom.battery_level = 1
        
        if battery_mv <= intercom.battery_shutdown:
            intercom.battery_shutdown_status = 1
        elif battery_mv <= intercom.battery_warning:
            intercom.battery_warning_status = 1

        mqtt_publish(intercom.mqtt_prefix
                    + "status/"
                    + intercom.host_name
                    + "/battery_powered",
                    "1"
                    )
        mqtt_publish(intercom.mqtt_prefix
                    + "status/"
                    + intercom.host_name
                    + "/battery_voltage",
                    str(battery_mv)
                    )
    else:
        logger.warning(f"Battery status error {battery_mv}")
        
    wifi_status = get_wifi_status(intercom.interface)
    if 'error' in wifi_status and wifi_status['error']:
        logger.warning(f"Wifi status error {wifi_status['error']}")
    else:
        mqtt_publish(intercom.mqtt_prefix
                     + "status/"
                     + intercom.host_name
                     + "/wifi_signal_level",
                     wifi_status['signal_level']
                     )
        mqtt_publish(intercom.mqtt_prefix
                     + "status/"
                     + intercom.host_name
                     + "/access_point_mac",
                     wifi_status['active_ap']
                     )
        mqtt_publish(intercom.mqtt_prefix
                     + "status/"
                     + intercom.host_name
                     + "/device_ip",
                     intercom.device_ip
                     )
    

def system_control():
    """
    Control the system operation.
    """
    UPDATE_INTERVAL_MS = 50  # Define update interval as 50 milliseconds
    # Define screensaver update interval as 5000 milliseconds
    SCREENSAVER_INTERVAL_MS = 5000
    last_screensaver_update = time() * 1000

    while intercom.system_control:
        # Get the current time in milliseconds
        current_time = int(time() * 1000)
        elapsed_time = current_time - last_screensaver_update

        # Battery too low, shutdown
        if intercom.battery_shutdown_status:
          intercom.system_active = False
          
        # Displays
        for i in displays:
            current_display = displays[i]
            if not current_display.update_freeze:
                if (buttons[0].is_pressed or buttons[1].is_pressed or 
                    buttons[0].is_locked or buttons[1].is_locked):
                    # Talking
                    if buttons[0].is_pressed or buttons[0].is_locked:
                        if buttons[1].is_pressed or buttons[1].is_locked:
                            # B is also pressed
                            current_text = (
                                intercom.talk_to[0] +
                                "," +
                                intercom.talk_to[1]
                            )
                        else:
                            # Only A is pressed
                            current_text = intercom.talk_to[0]
                    else:
                        current_text = intercom.talk_to[1]

                    if current_display.text != current_text:
                        if ',' in current_text:
                            # Time-based split update
                            if (current_display.last_text_split
                                        + intercom.multi_talk_delay_ms
                                        < current_time
                                    ):
                                text_split = current_text.split(',')
                                text_index = current_display.text_split

                                # Update the display text
                                current_display.render_talk_view(
                                    volume=str(intercom.audio_level),
                                    talk_to=text_split[text_index],
                                    ip=intercom.device_ip,
                                    font_path=intercom.font_path
                                )
                                
                                current_display.last_text_split = current_time

                                # Update the index for the next split
                                if text_index + 1 < len(text_split):
                                    current_display.text_split += 1
                                else:
                                    current_display.text_split = 0
                        else:
                            # Direct update if no split is needed
                            current_display.render_talk_view(
                                volume=str(intercom.audio_level),
                                talk_to=current_text,
                                ip=intercom.device_ip,
                                font_path=intercom.font_path
                            )
                    current_display.last_audio_level = 0
                    current_display.last_battery_level = 0
                else:
                    # Listening
                    if intercom.battery_warning_status:
                        if (current_display.last_text_split 
                            + intercom.multi_talk_delay_ms <= current_time
                            ):
                            current_display.last_text_split = current_time
                            current_display.render_main_view(
                                device_type=intercom.device_type,
                                battery_display=intercom.battery_display,
                                volume=str(intercom.audio_level),
                                battery_voltage=intercom.battery_voltage,
                                low_batt=1,
                                user=intercom.user,
                                ip=intercom.device_ip,
                                font_path=intercom.font_path
                            )
                    else:
                        screensaver_active = intercom.screensaver
                        time_exceeded = (current_time - 
                                        intercom.last_interaction_time) >= (
                                        intercom.screensaver_delay * 1000
                        )
                        not_in_menu = not intercom.in_menu
                        if (screensaver_active and time_exceeded and 
                            not_in_menu):
                            if elapsed_time >= SCREENSAVER_INTERVAL_MS:
                                # Screensaver on
                                intercom.screensaver_activated = True
                                last_screensaver_update = current_time
                                ic_sb = intercom.screensaver_brightness
                                current_display.render_screensaver(
                                    user=intercom.user,
                                    screensaver_brightness=ic_sb,
                                    font_path=intercom.font_path
                                )
                                # Change something to update the display 
                                # when screensaver turns off
                                current_display.last_audio_level = 0
                        else:
                            intercom.screensaver_activated = False
                            if (current_display.last_audio_level != 
                                intercom.audio_level or
                                current_display.last_battery_level !=
                                intercom.battery_level or 
                                (intercom.battery_display == "mV" and
                                current_display.last_battery_voltage != 
                                intercom.battery_voltage or
                                current_display.text != intercom.user)
                                ):
                                # Update only if audio level or 
                                # battery changes
                                cd = current_display
                                ic = intercom
                                cd.last_audio_level = ic.audio_level
                                cd.last_battery_level = ic.battery_level
                                cd.last_battery_voltage = ic.battery_voltage
                                cd.text = ic.user
                                current_display.render_main_view(
                                    device_type=intercom.device_type,
                                    battery_display=intercom.battery_display,
                                    volume=str(intercom.audio_level),
                                    battery_voltage=intercom.battery_voltage,
                                    low_batt=0,
                                    user=intercom.user,
                                    ip=intercom.device_ip,
                                    font_path=intercom.font_path
                                )
            else:
                current_display.last_audio_level = 0
                current_display.last_battery_level = 0
                current_display.last_battery_voltage = 0
                if current_display.update_freeze_start > 0:
                    if (current_display.update_freeze_start
                        + current_display.update_freeze_time_ms
                        <= current_time
                        ):
                        current_display.update_freeze = False

        # Status update
        if (intercom.last_status_update + intercom.status_interval_ms < 
            current_time):
            intercom.last_status_update = current_time
            update_device_status()

        # Sleep for the defined interval to control update frequency
        sleep(UPDATE_INTERVAL_MS / 1000.0)


def cleanup():
    """
    Clean up everything before shutdown.
    """
    # Update config if needed
    if 'intercom' in globals():
        update_config = 0
        audio_level = intercom.get_audio_level()
        mic_level = intercom.get_mic_level()
        if audio_level != config.audio_level:
            if 0 < audio_level <= 150:
                # Audio level has changed, update config
                config.audio_level = audio_level
                update_config = 1
        if config.mic_level != mic_level:
            if 0 < mic_level <= 150:
                # Mic level has changed, update config
                config.mic_level = mic_level
                update_config = 1
        if config.lock_buttons != intercom.lock_buttons:
            # Lock buttons has changed, update config
            config.lock_buttons = intercom.lock_buttons
            update_config = 1
        if update_config:
            config.save()

        if intercom.system_active:
            # Only log if not user shutdown
            stack = inspect.stack()
            if len(stack) > 1:
                caller_frame = stack[1]
                caller_name = caller_frame.function
                module_name = caller_frame.filename
                line_number = caller_frame.lineno
                logger.info(
                    f"Cleanup called from {caller_name} in "
                    f"{module_name} at line {line_number}, stopping script.")
            else:
                logger.info("Cleanup called without a valid "
                            "caller in the stack.")

        if not intercom.cleanup_done:
            intercom.cleanup_done = True
            intercom.system_control = False
            mqtt_publish(intercom.mqtt_prefix + "status/" +
                         intercom.host_name + "/in_menu",
                         "0")
            mqtt_publish(intercom.mqtt_prefix + "status/" +
                         intercom.host_name + "/state", "offline")
            mqtt_publish(intercom.mqtt_prefix + "broadcast/" +
                        intercom.user.lower() + "/talk", "not talking")
            clear_buttons()
            clear_all_displays()
            GPIO.cleanup()
            # Leave remove battery on display
            if intercom.battery_shutdown_status:
                render_text_lines(
                    0,
                    [
                        "Wait ~30s",
                        "then remove",
                        "empty batt!"
                    ]
                )
            else:
                render_text_lines(
                    0,
                    [
                        "Wait ~30s",
                        "then remove",
                        "the battery!"
                    ]
                )
            if not intercom.system_active:
                subprocess.run(['systemctl', 'poweroff'], check=True)


def signal_handler(sig, frame):
    """
    Handle termination signals for cleanup.
    """
    cleanup()
    sys.exit(0)


if __name__ == "__main__":
    global ads1115, buttons, config, displays, intercom

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    mumble_started = False

    # Mapping of log level names to logging constants
    log_level_mapping = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
    # Load config from file
    current_dir = os.path.dirname(__file__)
    config_file_path = os.path.join(current_dir, "config_bp.json5")

    config = IntercomConfig(
        file_path=config_file_path).load()

    # Get the logging level from the config
    log_level = log_level_mapping.get(config.log_level.upper())
    
    if log_level is None:
        valid_levels = ', '.join(log_level_mapping.keys())
        print(
            f"Invalid log level '{config.log_level}'. "
            f"Valid options are: {valid_levels}. "
            f"Falling back to WARNING.")
        log_level = logging.WARNING

    # Create a list for handlers
    handlers = []

    # Configure FileHandler if log_to_file is True
    if config.log_to_file:
        handlers.append(logging.FileHandler(config.log_file))

    # Configure StreamHandler if log_to_screen is True
    if config.log_to_screen:
        handlers.append(logging.StreamHandler())

    # SETUP LOGGING
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(levelname)s %(filename)s \
            at line %(lineno)d : %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers
    )
    logger = logging.getLogger()

    # Initialize Intercom
    intercom = Intercom(
        allow_mic_level_change=config.allow_mic_level_change,
        battery_correction=config.battery_correction,
        battery_display=config.battery_display,
        battery_shutdown=config.battery_shutdown,
        battery_warning=config.battery_warning,
        channel_count=config.channel_count,
        device_type=config.device_type,
        display_brightness=config.display_brightness,
        encoder_rotation_invert=config.encoder_rotation_invert,
        font_path=config.font_path,
        host_name=socket.gethostname(),
        interface=config.network_interface,
        lock_buttons=copy.deepcopy(config.lock_buttons),
        mqtt_keepalive=config.mqtt_keepalive,
        mqtt_pass=config.mqtt_pass,
        mqtt_port=config.mqtt_port,
        mqtt_prefix=config.mqtt_prefix,
        mqtt_server=config.mqtt_server,
        mqtt_user=config.mqtt_user,
        multi_talk_delay_ms=config.multi_talk_delay_ms,
        screensaver=config.screensaver,
        screensaver_brightness=config.screensaver_brightness,
        screensaver_delay=config.screensaver_delay,
        status_interval_ms=config.status_interval_ms,
        tls_certificate_path=config.tls_certificate_path
    )

    # Set audio and mic level
    intercom.set_audio_level(config.audio_level)
    intercom.set_mic_level(config.mic_level)

    # ADS1115
    ads1115 = IntercomADS1115(0x4a, 0)
    
    # Encoder
    if intercom.encoder_rotation_invert:
        encoder = IntercomEncoder(13, 15, encoder_changed)
    else:
        encoder = IntercomEncoder(15, 13, encoder_changed)
        
    # Displays
    displays = initialize_displays()
    render_text_lines(
        0,
        [
            "HALPIS",
            "INTCM",
            intercom.version
        ]
    )

    sleep(3)
    render_text_lines(
        0,
        [
            intercom.host_name,
            "",
            ""
        ]
    )
    
    # Initialize GPIO
    GPIO.setmode(GPIO.BOARD)
    # Define the GPIO pins for the buttons
    button_pins = [31, 37, 29]

    # Create button objects
    buttons = initialize_buttons(button_pins)
    clear_buttons()

    global client
    mqtt.Client.connected_flag = False

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=intercom.host_name,
                         clean_session=False,
                         userdata=None
                         )
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    client.tls_set(
        # Can be your self-signed CA or a real CA bundle
        ca_certs=intercom.tls_certificate_path,
        certfile=None,
        keyfile=None,
        tls_version=ssl.PROTOCOL_TLS_CLIENT
    )
    client.username_pw_set(username=intercom.mqtt_user, 
                           password=intercom.mqtt_pass)
    client.will_set(intercom.mqtt_prefix
                    + "status/"
                    + intercom.host_name
                    + "/state",
                    "offline",
                    qos=1,
                    retain=True
                    )

    try:
        while intercom.system_active:
            if intercom.device_ip == "":
                render_text_lines(
                    0,
                    [
                        intercom.host_name,
                        "NO IP",
                        ""
                    ]
                )
                
                intercom.device_ip = get_ip()
                render_text_lines(
                    0,
                    [
                        intercom.host_name,
                        intercom.device_ip,
                        "CONNECTING"
                    ]
                )

            # IS MQTT CONNECTED?
            if not client.connected_flag:
                IntercomButton.buttons_enabled = False
                if intercom.device_ip != "N/A":
                    logger.debug("Attempting MQTT connection...")
                    connect_mqtt()

            if client.connected_flag:
                # Display status on displays
                sleep(1)
                if not mumble_started:
                  intercom.last_interaction_time = int((time() + 125) * 1000)
                  if wait_for_mumble(timeout=120):
                      mumble_started = True
                      sleep(5)
                      # This is used to track user activity and 
                      # manage the screensaver
                      intercom.last_interaction_time = int(time() * 1000)
                if (intercom.system_control_thread is None
                    or not intercom.system_control_thread.is_alive()
                    ):
                    IntercomButton.buttons_enabled = True
                    try:
                        intercom.system_control_thread = Thread(
                            target=system_control, args=())
                        intercom.system_control_thread.start()
                    except RuntimeError as e:
                        logger.critical(f"RuntimeError starting thread: {e}")
                        sys.exit(1)
                    except TypeError as e:
                        logger.critical(f"TypeError starting thread: {e}")
                        sys.exit(1)
                    except Exception as e:  # Catching any other
                        # unforeseen exceptions
                        logger.critical(
                            f"Error: unable to start thread. Exception: {e}")
                        sys.exit(1)
            sleep(1)
    finally:
        cleanup()