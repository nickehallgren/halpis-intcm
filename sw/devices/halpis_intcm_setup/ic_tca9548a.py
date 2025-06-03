# This module is part of the HALPIS Intercom project
# Copyright (c) 2024, Niclas Hallgren
# All rights reserved.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import smbus2
import sys
import logging
from dataclasses import dataclass, field


@dataclass
class IntercomTCA9548Multiplexer:
    """
    Manage the TCA9548 I2C multiplexer.

    Attributes:
        i2c_expander_address (int): The I2C address of the multiplexer.
        i2c_port (int): The I2C bus port to use (default is 1).
        mux_ports (list): List of valid multiplexer ports to use.
        __allowed_mux_ports (list): List of allowed port values.
        __bus (smbus2.SMBus): I2C bus instance for communication.
        logger (logging.Logger): Logger for logging events and errors.
    """
    i2c_expander_address: int = 0x70
    i2c_port: int = 1
    mux_ports: list = field(default_factory=list)
    __allowed_mux_ports: list = field(
        default_factory=lambda: [
            0x01, 0x02, 0x80, 0x40, 0x20, 0x10, 0x08, 0x04
        ],
        init=False
    )

    __bus: smbus2.SMBus = field(init=False)
    logger: logging.Logger = field(init=False, repr=False)

    def __post_init__(self):
        """Initialize the I2C bus and validate multiplexer ports."""
        self.logger = logging.getLogger(__name__)
        try:
            self.__bus = smbus2.SMBus(self.i2c_port)
            self.__bus.write_byte(self.i2c_expander_address, 0)
            self.logger.debug("Multiplexer initialized successfully.")
        except OSError as e:
            self.logger.critical(
                f"TCA9548A I2C Multiplexer not found at "
                f"address {hex(self.i2c_expander_address)}: {e}"
            )
            sys.exit(1)

        # Validate and store only the allowed mux_ports
        self.mux_ports = [
            port for port in self.mux_ports if port in self.__allowed_mux_ports
        ]
        if len(self.mux_ports) == 0:
            self.logger.critical("No valid multiplexer ports were provided.")
            sys.exit(1)

    def clear_port(self) -> None:
        """Clear the multiplexer port, deselecting all channels."""
        try:
            self.__bus.write_byte(self.i2c_expander_address, 0)
            self.logger.debug("Cleared the multiplexer port.")
        except OSError as e:
            self.logger.critical(f"Error clearing the multiplexer port: {e}")
            sys.exit(1)

    def get_ports(self) -> list:
        """Return the stored mux_ports."""
        self.logger.debug(f"Current multiplexer ports: {self.mux_ports}")
        return self.mux_ports

    def select_port(self, mux_port: int) -> None:
        """Select the I2C channel on the multiplexer."""
        if mux_port not in self.__allowed_mux_ports:
            self.logger.critical(f"Invalid multiplexer port: {hex(mux_port)}")
            sys.exit(1)

        try:
            self.__bus.write_byte(self.i2c_expander_address, mux_port)
            self.logger.debug(f"Selected multiplexer port: {hex(mux_port)}")
        except OSError as e:
            self.logger.critical(
                f"Error selecting multiplexer port {hex(mux_port)}: {e}"
            )
            sys.exit(1)