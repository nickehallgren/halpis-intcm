# This module is part of the HALPIS Intercom project
# Copyright (c) 2024, Niclas Hallgren
# All rights reserved.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306, sh1106
from PIL import ImageFont
import logging
from typing import List
from dataclasses import dataclass, field
import random


@dataclass
class IntercomDisplay:
    """
    A class to manage and update text on an OLED display (SSD1306 or SH1106)
    over I2C.

    Attributes:
        num (int): Identifier for the display.
        i2c_address (int): I2C address for the OLED display. Defaults to 0x3c.
        i2c_port (int): I2C port number. Defaults to 1.
        width (int): Width of the display in pixels.
        height (int): Height of the display in pixels.
        rotate (int): Rotation of the display. Defaults to 0.
        display_type (str): Type of OLED display controller ('ssd1306' or
                            'sh1106').
        text (str): Current text displayed on the screen. Defaults to an empty
                    string.
        update_freeze (bool): Whether the display is frozen for updates.
                              Defaults to False.
        update_freeze_time_ms (int): Time in milliseconds to freeze updates.
                                     Defaults to 1500.
        update_freeze_start (int): Timestamp when the freeze started. Defaults
                                   to 0.
    """

    num: int
    width: int
    height: int
    display_type: str
    i2c_address: int = 0x3c
    i2c_port: int = 1
    display_brightness: int = 255
    rotate: int = 0
    text: str = ""
    text_split: int = 0
    last_audio_level: int = 0
    last_battery_level: int = 0
    last_battery_voltage: int = 0
    last_text: str = ""
    last_text_split: int = 0
    update_freeze: bool = False
    update_freeze_time_ms: int = 1500
    update_freeze_start: int = 0

    __device: object = field(init=False)
    __last_low_bat: int = field(default=0, init=False, repr=False)
    logger: logging.Logger = field(init=False, repr=False)

    def __post_init__(self):
        """
        Initialize the OLED display based on the selected display type
        and configure logging. This method is called automatically after
        the dataclass initialization.
        """
        self.logger = logging.getLogger(__name__)
        try:
            self.__serial = i2c(port=self.i2c_port, address=self.i2c_address)

            if self.display_type.lower() == 'ssd1306':
                self.__device = ssd1306(
                    self.__serial,
                    width=self.width,
                    height=self.height,
                    rotate=self.rotate,
                )
                self.logger.debug(
                    f"SSD1306 display initialized at I2C address: "
                    f"{hex(self.i2c_address)}"
                )
            elif self.display_type.lower() == 'sh1106':
                self.__device = sh1106(
                    self.__serial,
                    width=self.width,
                    height=self.height,
                    rotate=self.rotate,
                )
                self.__device.cleanup = self.do_nothing
                self.logger.debug(
                    f"SH1106 display initialized at I2C address: "
                    f"{hex(self.i2c_address)}"
                )
            else:
                raise ValueError(
                    "Unsupported display type. Use 'ssd1306' or 'sh1106'."
                )
            self.set_brightness(self.display_brightness)

        except Exception as e:
            self.logger.critical(f"Failed to initialize display: {e}")
            raise

    def set_brightness(self, level: int) -> None:
        """
        Set the brightness level of the OLED display.

        Args:
            level (int): Brightness level (0-255).
        """
        self.logger.debug(f"Setting display brightness to {level}")
        try:
            self.__device.contrast(level)
        except Exception as e:
            self.logger.error(f"Error setting brightness: {e}")

    def do_nothing(self, obj: object) -> None:
        """ Function to override display cleanup"""
        pass

    def __get_text_size(self, draw: object, text: str, font: str) -> dict:
        """
        Calculate the width and height of the given text in pixels using
        the provided font.

        Args:
            draw (object): The canvas draw object.
            text (str): The text to measure.
            font (str): The font to use for measuring.

        Returns:
            dict: A dictionary with the keys 'width' and 'height'
                  representing the pixel dimensions of the text.
        """
        self.logger.debug(f"Measuring text size: {text}")
        text_left, text_top, text_right, text_bottom = draw.textbbox(
            (0, 0), text, font=font
        )
        textwidth, textheight = text_right - text_left, text_bottom - text_top
        return {'width': textwidth, 'height': textheight}

    def render_text(self, text: str, font_path: str, font_size: int) -> None:
        """
        Render the provided text on the OLED display.

        Args:
            text (str): The text to display.
            font_path (str): The path to the TrueType font file.
            font_size (int): The font size to be used.
        """
        self.logger.debug(f"Rendering text: {text}")
        self.set_brightness(self.display_brightness)
        try:
            self.text = text
            with canvas(self.__device) as draw:
                font = ImageFont.truetype(font_path, font_size)
                text_size = self.__get_text_size(draw, text, font)
                y_offset = 4 if font.size == 14 else 2
                x = int(64 - text_size["width"] / 2)
                y = int(8 - text_size["height"] / 2) + y_offset
                draw.text((x, y), text, font=font, fill=255)
        except Exception as e:
            self.logger.error(f"Error updating text on display: {e}")

    def render_text_lines(
        self, lines: List[str], font_path: str, font_size: int
    ) -> None:
        """
        Render multiple lines of text on the OLED display.

        Args:
            lines (List[str]): The text for each line.
            font_path (str): The path to the TrueType font file.
            font_size (int): The font size to be used.
        """
        self.logger.debug(f"Rendering text lines: {lines}")
        self.set_brightness(self.display_brightness)
        try:
            self.text = lines[0] if lines else ""
            with canvas(self.__device) as draw:
                font = ImageFont.truetype(font_path, font_size)

                for i, line in enumerate(lines):
                    text_size = self.__get_text_size(draw, line, font)
                    x = int(64 - text_size["width"] / 2)
                    y = 5 + (i * 20)
                    draw.text((x, y), line, font=font, fill=255)
        except Exception as e:
            self.logger.error(f"Error rendring text on display: {e}")

    def render_screensaver(
        self, screensaver_brightness: int, user: str, font_path: str
    ) -> None:
        """
        Render screensaver text on the OLED display.

        Args:
            screensaver_brightness (int): Brightness level for the screensaver.
            user (str): The text to display.
            font_path (str): The path to the TrueType font file.
        """
        self.logger.debug(f"Rendering screensaver: {user}")
        self.set_brightness(screensaver_brightness)
        with canvas(self.__device) as draw:
            font_size = 20
            font = ImageFont.truetype(font_path, font_size)
            text_size = self.__get_text_size(draw, user, font)
            text_width = text_size["width"]
            text_height = font_size
            sc_x = random.randint(0, self.width - text_width)
            sc_y = random.randint(0, self.height - text_height)
            draw.text((sc_x, sc_y), user, font=font, fill=255)

    def render_main_view(
        self,
        volume: str,
        device_type: str,
        battery_display: str,
        battery_voltage: int,
        low_batt: int,
        user: str,
        ip: str,
        font_path: str,
    ) -> None:
        """
        Render the main view on the OLED display.

        Args:
            volume (str): Volume level.
            device_type (str): Type of device (basestation or beltpack).
            battery_display (str): Type of battery display (icon or mV).
            battery_voltage (int): Current battery voltage.
            low_batt (int): Low battery indicator.
            user (str): User name.
            ip (str): IP address.
            font_path (str): The path to the TrueType font file.
        """
        self.logger.debug(f"Rendering main view")
        self.set_brightness(self.display_brightness)
        if device_type == 'basestation':
            pass
        elif device_type == 'beltpack':
            try:
                with canvas(self.__device) as draw:
                    font = ImageFont.truetype(font_path, 16)
                    draw.text((2, 0), "V" + volume + "%", font=font, fill=255)

                    if battery_display == 'icon':
                        draw.rectangle((123, 6, 126, 11), outline=1, fill=1)
                        draw.rectangle((63, 2, 123, 15), outline=1, fill=0)

                        if low_batt:
                            if self.__last_low_bat == 0:
                                self.__last_low_bat = 1
                                font = ImageFont.truetype(font_path, 10)
                                draw.text((73, 4), "LOW BAT", font=font,
                                          fill=255)
                            else:
                                self.__last_low_bat = 0
                                font = ImageFont.truetype(font_path, 10)
                                draw.text((73, 4), "", font=font, fill=255)
                        else:
                            if battery_voltage >= 6700:
                                draw.rectangle((65, 4, 75, 13), outline=1,
                                               fill=1)
                            if battery_voltage >= 7025:
                                draw.rectangle((77, 4, 86, 13), outline=1,
                                               fill=1)
                            if battery_voltage >= 7350:
                                draw.rectangle((88, 4, 98, 13), outline=1,
                                               fill=1)
                            if battery_voltage >= 7675:
                                draw.rectangle((100, 4, 110, 13), outline=1,
                                               fill=1)
                            if battery_voltage >= 8000:
                                draw.rectangle((112, 4, 121, 13), outline=1,
                                               fill=1)
                    elif battery_display == 'mV':
                        if low_batt:
                            if self.__last_low_bat == 0:
                                self.__last_low_bat = 1
                                font = ImageFont.truetype(font_path, 16)
                                draw.text((58, 0), "LOW BAT", font=font,
                                          fill=255)
                            else:
                                self.__last_low_bat = 0
                                font = ImageFont.truetype(font_path, 16)
                                draw.text((68, 0), str(battery_voltage) + "mV",
                                          font=font, fill=255)
                        else:
                            font = ImageFont.truetype(font_path, 16)
                            draw.text((68, 0), str(battery_voltage) + "mV",
                                      font=font, fill=255)

                    font = ImageFont.truetype(font_path, 26)
                    text_size = self.__get_text_size(draw, user, font)
                    x = int(64 - text_size["width"] / 2)
                    draw.text((x, 20), user, font=font, fill=255)

                    font = ImageFont.truetype(font_path, 14)
                    text_size = self.__get_text_size(draw, ip, font)
                    x = int(64 - text_size["width"] / 2)
                    draw.text((x, 51), ip, font=font, fill=255)
            except Exception as e:
                self.logger.error(f"Error drawing main view: {e}")

    def render_talk_view(
        self, volume: str, talk_to: str, ip: str, font_path: str
    ) -> None:
        """
        Render the talk view on the display.

        Args:
            volume (str): Volume level.
            talk_to (str): User to talk to.
            ip (str): IP address.
            font_path (str): The path to the TrueType font file.
        """
        self.logger.debug(f"Rendering talk view")
        self.set_brightness(self.display_brightness)
        try:
            with canvas(self.__device) as draw:
                font = ImageFont.truetype(font_path, 16)
                draw.text((2, 0), "V" + volume + "%", font=font, fill=255)

                font = ImageFont.truetype(font_path, 16)
                draw.text((60, 0), "TALK TO", font=font, fill=255)

                font = ImageFont.truetype(font_path, 26)
                text_size = self.__get_text_size(draw, talk_to, font)
                x = int(64 - text_size["width"] / 2)
                draw.text((x, 20), talk_to, font=font, fill=255)

                font = ImageFont.truetype(font_path, 14)
                text_size = self.__get_text_size(draw, ip, font)
                x = int(64 - text_size["width"] / 2)
                draw.text((x, 51), ip, font=font, fill=255)
        except Exception as e:
            self.logger.error(f"Error drawing main beltpack view: {e}")

    def get_max_text_lines(self, font_path: str, font_size: int) -> int:
        """
        Calculate the maximum number of lines that can fit on the display
        based on the font size and height.

        Args:
            font_path (str): The path to the TrueType font file.
            font_size (int): The font size to be used.

        Returns:
            int: The maximum number of lines that can fit on the display.
        """
        self.logger.debug(f"Calculating max text lines")
        with canvas(self.__device) as draw:
            font = ImageFont.truetype(font_path, font_size)
            text_size = self.__get_text_size(draw, "A", font)
            text_size["height"] += 4
            return self.height // text_size["height"]

    def update_menu(
        self, lines: list, active_line: int, max_lines: int, font_path: str,
        font_size: int
    ) -> None:
        """
        Update the display with a multi-line menu, highlighting the active
        line.

        Args:
            lines (list): The list of text lines to be displayed.
            active_line (int): Indicates which line is active (0-based index).
            font_path (str): The path to the TrueType font file.
            font_size (int): The font size to be used.
        """
        self.logger.debug(f"Updating menu")
        self.set_brightness(self.display_brightness)
        try:
            self.text = lines[0] if lines else ""
            add_height = 4
            with canvas(self.__device) as draw:
                font = ImageFont.truetype(font_path, font_size)
                text_size = self.__get_text_size(draw, "A", font)
                text_size["height"] += add_height

                for i, line in enumerate(lines[:max_lines]):
                    text_size = self.__get_text_size(draw, line, font)
                    x = int((self.width - text_size["width"]) / 2)
                    y = i * (text_size["height"] + add_height)

                    if i == active_line:
                        draw.rectangle(
                            (0, y, self.width, y + (text_size["height"] +
                                                    add_height)),
                            outline=0,
                            fill=255,
                        )
                        draw.text((x, y), line, font=font, fill=0)
                    else:
                        draw.text((x, y), line, font=font, fill=255)
        except Exception as e:
            self.logger.error(f"Error updating menu on display: {e}")

    def clear_display(self) -> None:
        """
        Clears the OLED display.
        """
        self.logger.debug(f"Clearing display")
        try:
            self.__device.clear()
        except Exception as e:
            self.logger.error(f"Error clearing display: {e}")