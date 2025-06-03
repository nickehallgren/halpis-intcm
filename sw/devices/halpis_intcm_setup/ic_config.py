# This module is part of the HALPIS Intercom project
# Copyright (c) 2024, Niclas Hallgren
# All rights reserved.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from dataclasses import dataclass, field
import os
import logging
import json5
import re


@dataclass
class IntercomConfig:
    """
    A class to manage intercom configuration settings.
    """
    allow_mic_level_change: bool = False
    audio_level: int = 0
    battery_correction: float = 0.0
    battery_display: str = ''
    battery_shutdown: int = 0
    battery_warning: int = 0
    channel_count: int = 0
    device_type: str = ''
    display_brightness: int = 0
    display_type: str = ''
    encoder_rotation_invert: bool = False
    file_path: str = ''
    font_path: str = ''
    headset: bool = False
    headset_audio_level: int = 0
    lock_buttons: list = field(default_factory=lambda: [False])
    log_file: str = ''
    log_level: str = ''
    log_to_file: bool = False
    log_to_screen: bool = False
    mic_level: int = 0
    mqtt_keepalive: int = 0
    mqtt_pass: str = ''
    mqtt_port: int = 0
    mqtt_prefix: str = ''
    mqtt_server: str = ''
    mqtt_user: str = ''
    multi_talk_delay_ms: int = 0
    network_interface: str = ''
    np_blink_rate_ms: int = 0
    np_brightness: float = 0.0
    np_post_talk_blink_ms: int = 0
    screensaver: bool = False
    screensaver_brightness: int = 0
    screensaver_delay: int = 0
    status_interval_ms: int = 0
    tls_certificate_path: str = ''
    logger: logging.Logger = field(init=False, repr=False)

    def __post_init__(self):
        """Initialize the logger and configuration data."""
        self.logger = logging.getLogger(__name__)
        self._config_data = {}

    def __setattr__(self, key, value):
        """Set attribute and update configuration data."""
        if key != '_config_data' and hasattr(self, '_config_data'):
            self._config_data[key] = value
            self.logger.debug(f"Setting {key} to {value}")
        super().__setattr__(key, value)

    def _update_fields(self, config_data):
        """Update fields with values from configuration data."""
        for field_name, value in config_data.items():
            if hasattr(self, field_name):
                setattr(self, field_name, value)

    def _validate_config(self):
        """Validate configuration values."""
        self.logger.debug("Validating configuration values...")
        # Lock buttons list must have one more than the channel count
        # and the last MUST be False for the encoder to work properly.
        if len(self.lock_buttons) < (self.channel_count + 1):
            self.lock_buttons.extend(
                [False] * ((self.channel_count + 1) - len(self.lock_buttons))
            )
        if not (0 <= self.audio_level <= 150):
            self.logger.error(
                f"Invalid audio_level: {self.audio_level} in config.json5. "
                f"It must be between 0 and 150."
            )
        if not (0 <= self.mic_level <= 150):
            self.logger.error(
                f"Invalid mic_level: {self.mic_level} in config.json5. "
                f"It must be between 0 and 150."
            )
            exit(1)
        is_beltpack = self.device_type == 'beltpack'
        if is_beltpack and self.battery_display not in ['icon', 'mV']:
            self.logger.error(
                f"Invalid battery_display: {self.battery_display} in "
                f"config.json5. It must be 'icon' or 'mV'."
            )
            exit(1)

    def load(self):
        """Load configuration from file."""
        self.logger.debug(f"Loading configuration from {self.file_path}...")
        if not os.path.exists(self.file_path):
            self.logger.error(
                f"Configuration file not found at {self.file_path}. "
                f"Please create the file with the appropriate settings and "
                f"restart the application."
            )
            exit(1)

        with open(self.file_path, 'r') as file:
            config_str = file.read()
            config_data = json5.loads(config_str)
            self._update_fields(config_data)

        self._config_data = config_data
        self._validate_config()
        return self

    def save(self):
        """Save configuration to file with comments."""
        self.logger.debug(f"Saving configuration to {self.file_path}...")
        # Ensure lock_buttons list is not longer than the channel_count
        current_length = len(self._config_data['lock_buttons'])
        if current_length > self.channel_count:
            self._config_data['lock_buttons'] = (
                self._config_data['lock_buttons'][:self.channel_count]
            )

        # Convert the updated configuration back to JSON5 string
        updated_config_str = json5.dumps(self._config_data, indent=4)

        # Load the original configuration as a string
        with open(self.file_path, 'r') as file:
            original_config_str = file.read()

        # Preserve comments by merging the original and updated configurations
        merged_config_str = self._merge_configs(
            original_config_str, updated_config_str)

        # Save the merged configuration back to the file
        with open(self.file_path, 'w') as file:
            file.write(merged_config_str)

    def _merge_configs(self, original, updated):
        """
        Merge the original and updated configuration strings
        while preserving comments and handling multi-line values.
        """
        self.logger.debug("Merging configurations while preserving comments...")

        # Parse updated JSON5 data
        updated_data = json5.loads(updated)

        # Split original into lines for processing
        original_lines = original.splitlines()

        # Regular expression to identify JSON keys (both quoted and unquoted)
        key_re = re.compile(r'^(\s*(?:"[^"]+"|[^:]+)\s*):')

        merged_lines = []
        inside_multiline_value = False
        current_key = None
        buffer = []

        for line in original_lines:
            match = key_re.match(line)

            # If inside a multi-line value (like a list or object), keep buffering
            if inside_multiline_value:
                buffer.append(line)
                if "]" in line or "}" in line:  # Detect end of list/dictionary
                    inside_multiline_value = False
                    if current_key in updated_data:
                        # Replace entire block with the updated value
                        formatted_value = json5.dumps(
                            updated_data[current_key], indent=4, ensure_ascii=False
                        ).replace('\n', '\n    ')
                        merged_lines.append(
                            f"    {current_key}: {formatted_value},"
                        )
                        updated_data.pop(current_key)
                    else:
                        merged_lines.extend(buffer)  # Keep original if unchanged
                continue

            # If it's a key-value pair, check for updates
            if match:
                current_key = match.group(1).strip(": ")

                # Handle multi-line values (lists, objects)
                if line.strip().endswith("[") or line.strip().endswith("{"):
                    inside_multiline_value = True
                    buffer = [line]
                    continue  # Wait until end of multi-line value

                # Replace the line if the key exists in updated data
                if current_key in updated_data:
                    formatted_value = json5.dumps(
                        updated_data[current_key], indent=4, ensure_ascii=False
                    ).replace('\n', '\n    ')
                    merged_lines.append(f"    {current_key}: {formatted_value},")
                    updated_data.pop(current_key)
                    continue  # Skip adding the old line

            # Keep original line (comments, untouched keys)
            merged_lines.append(line)

        # Append any remaining new keys from updated data
        for key, value in updated_data.items():
            formatted_value = json5.dumps(
                value, indent=4, ensure_ascii=False).replace('\n', '\n    ')
            merged_lines.append(f"    {key}: {formatted_value},")

        return "\n".join(merged_lines)