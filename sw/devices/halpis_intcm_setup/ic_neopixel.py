# This module is part of the HALPIS Intercom project
# Copyright (c) 2024, Niclas Hallgren
# All rights reserved.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import spidev
import logging
from dataclasses import dataclass, field


@dataclass
class IntercomNeopixel:
    """
    Manage NeoPixel LED strip using SPI communication.

    Attributes:
        spibus (int): SPI bus number to use for communication.
        spidevice (int): SPI device number to use for communication.
        count (int): Number of NeoPixels in the strip.
        brightness (int): Brightness level for the NeoPixels (0-1).
        led_pixels (list): List of current colors for each LED pixel.
        __spi (spidev.SpiDev): SPI device instance for communication.
        logger (logging.Logger): Logger for logging events and errors.
    """
    spibus: int
    spidevice: int
    count: int
    brightness: int
    led_pixels: list = field(init=False)
    __spi: spidev.SpiDev = field(init=False, repr=False)
    logger: logging.Logger = field(init=False, repr=False)

    def __post_init__(self):
        """Initialize the SPI device and set up NeoPixel attributes."""
        self.logger = logging.getLogger(__name__)
        self.__spi = spidev.SpiDev()
        try:
            # Open SPI device and set maximum speed
            self.__spi.open(self.spibus, self.spidevice)
            self.__spi.max_speed_hz = 10000000
            self.logger.debug("Initialized SPI device for Neopixels.")
        except OSError as e:
            self.logger.critical(f"OSError: {e} - Unable to open "
                                 f"SPI device.")
            raise
        except ValueError as e:
            self.logger.critical(f"ValueError: {e} - Invalid SPI "
                                 f"configuration.")
            raise
        except PermissionError as e:
            self.logger.critical(
                f"PermissionError: {e} - Permission denied while "
                f"accessing SPI."
            )
            raise
        except Exception as e:
            self.logger.critical(f"Unexpected error: {e}")
            raise

        # Initialize the LED pixels with default color (off)
        self.led_pixels = [self.color(0, 0, 0)] * self.count

        # Define color mappings
        self.colors = {
            "off": self.color(0, 0, 0),
            "red": self.color(int(255 * self.brightness), 0, 0),
            "green": self.color(0, int(255 * self.brightness), 0),
            "blue": self.color(0, 0, int(255 * self.brightness)),
            "yellow": self.color(
                int(255 * self.brightness),
                int(100 * self.brightness),
                0
            ),
            "white": self.color(
                int(255 * self.brightness),
                int(255 * self.brightness),
                int(255 * self.brightness)
            ),
        }

    def close_spi(self):
        """Close the SPI device gracefully."""
        try:
            self.__spi.close()
            self.logger.debug("SPI device closed.")
        except Exception as e:
            self.logger.error(f"Failed to close SPI device: {e}")

    def color(self, r: int, g: int, b: int) -> tuple:
        """Convert R, G, B values to a tuple representation."""
        self.logger.debug(f"Convert colors to tuple")
        return (g, r, b)

    def __send_pixel_data(self, pixels: list[tuple]) -> None:
        """Send pixel data to the LED strip via SPI."""
        self.logger.debug(f"Sending pixel data to LEDs")
        try:
            data = []
            for pixel in pixels:
                for color in pixel:
                    data.extend(self.__spi_color_byte(color))
            self.__spi.xfer2(data)  # Transfer pixel data via SPI
        except OSError as e:
            self.logger.error(f"OSError while sending pixel data: {e}")
        except Exception as e:
            self.logger.error(
                f"Unexpected error while sending pixel data: {e}"
            )

    def __spi_color_byte(self, color: int) -> list:
        """Convert a color byte to the SPI equivalent."""
        self.logger.debug(f"Convert color byte to SPI equivalent")
        byte = []
        for i in range(8):
            if color & (1 << (7 - i)):
                byte.append(0b11111000)  # Bit set (1)
            else:
                byte.append(0b11000000)  # Bit not set (0)
        return byte

    def set_neopixel_color(self, num: int, color: str) -> None:
        """
        Set the color of the NeoPixel at a specific index.

        Args:
            num (int): Index of the NeoPixel to change.
            color (str): Color name to set (e.g., "red", "green").
        """
        self.logger.debug(f"Setting NeoPixel {num} to color {color}")
        if color in self.colors:
            self.led_pixels[num] = self.colors[color]
        else:
            valid_colors = ', '.join(self.colors.keys())
            self.logger.error(
                f"Invalid color '{color}'. Only {valid_colors} are allowed."
            )

        self.__send_pixel_data(self.led_pixels)

    def set_neopixel_off(self, num: int) -> None:
        """
        Turn off the NeoPixel at a specific index.

        Args:
            num (int): Index of the NeoPixel to turn off.
        """
        self.logger.debug(f"Turning off NeoPixel {num}")
        if 0 <= num < self.count:
            self.led_pixels[num] = self.color(0, 0, 0)
            self.__send_pixel_data(self.led_pixels)
        elif num == -1:
            # Turn off all NeoPixels
            for i in range(self.count):
                self.led_pixels[i] = self.color(0, 0, 0)
            self.__send_pixel_data(self.led_pixels)
        else:
            self.logger.error(
                f"Invalid index. Only -1 to {self.count - 1} are allowed."
            )