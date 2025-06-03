# This module is part of the HALPIS Intercom project
# Copyright (c) 2024, Niclas Hallgren
# All rights reserved.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import threading
import time
import RPi.GPIO as GPIO
import sys
import logging
from dataclasses import dataclass, field


@dataclass
class IntercomButton:
    """
    Handle button press events using GPIO on Raspberry Pi.

    Attributes:
        pin (int): GPIO pin number for the button.
        num (int): Button number for identification.
        on_button_change (bool | None): Callback for button state changes.
        on_long_press (bool | None): Callback for long press detection.
    """
    pin: int
    num: int
    on_button_change: bool | None = None
    on_long_press: bool | None = None  # Long press callback
    __last_pressed_time: int = field(default=0, init=False)
    _is_locked: bool = field(default=False, init=False)
    __is_pressed: bool = field(default=False, init=False)
    __long_press_detected: bool = field(default=False, init=False)
    buttons_enabled: bool = field(default=False, init=False, repr=False)
    logger: logging.Logger = field(init=False, repr=False)
    _long_press_thread: threading.Thread = field(
        default=None, init=False, repr=False
    )
    _stop_thread: bool = field(default=False, init=False, repr=False)

    def __post_init__(self):
        """Initialize GPIO pin and set up event detection."""
        self.logger = logging.getLogger(__name__)
        try:
            GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            GPIO.add_event_detect(
                self.pin,
                GPIO.BOTH,
                callback=self.__callback,
                bouncetime=100  # Debounce time in milliseconds
            )
            self.logger.debug(
                f"IntercomButton initialized on pin {self.pin} "
                f"for button {self.num}"
            )
        except ValueError as e:
            self.logger.critical(
                f"ValueError: {e} - Invalid pin number {self.pin}"
            )
            sys.exit(1)
        except Exception as e:
            self.logger.critical(f"Unexpected error during GPIO setup: {e}")
            sys.exit(1)

    @property
    def is_locked(self) -> bool:
        """Return the lock state of the button."""
        return self._is_locked

    @is_locked.setter
    def is_locked(self, value: bool) -> None:
        """Update locked state and log the change."""
        if value != self._is_locked:
            self._is_locked = value
            self.logger.debug(
                f"Lock state changed to {self._is_locked} "
                f"for button {self.num}"
            )

    @property
    def is_pressed(self) -> bool:
        """Return the current pressed state of the button."""
        return self.__is_pressed

    @is_pressed.setter
    def is_pressed(self, value: bool) -> None:
        """Update pressed state and invoke the callback."""
        if value != self.__is_pressed:
            self.__is_pressed = value
            self.logger.debug(
                f"Button {self.num} pressed state changed to "
                f"{self.__is_pressed}"
            )
        if self.on_button_change:
            try:
                self.on_button_change(self)
            except Exception as e:
                self.logger.error(f"Error in on_button_change callback: {e}")

    def __callback(self, channel) -> None:
        """Callback triggered when the button is pressed or released."""
        if IntercomButton.buttons_enabled:
            try:
                if GPIO.input(channel) == GPIO.HIGH:
                    self.__last_pressed_time = int(time.time() * 1000)
                    self.is_pressed = True
                    self.__long_press_detected = False
                    self._stop_thread = False
                    self.logger.debug(
                        f"Button {self.num} pressed at "
                        f"{self.__last_pressed_time}"
                    )
                    self._long_press_thread = threading.Thread(
                        target=self._check_long_press
                    )
                    self._long_press_thread.start()
                else:
                    self.__last_released_time = int(time.time() * 1000)
                    if (
                        int(time.time() * 1000) - self.__last_pressed_time
                        < 1000
                    ):
                        self.is_locked = not self.is_locked
                        self.logger.debug(
                            f"Lock state toggled for button {self.num} "
                            f"after press-release cycle."
                        )
                    self.is_pressed = False
                    self._stop_thread = True
                    self.logger.debug(f"Button {self.num} released.")
            except Exception as e:
                self.logger.error(
                    f"Error in callback processing for button {self.num}: {e}"
                )

    def _check_long_press(self) -> None:
        """
        Monitor button press duration to detect long presses.

        A long press is defined as a press lasting more than 1 second.
        """
        while not self._stop_thread:
            current_time = int(time.time() * 1000)
            press_duration = current_time - self.__last_pressed_time
            if press_duration >= 1000 and not self.__long_press_detected:
                self.__long_press_detected = True
                self.logger.debug(
                    f"Button {self.num} held for more than 1 second."
                )
                if self.on_long_press:
                    try:
                        self.on_long_press(self)
                    except Exception as e:
                        self.logger.error(
                            f"Error in on_long_press callback: {e}"
                        )
            time.sleep(0.1)  # Sleep for 100 ms to reduce CPU usage