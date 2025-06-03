# This module is part of the HALPIS Intercom project
# Copyright (c) 2024, Niclas Hallgren
# All rights reserved.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from dataclasses import dataclass, field
import logging
from ADS1115 import ADS1115


@dataclass
class IntercomADS1115:
    """
    A class to interact with the ADS1115 ADC.

    Attributes:
        address (int): I2C address of the ADS1115.
        ads (ADS1115): Instance of the ADS1115 class.
        logger (logging.Logger): Logger for logging information.
    """
    address: int
    ads: ADS1115 = None
    logger: logging.Logger = field(init=False, repr=False)

    def __post_init__(self):
        """
        Post-initialization to set up the logger and initialize the ADS1115.
        """
        self.logger = logging.getLogger(__name__)
        self.logger.debug(
            f"Initializing ADS1115 at address {hex(self.address)}")
        # Initialize the ADS1115 instance with the provided address
        self.ads = ADS1115(address=self.address)

    def measure_voltage(
        self, channel: int = 0, battery_correction: float = 3.15
    ) -> int:
        """
        Measure the voltage from a specified channel.

        Args:
            channel (int): The ADC channel to read from (default is 0).
            battery_correction (float): Correction factor for the battery.

        Returns:
            int: The measured voltage in millivolts.
        """
        self.logger.debug(f"Measuring voltage on channel {channel}")
        try:
            voltage = int(self.ads.readADCSingleEnded() * battery_correction)
            self.logger.info(f"Measured voltage: {voltage} mV")
            return voltage
        except Exception as e:
            self.logger.error(f"Error measuring voltage: {e}")
            return None
