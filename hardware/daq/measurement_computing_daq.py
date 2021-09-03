# -*- coding: utf-8 -*-
"""
Qudi-CBS

This file contains a class for the Measurement Computing DAQ.

An extension to Qudi.

@author: F. Barho

Created on Wed June 6 2021
-----------------------------------------------------------------------------------

Qudi is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Qudi is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Qudi. If not, see <http://www.gnu.org/licenses/>.

Copyright (c) the Qudi Developers. See the COPYRIGHT.txt file at the
top-level directory of this distribution and at <https://github.com/Ulm-IQO/qudi/>
-----------------------------------------------------------------------------------
"""
import numpy as np
from time import sleep
from mcculw import ul
from mcculw.enums import ULRange, DigitalIODirection, InterfaceType
from mcculw.ul import ULError
from mcculw.device_info import DaqDeviceInfo

from core.module import Base
from core.configoption import ConfigOption


class MccDAQ(Base):
    """ Class representing the measurement computing DAQ.

    Example config for copy-paste:
        mcc_daq:
            module.Class: 'daq.measurement_computing_daq.MccDAQ'
            rinsing_pump_channel: 0
            fluidics_pump_channel: 1

    """

    # config options
    # ao channels
    rinsing_pump_channel = ConfigOption('rinsing_pump_channel', None, missing='warn')
    fluidics_pump_channel = ConfigOption('fluidics_pump_channel', None, missing='warn')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.board_num = None
        self.port = None

    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)

    def on_activate(self):
        """ Initialization steps when module is called.
        """
        ul.ignore_instacal()
        devices = ul.get_daq_device_inventory(InterfaceType.ANY)
        if not devices:
            raise Exception('Error: No DAQ devices found')

        print('Found', len(devices), 'DAQ device(s):')
        for device in devices:
            print('  ', device.product_name, ' (', device.unique_id, ') - ',
                  'Device ID = ', device.product_id, sep='')

        device = devices[0]
        self.board_num = 0

        # Add the first DAQ device to the UL with the specified board number
        ul.create_daq_device(self.board_num, device)

        self.port = self.get_dio_port()
        print(f'port: {self.port}')

    def on_deactivate(self):
        """ Required deactivation steps.
        """
        ul.release_daq_device(self.board_num)

# ----------------------------------------------------------------------------------------------------------------------
# DAQ utility functions
# ----------------------------------------------------------------------------------------------------------------------

# Get the port
    def get_dio_port(self):
        """ Get the available port from the device and configure it as output port.
        :return: mcculw.device_info.dio_info.PortInfo object """
        daq_dev_info = DaqDeviceInfo(self.board_num)
        if not daq_dev_info.supports_digital_io:
            raise Exception('Error: The DAQ device does not support '
                            'digital I/O')

        dio_info = daq_dev_info.get_dio_info()
        print(f'port_info: {dio_info.port_info}')
        num_ports = dio_info.num_ports
        print(f'num_ports: {num_ports}')

        # Find the first port that supports input, defaulting to None
        # if one is not found.
        port = next((port for port in dio_info.port_info), None)
        if not port:
            raise Exception('Error: The DAQ device does not support '
                            'digital output')

        if port.is_port_configurable:
            ul.d_config_port(self.board_num, port.type, DigitalIODirection.OUT)
            print('port configured as OUT')

        return port

# Analog output channels -----------------------------------------------------------------------------------------------

    def write_to_ao_channel(self, voltage, channel):
        """ Write a voltage to an analog output channel.

        :param: float voltage: target voltage value to apply to the channel
        :param: int channel: number of the addressed channel

        :return: None
        """
        daq_dev_info = DaqDeviceInfo(self.board_num)
        if not daq_dev_info.supports_analog_output:
            raise Exception('Error: The DAQ device does not support '
                            'analog output')
        ao_info = daq_dev_info.get_ao_info()
        print(ao_info.supported_ranges)
        ao_range = ao_info.supported_ranges[0]
        print(ao_range)

        print('Outputting', voltage, 'Volts to channel', channel)
        # Send the value to the device (optional parameter omitted)
        ul.v_out(self.board_num, channel, ao_range, voltage)

# Analog input channels ------------------------------------------------------------------------------------------------
    # no ai channels for this daq
    def read_ai_channel(self, channel):
        """ Read a value from an analog input channel.

        :param: int channel: identifier number of the requested channel

        :return: float data: value read from the ai channel
        """
        daq_dev_info = DaqDeviceInfo(self.board_num)
        if not daq_dev_info.supports_analog_input:
            raise Exception('Error: The DAQ device does not support '
                            'analog input')

# Digital output channels ----------------------------------------------------------------------------------------------
    def set_up_do_channel(self, channel_number):
        """ Define a line in a digital port as output channel.
        :param channel_number: number of the do channel (do line, bit) in the range of the available dio configurable
                            lines, that shall be used for digital output
        :return: None
        """
        # If the bit in the port is configurable, configure it for output.
        if self.port.is_bit_configurable:
            ul.d_config_bit(self.board_num, self.port.type, channel_number, DigitalIODirection.OUT)

    def write_to_do_channel(self, channel, num_samp, digital_write):
        """ Write a value to a digital output channel.
        The channel needs to be configured previously using set_up_do_channel method.

        :param: channel: identifier of the virtual channel (number of the bit / do line in a port)
        :param: int num_samp: number of values to write (one single value here). This argument is needed for
                            compatibility with daq_logic. Set it to 1 when calling the function from logic.
        :param: int digital_write: value to write

        :return: None
        """
        print('Setting', self.port.type.name, channel, 'to', digital_write)
        # Output the value to the channel (bit)
        # ul.d_out(self.board_num, port.type, digital_write)
        ul.d_bit_out(self.board_num, self.port.type, channel, digital_write)

# Digital input channels -----------------------------------------------------------------------------------------------
    def set_up_di_channel(self, channel_number):
        """ Define a line in a digital port as input channel.
        :param channel_number: number of the di channel (di line, bit) in the range of the available dio configurable
                            lines, that shall be used for digital input
        :return: None
        """
        # If the bit in the port is configurable, configure it for output.
        if self.port.is_bit_configurable:
            ul.d_config_bit(self.board_num, self.port.type, channel_number, DigitalIODirection.IN)

    def read_di_channel(self, channel, num_samp=1):
        """ Read a value from a digital input channel.
        The channel needs to be configured previously using set_up_di_channel method.

        :param: channel: identifier of the virtual channel (number of the bit / di line in a port)
        :param: int num_samp: number of values to write (one single value here). This argument is needed for
                            compatibility with daq_logic. Defaults to 1.
        :return: int bit_value: value read from the di line
        """
        bit_value = ul.d_bit_in(self.board_num, self.port.type, channel)
        return bit_value

    def test_function(self):
        self.set_up_do_channel(0)  # configure bit 0 as output
        self.set_up_di_channel(2)  # configure bit 2 as input

# ----------------------------------------------------------------------------------------------------------------------
# Various functionality of DAQ
# ----------------------------------------------------------------------------------------------------------------------

# Needle rinsing pump---------------------------------------------------------------------------------------------------
    def write_to_rinsing_pump_channel(self, voltage):
        """ Start / Stop the needle rinsing pump

        :param: float voltage: target voltage to apply to the channel

        :return: None
        """
        if 0 <= voltage <= 10:  # replace by reading limits from device
            self.write_to_ao_channel(voltage, self.rinsing_pump_channel)
        else:
            self.log.warning('Voltage not in allowed range.')

# Flowcontrol pump------------------------------------------------------------------------------------------------------
    def write_to_fluidics_pump_channel(self, voltage):
        if 0 <= voltage <= 10:  # replace by reading limits from device
            self.write_to_ao_channel(voltage, self.fluidics_pump_channel)
        else:
            self.log.warning('Voltage not in allowed range.')



if __name__ == '__main__':
    mcc_daq = MccDAQ()
    mcc_daq.on_activate()
    # mcc_daq.write_to_ao_channel(0, 0)
    mcc_daq.write_to_pump_ao_channel(1)
    sleep(2)
    mcc_daq.write_to_pump_ao_channel(0)

    mcc_daq.write_to_fluidics_pump_ao_channel(1)
    sleep(2)
    mcc_daq.write_to_fluidics_pump_ao_channel(0)

    mcc_daq.on_deactivate()
    # mcc_daq.config_first_detected_device(0)
    # mcc_daq.read_ai()
    # mcc_daq.read_di()
    # mcc_daq.read_value()
    # mcc_daq.run_example()
    # mcc_daq.digital_in_example()
