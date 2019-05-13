# -*- coding: utf-8 -*-
"""
This module operates a confocal microsope.

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
"""

from qtpy import QtCore
from collections import OrderedDict
from itertools import combinations
import time
import datetime
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt

from logic.generic_logic import GenericLogic
from core.util.mutex import Mutex
from core.module import Connector, ConfigOption, StatusVar


class ScanData:
    """

    """
    def __init__(self, scan_axes, channel_config, scanner_settings):
        self._scan_axes = tuple(scan_axes)
        if self._scan_axes not in scanner_settings['scan_axes']:
            raise ValueError('scan_axes must be tuple of axes name strings contained in '
                             'scanner_settings')
        self._target_ranges = tuple(scanner_settings['scan_range'][ax] for ax in self._scan_axes)
        self._resolution = tuple(scanner_settings['scan_resolution'][ax] for ax in self._scan_axes)
        self._channel_names = tuple(channel_config)
        self._channel_units = {ch: ch_dict['unit'] for ch, ch_dict in channel_config.items()}
        self.__available_axes = tuple(scanner_settings['scan_resolution'])
        self._position_data = {ax: np.zeros((*self._resolution,)) for ax in self.__available_axes}
        self._data = {ch: np.zeros((*self._resolution,)) for ch in self._channel_names}
        # TODO: Automatic interpolation onto regular grid needs to be implemented
        return

    @property
    def scan_axes(self):
        return self._scan_axes

    @property
    def target_ranges(self):
        return self._target_ranges

    @property
    def resolution(self):
        return self._resolution

    @property
    def channel_names(self):
        return self._channel_names

    @property
    def channel_units(self):
        return self._channel_units

    @property
    def data(self):
        return self._data

    @property
    def position_data(self):
        return self._position_data

    def new_data(self):
        self._position_data = {ax: np.zeros((*self.resolution,)) for ax in self.__available_axes}
        self._data = {ch: np.zeros((*self.resolution,)) for ch in self.channel_names}
        return

    def add_line_data(self, position, data, y_index=None, x_index=None):
        """

        @param dict data:
        @param int y_index:
        @param int x_index:
        """
        if x_index is None and y_index is None:
            raise ValueError('Must pass either x_index or y_index to add line data.')

        if set(position) != set(self.__available_axes):
            raise ValueError('position dict must contain all available axes {0}.'
                             ''.format(self.__available_axes))
        if set(data) != set(self.channel_names):
            raise ValueError('data dict must contain all available data channels {0}.'
                             ''.format(self.channel_names))
        for arr in position.values():
            if y_index is None and arr.size != self.resolution[1]:
                raise ValueError('Size of line position data array must be {0} but is {1}'
                                 ''.format(self.resolution[1], arr.size))
            if x_index is None and arr.size != self.resolution[0]:
                raise ValueError('Size of line position data array must be {0} but is {1}'
                                 ''.format(self.resolution[0], arr.size))
        for arr in data.values():
            if y_index is None and arr.size != self.resolution[1]:
                raise ValueError('Size of line data array must be {0} but is {1}'
                                 ''.format(self.resolution[1], arr.size))
            if x_index is None and arr.size != self.resolution[0]:
                raise ValueError('Size of line data array must be {0} but is {1}'
                                 ''.format(self.resolution[0], arr.size))

        for channel, arr in data.items():
            if y_index is None:
                self._data[channel][int(x_index), :] = arr
            elif x_index is None:
                self._data[channel][:, int(y_index)] = arr

        for axis, arr in position.items():
            if y_index is None:
                self._position_data[axis][int(x_index), :] = arr
            elif x_index is None:
                self._position_data[axis][:, int(y_index)] = arr
        return


class ConfocalLogic(GenericLogic):
    """
    This is the Logic class for confocal scanning.
    """
    _modclass = 'confocallogic'
    _modtype = 'logic'

    # declare connectors
    confocalscanner1 = Connector(interface='ConfocalScannerInterface')
    savelogic = Connector(interface='SaveLogic')

    # status vars
    _clock_frequency = StatusVar('clock_frequency', 500)
    return_slowness = StatusVar(default=50)
    max_history_length = StatusVar(default=10)

    # signals
    sigScanStateChanged = QtCore.Signal(bool, tuple)
    sigScannerPositionChanged = QtCore.Signal(dict, object)
    sigScannerTargetChanged = QtCore.Signal(dict, object)
    sigScannerSettingsChanged = QtCore.Signal(dict)
    sigOptimizerSettingsChanged = QtCore.Signal(dict)
    sigScanDataChanged = QtCore.Signal(dict)

    __sigNextLine = QtCore.Signal()

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

        self.threadlock = Mutex()

        # Create semi-random dummy constraints
        self._constraints = dict()
        self._constraints['data_channels'] = dict()
        self._constraints['data_channels']['fluorescence'] = dict()
        self._constraints['data_channels']['fluorescence']['unit'] = 'c/s'
        self._constraints['data_channels']['unfug'] = dict()
        self._constraints['data_channels']['unfug']['unit'] = 'bpm'
        self._constraints['axes'] = dict()
        for axis in ('x', 'y', 'z', 'phi'):
            self._constraints['axes'][axis] = dict()
            limit = 50e-6 + 50e-6 * np.random.rand()
            self._constraints['axes'][axis]['min_value'] = -limit
            self._constraints['axes'][axis]['max_value'] = limit
            self._constraints['axes'][axis]['min_step'] = 1e-9
            self._constraints['axes'][axis]['min_resolution'] = 2
            self._constraints['axes'][axis]['max_resolution'] = np.inf
            self._constraints['axes'][axis]['unit'] = 'm' if axis != 'phi' else '°'

        # scanner settings
        self._scanner_settings = dict()
        self._scanner_settings['scan_axes'] = tuple(combinations(self.scanner_constraints['axes'],
                                                                 2))
        self._scanner_settings['pixel_clock_frequency'] = 1000
        self._scanner_settings['backscan_points'] = 50
        self._scanner_settings['scan_resolution'] = dict()
        self._scanner_settings['scan_range'] = dict()
        for axis, constr_dict in self._constraints['axes'].items():
            self._scanner_settings['scan_resolution'][axis] = np.random.randint(
                max(constr_dict['min_resolution'], 100),
                min(constr_dict['max_resolution'], 400) + 1)
            self._scanner_settings['scan_range'][axis] = (constr_dict['min_value'],
                                                          constr_dict['max_value'])

        # Scanner target position
        self._target = dict()
        for axis, axis_dict in self.scanner_constraints['axes'].items():
            extent = axis_dict['max_value'] - axis_dict['min_value']
            self._target[axis] = axis_dict['min_value'] + extent * np.random.rand()

        # Optimizer settings
        self._optimizer_settings = dict()
        self._optimizer_settings['settle_time'] = 0.1
        self._optimizer_settings['pixel_clock'] = 50
        self._optimizer_settings['backscan_pts'] = 20
        self._optimizer_settings['sequence'] = ('xy', 'z')
        self._optimizer_settings['axes'] = dict()
        self._optimizer_settings['axes']['x'] = {'resolution': 15, 'range': 1e-6}
        self._optimizer_settings['axes']['y'] = {'resolution': 15, 'range': 1e-6}
        self._optimizer_settings['axes']['z'] = {'resolution': 15, 'range': 1e-6}
        self._optimizer_settings['axes']['phi'] = {'resolution': 15, 'range': 1e-6}

        # Scan data buffer
        self._current_dummy_data = None
        self._scan_data = dict()
        for axes in self._scanner_settings['scan_axes']:
            self._scan_data[tuple(axes)] = ScanData(
                scan_axes=axes,
                channel_config=self.scanner_constraints['data_channels'],
                scanner_settings=self.scanner_settings)
            self._scan_data[tuple(axes)].new_data()

        # others
        self.__timer = None
        self.__scan_line_count = 0
        self.__running_scan = None
        self.__scan_start_time = 0
        self.__scan_line_interval = None
        self.__scan_line_positions = dict()
        self.__scan_stop_requested = True
        return

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self.__timer = QtCore.QTimer()
        self.__timer.setInterval(500)
        self.__timer.setSingleShot(False)
        self.__timer.timeout.connect(self.notify_scanner_position_change)
        self.__timer.start()

        self.__scan_line_count = 0
        self.__running_scan = None
        self.__scan_start_time = time.time()
        self.__scan_line_interval = None
        self.__scan_stop_requested = True
        self.__sigNextLine.connect(self._scan_loop, QtCore.Qt.QueuedConnection)
        return

    def on_deactivate(self):
        """ Reverse steps of activation
        """
        self.__timer.stop()
        self.__timer.timeout.disconnect()
        self.__sigNextLine.disconnect()
        return

    @property
    def scan_data(self):
        return self._scan_data.copy()

    @property
    def scanner_position(self):
        pos = dict()
        for axis, value in self._target.items():
            axis_range = abs(
                self._constraints['axes'][axis]['max_value'] - self._constraints['axes'][axis][
                    'min_value'])
            pos[axis] = value + (np.random.rand() - 0.5) * axis_range * 0.01
        return pos

    @property
    def scanner_target(self):
        return self._target.copy()

    @property
    def scanner_axes_names(self):
        return tuple(self.scanner_constraints['axes'])

    @property
    def scanner_constraints(self):
        return self._constraints.copy()

    @property
    def scanner_settings(self):
        return self._scanner_settings.copy()

    @property
    def optimizer_settings(self):
        return self._optimizer_settings.copy()

    @QtCore.Slot(dict)
    def set_scanner_settings(self, settings):
        if 'scan_axes' in settings:
            for axes in settings['scan_axes']:
                if not (0 < len(axes) < 3):
                    self.log.error('Scan_axes must contain only tuples of len 1 or 2.')
                    return
                for axis in axes:
                    if axis not in self._constraints['axes']:
                        self.log.error('Axis "{0}" is no valid axis for scanner.'.format(axis))
                        return
            self._scanner_settings['scan_axes'] = tuple(settings['scan_axes'])
        if 'pixel_clock_frequency' in settings:
            if settings['pixel_clock_frequency'] < 1:
                self.log.error('Pixel clock frequency must be integer number >= 1.')
                return
            self._scanner_settings['pixel_clock_frequency'] = int(settings['pixel_clock_frequency'])
        if 'backscan_points' in settings:
            if settings['backscan_points'] < 1:
                self.log.error('Backscan points must be integer number >= 1.')
                return
            self._scanner_settings['backscan_points'] = int(settings['backscan_points'])
        if 'scan_resolution' in settings:
            for axis, res in settings['scan_resolution'].items():
                if axis not in self._constraints['axes']:
                    self.log.error('Axis "{0}" is no valid axis for scanner.'.format(axis))
                    return
                if res < self._constraints['axes'][axis]['min_resolution']:
                    self.log.error('Resolution to set not within allowed boundaries.')
                    return
                elif res > self._constraints['axes'][axis]['max_resolution']:
                    self.log.error('Resolution to set not within allowed boundaries.')
                    return
            self._scanner_settings['scan_resolution'].update(settings['scan_resolution'])
        if 'scan_range' in settings:
            for axis, range in settings['scan_range'].items():
                if axis not in self._constraints['axes']:
                    self.log.error('Axis "{0}" is no valid axis for scanner.'.format(axis))
                    return
                if min(range) < self._constraints['axes'][axis]['min_value']:
                    self.log.error('Scan range to set not within allowed boundaries.')
                    return
                elif max(range) > self._constraints['axes'][axis]['max_value']:
                    self.log.error('Resolution to set not within allowed boundaries.')
                    return
            self._scanner_settings['scan_range'].update(settings['scan_range'])
        self.sigScannerSettingsChanged.emit(self.scanner_settings)
        return

    @QtCore.Slot(dict)
    def set_optimizer_settings(self, settings):
        if 'axes' in settings:
            for axis, axis_dict in settings['axes'].items():
                self._optimizer_settings['axes'][axis].update(axis_dict)
        if 'settle_time' in settings:
            if settings['settle_time'] < 0:
                self.log.error('Optimizer settle time must be positive number.')
            else:
                self._optimizer_settings['settle_time'] = float(settings['settle_time'])
        if 'pixel_clock' in settings:
            if settings['pixel_clock'] < 1:
                self.log.error('Optimizer pixel clock must be integer number >= 1.')
            else:
                self._optimizer_settings['pixel_clock'] = int(settings['pixel_clock'])
        if 'backscan_pts' in settings:
            if settings['backscan_pts'] < 1:
                self.log.error('Optimizer backscan points must be integer number >= 1.')
            else:
                self._optimizer_settings['backscan_pts'] = int(settings['backscan_pts'])
        if 'sequence' in settings:
            self._optimizer_settings['sequence'] = tuple(settings['sequence'])

        self.sigOptimizerSettingsChanged.emit(self.optimizer_settings)
        return

    @QtCore.Slot(dict)
    @QtCore.Slot(dict, object)
    def set_scanner_target_position(self, pos_dict, caller_id=None):
        constr = self.scanner_constraints
        for ax, pos in pos_dict.items():
            if ax not in constr['axes']:
                self.log.error('Unknown scanner axis: "{0}"'.format(ax))
                return

        self._target.update(pos_dict)
        self.sigScannerTargetChanged.emit(pos_dict, id(self) if caller_id is None else caller_id)
        time.sleep(0.01)
        self.notify_scanner_position_change()
        return

    @QtCore.Slot()
    def notify_scanner_position_change(self):
        self.sigScannerPositionChanged.emit(self.scanner_position, id(self))

    @QtCore.Slot(tuple, bool)
    def toggle_scan(self, scan_axes, start):
        print(scan_axes)
        with self.threadlock:
            if start and self.module_state() != 'idle':
                self.log.error('Unable to start scan. Scan already in progress.')
                return
            elif not start and self.module_state() == 'idle':
                self.log.error('Unable to stop scan. No scan running.')
                return

            if start:
                self.module_state.lock()
                self.__timer.stop()
                self.__running_scan = scan_axes
                self.sigScanStateChanged.emit(True, self.__running_scan)
                self._current_dummy_data = self._generate_2d_dummy_data(scan_axes)
                self.__scan_line_count = 0
                self.__scan_start_time = time.time()
                self._scan_data[self.__running_scan] = ScanData(
                    scan_axes=self.__running_scan,
                    channel_config=self.scanner_constraints['data_channels'],
                    scanner_settings=self.scanner_settings)
                self._scan_data[self.__running_scan].new_data()
                num_x_vals = self.scanner_settings['scan_resolution'][scan_axes[0]]
                self.__scan_line_interval = num_x_vals / self.scanner_settings[
                    'pixel_clock_frequency']
                self.__scan_line_positions = {ax: np.full(num_x_vals, self.scanner_target[ax]) for
                                              ax in self._constraints['axes']}
                min_val, max_val = self.scanner_settings['scan_range'][self.__running_scan[0]]
                self.__scan_line_positions[self.__running_scan[0]] = np.linspace(min_val,
                                                                                 max_val,
                                                                                 num_x_vals)
                self.__scan_stop_requested = False
                self.__sigNextLine.emit()
            else:
                self.__scan_stop_requested = True
        return

    @QtCore.Slot()
    def _scan_loop(self):
        if self.module_state() != 'locked':
            return

        with self.threadlock:
            max_number_of_lines = self.scanner_settings['scan_resolution'][self.__running_scan[1]]
            if self.__scan_line_count >= max_number_of_lines or self.__scan_stop_requested:
                self.module_state.unlock()
                self.sigScanStateChanged.emit(False, self.__running_scan)
                self.__timer.start()
                return

            y_min, y_max = self.scanner_settings['scan_range'][self.__running_scan[1]]
            self.__scan_line_positions[self.__running_scan[1]] = np.full(
                self.scanner_settings['scan_resolution'][self.__running_scan[0]],
                y_min + (y_max - y_min) / (max_number_of_lines - 1))

            self.__scan_line_count += 1
            next_line_time = self.__scan_start_time + self.__scan_line_count * self.__scan_line_interval
            while time.time() < next_line_time:
                time.sleep(0.1)

            scan_line = self._current_dummy_data[:, self.__scan_line_count-1]
            channels = self._scan_data[self.__running_scan].channel_names

            self._scan_data[self.__running_scan].add_line_data(
                position=self.__scan_line_positions,
                data={chnl: scan_line for chnl in channels},
                y_index=self.__scan_line_count-1)

            self.sigScanDataChanged.emit({self.__running_scan: self.scan_data[self.__running_scan]})
            self.__sigNextLine.emit()
        return

    def _generate_2d_dummy_data(self, axes):
        x_res = self._scanner_settings['scan_resolution'][axes[0]]
        y_res = self._scanner_settings['scan_resolution'][axes[1]]
        x_start = self._scanner_settings['scan_range'][axes[0]][0]
        y_start = self._scanner_settings['scan_range'][axes[1]][0]
        z_start = -5e-6
        x_end = self._scanner_settings['scan_range'][axes[0]][1]
        y_end = self._scanner_settings['scan_range'][axes[1]][1]
        z_end = 5e-6
        x_range = x_end - x_start
        y_range = y_end - y_start
        z_range = z_end - z_start

        area_density = 1 / (5e-6 * 5e-6)

        params = np.random.rand(round(area_density * x_range * y_range), 7)
        params[:, 0] = params[:, 0] * x_range + x_start     # X displacement
        params[:, 1] = params[:, 1] * y_range + y_start     # Y displacement
        params[:, 2] = params[:, 2] * z_range + z_start     # Z displacement
        params[:, 3] = params[:, 3] * 50e-9 + 150e-9        # X sigma
        params[:, 4] = params[:, 4] * 50e-9 + 150e-9        # Y sigma
        params[:, 5] = params[:, 5] * 100e-9 + 450e-9       # Z sigma
        params[:, 6] = params[:, 6] * 2 * np.pi             # theta

        amplitude = 200000
        offset = 20000

        def gauss_ensemble(x, y):
            result = np.zeros(x.shape)
            for x0, y0, z0, sigmax, sigmay, sigmaz, theta in params:
                a = np.cos(theta) ** 2 / (2 * sigmax ** 2) + np.sin(theta) ** 2 / (2 * sigmay ** 2)
                b = np.sin(2 * theta) / (4 * sigmay ** 2) - np.sin(2 * theta) / (4 * sigmax ** 2)
                c = np.sin(theta) ** 2 / (2 * sigmax ** 2) + np.cos(theta) ** 2 / (2 * sigmay ** 2)
                zfactor = np.exp(-(z0 ** 2) / (2 * sigmaz**2))
                result += zfactor * np.exp(
                    -(a * (x - x0) ** 2 + 2 * b * (x - x0) * (y - y0) + c * (y - y0) ** 2))
            result *= amplitude - offset
            result += offset
            return result

        xx, yy = np.meshgrid(np.linspace(x_start, x_end, x_res),
                             np.linspace(y_start, y_end, y_res),
                             indexing='ij')
        return np.random.rand(xx.shape[0], xx.shape[1]) * amplitude * 0.10 + gauss_ensemble(xx, yy)


