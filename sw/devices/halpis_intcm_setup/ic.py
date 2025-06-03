# Copyright (c) 2024, Niclas Hallgren
# All rights reserved.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import subprocess
import re
import logging
from time import time
from typing import Dict, List, Tuple, Optional
from threading import Thread
from dataclasses import dataclass, field


@dataclass
class Intercom:
    """
    A class to manage intercom functionality, including microphone and 
    audio level control, user interactions, MQTT status reporting, and
    menu states. Designed for hardware such as beltpacks and basestations.
    """

    # === Required Fields ===
    allow_mic_level_change: bool

    # === Optional/Default Fields ===
    audio_level: int = 0
    battery_correction: float = 3.15
    battery_display: str = "icon"
    battery_level: int = 0
    battery_shutdown: Optional[int] = field(default=None)
    battery_shutdown_status: bool = False
    battery_voltage: int = 0
    battery_warning: Optional[int] = field(default=None)
    battery_warning_status: bool = False
    channel_count: int = 0
    cleanup_done: bool = False
    device_ip: str = ""
    device_type: str = ""
    display_brightness: int = 255
    encoder_adjust: bool = False
    encoder_last: int = 0
    encoder_rotation_invert: bool = False
    font_path: str = ""
    headset: bool = False
    headset_audio_level: int = 0
    host_name: str = ""
    in_menu: bool = False
    interface: str = ""
    last_status_update: int = 0
    lock_buttons: List[bool] = field(default_factory=list)
    menu_main: int = 0
    menu_sub: int = 0
    mqtt_keepalive: int = 0
    mqtt_pass: str = ""
    mqtt_port: int = 0
    mqtt_prefix: str = ""
    mqtt_server: str = ""
    mqtt_status_codes: Dict[int, str] = field(default_factory=lambda: {
        0: "SUCCESS",
        1: "INCOR PROT",
        2: "INVAL CLNT",
        3: "SRV UNAVAIL",
        4: "BAD US/OW",
        5: "NOT AUTH",
        98: "SRV NOT FOUND",
        99: "TIMEOUT"
    })
    mqtt_user: str = ""
    multi_talk_delay_ms: int = 0
    neopixel_blink_rate_ms: int = 500
    neopixel_brightness: float = 0.06
    neopixel_post_talk_blink_ms: int = 1500
    normal_font_size: int = 26
    published_talk_to: str = ""
    screensaver_activated: bool = False
    screensaver: bool = False
    screensaver_delay: int = 15000
    screensaver_brightness: int = 16
    small_font_size: int = 16
    status_interval_ms: int = 0
    system_active: bool = True
    system_control: bool = True
    system_control_thread: Optional[Thread] = None
    tls_certificate_path: str = ""
    user: str = "NO SETUP"
    version: str = "SW v1.0"

    # === Init-only/Internal Fields ===
    logger: logging.Logger = field(init=False, repr=False)
    last_interaction_time: int = field(init=False)
    talking_to_me: Dict[str, Tuple[int, bool]] = field(
        default_factory=dict, init=False)
    talk_to: Dict[int, str] = field(default_factory=dict, init=False)

    def __post_init__(self):
        """
        Perform post-initialization setup for the Intercom instance.

        - Initializes the logger.
        - Validates `device_type` and required battery parameters.
        - Sets up default communication channels based on `channel_count`.
        - Sets last interaction time.
        """
        self.logger = logging.getLogger(__name__)
        self.last_interaction_time = int(time() * 1000)

        allowed_types = {"beltpack", "basestation"}
        if self.device_type not in allowed_types:
            raise ValueError(
                f"device_type must be one of {allowed_types}, got '{self.device_type}'.")

        if self.device_type == "beltpack":
            if self.battery_warning is None:
                raise ValueError(
                    "battery_warning must be specified for device_type 'beltpack'.")
            if self.battery_shutdown is None:
                raise ValueError(
                    "battery_shutdown must be specified for device_type 'beltpack'.")

        for i in range(self.channel_count):
            self.talk_to[i] = ""

    def add_talking_to_me(self, role: str, is_talking: bool):
        """
        Add or update a role's talking status and timestamp.

        Args:
            role (str): The role identifier.
            is_talking (bool): Whether the role is currently talking.
        """
        self.logger.debug(
            f"Adding or updating role: {role} with talking status {is_talking}.")
        current_time = int(time() * 1000)

        if role in self.talking_to_me:
            self.talking_to_me[role] = (current_time, is_talking)
        else:
            self.talking_to_me[role] = (current_time, is_talking)

    def clear_talking_to_me(self):
        """
        Remove all role entries from the `talking_to_me` dictionary.
        """
        self.logger.debug("Clearing all entries from talking_to_me.")
        self.talking_to_me.clear()

    def is_user_talking(self, role: str) -> bool:
        """
        Check if a specific user (by role) is currently talking.

        Args:
            role (str): The role identifier.

        Returns:
            bool: True if the user is currently talking, False otherwise.
        """
        self.logger.debug(f"Checking if {role} is talking.")
        return self.talking_to_me.get(role, (None, False))[1]

    def round_to_nearest_5(self, number) -> int:
        """
        Round a given number to the nearest multiple of 5.

        Args:
            number (int or float): The number to be rounded.

        Returns:
            int: The number rounded to the nearest multiple of 5.
        """
        self.logger.debug(f"Rounding {number} to the nearest multiple of 5.")
        return round(number / 5) * 5

    def get_mic_level(self) -> int:
        """
        Get the current microphone input level as a percentage.

        Returns:
            int: The rounded microphone level (0–150%), or -1 if unavailable.
        """
        self.logger.debug("Getting the current microphone level.")
        try:
            command = "pacmd list-sources | grep 'volume: mono'"
            mic_data = subprocess.run(
                f"sudo -u '#1000' XDG_RUNTIME_DIR=/run/user/1000 {command}",
                shell=True,
                capture_output=True,
                text=True
            )
            if mic_data.returncode == 0:
                matches = re.findall(r'(\d+)%', mic_data.stdout)
                if matches:
                    return self.round_to_nearest_5(int(matches[0]))
            return -1
        except Exception as e:
            self.logger.error(f"Error retrieving microphone level: {e}")
            return -1

    def set_mic_level(self, mic_level: int) -> None:
        """
        Set the system microphone input level.

        Args:
            mic_level (int): Desired microphone level (0–150%).

        Logs:
            Errors if setting fails or value is invalid.
        """
        self.logger.debug(f"Setting microphone level to {mic_level}.")
        if 0 <= mic_level <= 150:
            try:
                command = f"pactl set-source-volume @DEFAULT_SOURCE@ {mic_level}%"
                subprocess.run(
                    f"sudo -u '#1000' XDG_RUNTIME_DIR=/run/user/1000 {command}",
                    shell=True,
                    check=True
                )
            except Exception as e:
                self.logger.error(f"Error setting microphone level: {e}")
        else:
            self.logger.error(
                f"Invalid microphone level: {mic_level}. Must be between 0 and 150.")

    def get_audio_level(self) -> int:
        """
        Get the current audio output level as a percentage.

        Returns:
            int: The rounded audio output level (0–150%), or -1 if unavailable.
        """
        self.logger.debug("Getting the current audio level.")
        try:
            command = "pactl get-sink-volume @DEFAULT_SINK@ | grep 'front-left: '"
            audio_data = subprocess.run(
                f"sudo -u '#1000' XDG_RUNTIME_DIR=/run/user/1000 {command}",
                shell=True,
                capture_output=True,
                text=True
            )
            if audio_data.returncode == 0:
                matches = re.findall(r'(\d+)%', audio_data.stdout)
                if matches:
                    if self.headset:
                        return self.round_to_nearest_5(self.headset_audio_level)
                    return self.round_to_nearest_5(int(matches[0]))
            return -1
        except Exception as e:
            self.logger.error(f"Error retrieving audio level: {e}")
            return -1

    def set_audio_level(self, audio_level: int) -> None:
        """
        Set the audio output level.

        Args:
            audio_level (int): Desired audio level (0–150%).

        Updates:
            `audio_level` or `headset_audio_level` based on current mode.
        Logs:
            Errors if command execution fails.
        """
        self.logger.debug(f"Setting audio level to {audio_level}.")
        if 0 <= audio_level <= 150:
            try:
                command = f"pactl set-sink-volume @DEFAULT_SINK@ {audio_level}%"
                subprocess.run(
                    f"sudo -u '#1000' XDG_RUNTIME_DIR=/run/user/1000 {command}",
                    shell=True,
                    check=True
                )
                if self.headset:
                    self.headset_audio_level = audio_level
                else:
                    self.audio_level = audio_level
            except Exception as e:
                self.logger.error(f"Error setting audio level: {e}")
        else:
            self.logger.error(
                f"Invalid audio level: {audio_level}. Must be between 0 and 150.")
