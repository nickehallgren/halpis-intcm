# This module is part of the HALPIS Intercom project
# Copyright (c) 2024, Niclas Hallgren
# All rights reserved.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import RPi.GPIO as GPIO
import logging
from dataclasses import dataclass, field

# Set the GPIO mode to use the physical pin numbering
GPIO.setmode(GPIO.BOARD)


@dataclass
class IntercomEncoder:
    """
    Handle rotary encoder input using GPIO on Raspberry Pi.
    
    Attributes:
        leftPin (int): GPIO pin connected to the left signal of the encoder.
        rightPin (int): GPIO pin connected to the right signal of the encoder.
        callback (function): Function to call when the encoder value changes.
        value (int): The current value of the encoder.
        state (str): The current state of the encoder's signals.
        direction (str): The direction of the last detected movement 
        ("R" or "L").
    """
    leftPin: int
    rightPin: int
    callback: any = None  # No strict typing for callback, allows any callable
    value: int = 0
    state: str = field(default="00", init=False)
    direction: str = field(default=None, init=False)

    logger: logging.Logger = field(init=False, repr=False)

    def __post_init__(self):
        """
        Initialize the GPIO pins for the encoder and set up event detection
        for both pins. Log any errors encountered during setup.
        """
        self.logger = logging.getLogger(__name__)
        try:
            # Setup the GPIO pins with pull-up resistors and event detection
            self.logger.debug(
                f"Setting up GPIO pins: leftPin={self.leftPin}, "
                f"rightPin={self.rightPin}"
            )
            GPIO.setup(self.leftPin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            GPIO.setup(self.rightPin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

            # Add event detection for both left and right pins
            GPIO.add_event_detect(
                self.leftPin, GPIO.BOTH, callback=self.transitionOccurred
            )
            GPIO.add_event_detect(
                self.rightPin, GPIO.BOTH, callback=self.transitionOccurred
            )

            # Read the initial state of the encoder's pins
            initial_p1 = GPIO.input(self.leftPin)
            initial_p2 = GPIO.input(self.rightPin)
            self.state = f"{initial_p1}{initial_p2}"
            self.logger.debug(f"Initial encoder state: {self.state}")

            self.logger.debug("GPIO pins set up successfully")

        except ValueError as e:
            # Handle invalid GPIO pin numbers
            self.logger.error(f"Invalid GPIO pin numbers: {e}")
            raise

        except RuntimeError as e:
            # Handle issues related to GPIO setup, such as 
            # lack of initialization
            self.logger.error(f"GPIO setup error: {e}")
            raise

        except Exception as e:
            # Catch-all for any other exceptions during setup
            self.logger.error(f"Unexpected error during GPIO setup: {e}")
            raise

    def getValue(self):
        """
        Retrieve the current value of the encoder and log the retrieval.
        
        Returns:
            int: The current value of the encoder.
        """
        self.logger.debug(f"Getting value: {self.value}")
        return self.value

    def transitionOccurred(self, _):
        """
        Called when a GPIO pin state change is detected. Updates the encoder's
        state and checks for valid transitions to determine the direction of
        rotation. Logs detected transitions and updates the value accordingly.
        
        Args:
            _ (int): Ignored argument, required by GPIO callback interface.
        """
        # Read the current state of the left and right encoder pins
        p1 = GPIO.input(self.leftPin)
        p2 = GPIO.input(self.rightPin)
        newState = f"{p1}{p2}"

        self.logger.debug(
            f"Transition occurred: newState={newState}, oldState={self.state}"
        )

        # Define valid transitions for right (clockwise) 
        # and left (counterclockwise)
        valid_right = [
            ("00", "01"), ("01", "11"), ("11", "10"), ("10", "00")
        ]
        valid_left = [
            ("00", "10"), ("10", "11"), ("11", "01"), ("01", "00")
        ]

        if (self.state, newState) in valid_right:
            # Right (clockwise) rotation detected
            self.direction = "R"
            self.logger.debug("Detected Right movement")
            if newState == "00":
                # Full right movement completed
                self.logger.debug("Right movement complete")
                self.updateValue(1)

        elif (self.state, newState) in valid_left:
            # Left (counterclockwise) rotation detected
            self.direction = "L"
            self.logger.debug("Detected Left movement")
            if newState == "00":
                # Full left movement completed
                self.logger.debug("Left movement complete")
                self.updateValue(-1)

        else:
            # Invalid or noisy transition, ignore it
            self.logger.debug(
                f"Invalid transition: {self.state} -> {newState}, ignoring"
            )

        # Update the encoder's state
        self.state = newState

    def updateValue(self, delta):
        """
        Update the encoder's value by the specified delta and invoke the 
        callback if provided. Logs the value update and any errors in 
        the callback execution.
        
        Args:
            delta (int): The change to apply to the encoder's value.
        """
        # Update the value and log the change
        self.logger.debug(
            f"Updating value: current={self.value}, delta={delta}"
        )
        self.value += delta
        self.logger.debug(f"New value: {self.value}")

        # Call the callback function if provided
        if self.callback:
            self.logger.debug(
                f"Calling callback with value={self.value} "
                f"and direction={self.direction}"
            )
            try:
                self.callback(self.value, self.direction)
            except Exception as e:
                # Log any exceptions raised during callback execution
                self.logger.warning(f"Error during callback: {e}")