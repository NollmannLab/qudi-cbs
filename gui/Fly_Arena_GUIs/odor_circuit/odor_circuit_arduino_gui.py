# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains a GUI for the odor circuit on the Fly Arena.

An extension to Qudi.

@author: D. Guerin, JB. Fiche

Created on Fry May 24, 2024
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

import logging
import os
import numpy as np
from PyQt5.QtCore import QTimer, Qt, QTime
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QFileDialog
from matplotlib import pyplot as plt
from qtpy import QtWidgets, uic, QtCore
# from qtpy.QtCore import Signal
# from scipy.stats import norm
# from datetime import datetime
from time import sleep
from core.configoption import ConfigOption
from core.connector import Connector
from gui.guibase import GUIBase

logging.basicConfig(filename='logfile.log', filemode='w', level=logging.DEBUG)
logger = logging.getLogger(__name__)


class MFCcheckWindow(QtWidgets.QDialog):
    """ Create the MFC calibration window, based on the corresponding *.ui file.
    This dialog allows the calibration of the MFCs """

    def __init__(self):
        super().__init__()
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'MFCcheck.ui')
        uic.loadUi(ui_file, self)


class MainWindow(QtWidgets.QMainWindow):
    """ Class defined for the main window for odor control.
    """

    def __init__(self, close_function):
        super().__init__()
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'odor_circuit_window1.ui')
        uic.loadUi(ui_file, self)
        self.close_function = close_function
        self.show()

    def closeEvent(self, event):
        self.close_function()
        event.accept()


class OdorCircuitGUI(GUIBase):
    """ Main GUI class to handle interactions with MFCs and Valves.
    """
    # connector
    odor_logic = Connector(interface='OdorCircuitArduinoLogic')
    _Path_MFC = ConfigOption('Path_MFC', None)
    _Fluidics_off_path = ConfigOption('Fluidics_off_path', None)
    _Fluidics_on_path = ConfigOption('Fluidics_on_path', None)
    _default_quadrant_flow = ConfigOption('default_quadrant_flow', None)
    _odors = ConfigOption('odors', None)
    _config_valves = ConfigOption('config_valve', None)
    _config_path = ConfigOption('config_path', None)

    # _path_MFC1 = ConfigOption('path_MFC1', None)
    # _path_MFC2 = ConfigOption('path_MFC2', None)
    # _path_MFCPurge = ConfigOption('path_MFCPurge', None)
    # valve_odor_1_in = 0
    # valve_odor_2_in = 0
    # valve_odor_3_in = 0
    # valve_odor_4_in = 0
    # valve_odor_1_out = 0
    # valve_odor_2_out = 0
    # valve_odor_3_out = 0
    # valve_odor_4_out = 0
    # mixing_valve = 0
    # final_valve = 0
    MFC_status = False

    sigStartFlowMeasure = QtCore.Signal()
    sigStopFlowMeasure = QtCore.Signal()
    sigChangeValveState = QtCore.Signal(str, int)
    sigStopFlowCalibration = QtCore.Signal()
    # define the default language option as English (to make sure all float have a point as a separator)
    QtCore.QLocale.setDefault(QtCore.QLocale("English"))

    # # Declaration of custom signals
    # sigMFC_ON = Signal()
    # sigMFC_OFF = Signal()
    # sigLaunchClicked = Signal()

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.date_str = None
        # self.Caltime = 0
        # self.G = 0
        self.prep_timer: object = None
        self.start_prep_time: int = 0
        self.inject_timer: object = None
        self.start_inject_time: int = 0
        self.calibration_timer: object = None
        self.start_calibration_time: int = 0
        self.flowrate_timetraces: dict = {}
        self.flowrate_data: dict = {}
        self.measure: dict = {}
        self.t_data: list = []
        self.MFC_number: int = 0
        self.odor_number: int = 0
        self.preparing_odor: bool = False
        self.injecting_odor: bool = False
        self.calibrating_MFCs: bool = False
        self.selected_odor: int = 0
        self.valve_status: dict = {}
        self.pixmap_fluidics_scheme: object = None

        # self._flowrate1_timetrace = None
        # self._flowrate2_timetrace = None
        # self._flowrate3_timetrace = None
        # self._flowrate4_timetrace = None
        # self.mesure1 = None
        # self.mesure2 = None
        # self.mesure3 = None
        # self.mesure4 = None
        # self.flowrate1_data = None
        # self.flowrate2_data = None
        # self.flowrate3_data = None
        # self.flowrate4_data = None
        self._odor_logic = None
        self._mw = None
        self._MFCW = None

        # self.valves_status = {
        #     'valve_odor_1_in': '0',
        #     'valve_odor_2_in': '0',
        #     'valve_odor_3_in': '0',
        #     'valve_odor_4_in': '0',
        #     'final_valve': '0',
        #     'mixing_valve': '0',
        #     'valve_odor_1_out': '0',
        #     'valve_odor_2_out': '0',
        #     'valve_odor_3_out': '0',
        #     'valve_odor_4_out': '0'
        # }
        # self.valves_in_out = {
        #     'odor_1': ['valve_odor_1_in', 'valve_odor_1_out'],
        #     'odor_2': ['valve_odor_2_in', 'valve_odor_2_out'],
        #     'odor_3': ['valve_odor_3_in', 'valve_odor_3_out'],
        #     'odor_4': ['valve_odor_4_in', 'valve_odor_4_out']
        # }
        self._mw = MainWindow(close_function=self.close_function)  # Assuming MainWindow handles main UI
        self._mfcw = MFCcheckWindow()

        # self.pixmap1 = QPixmap(self._Fluidics_on_path)
        # self.pixmap2 = QPixmap(self._Fluidics_off_path)
        # self.pixmap1 = self.pixmap1.scaled(1101, 651, Qt.KeepAspectRatio)
        # self.pixmap2 = self.pixmap2.scaled(1101, 651, Qt.KeepAspectRatio)

    def on_activate(self):
        """ Initialize all UI elements and establish signal connections.
        """
        # Connect logic and initialize variables for the GUI
        self._odor_logic = self.odor_logic()
        self.MFC_number = self._odor_logic.MFC_number
        self.odor_number = self._odor_logic.n_odors_available

        # Initialize the main window and its dockwidgets
        self._mw.centralwidget.show()
        self.init_menu()
        self.init_toolbar()
        self.init_flowcontrol_main_window()
        self.init_MFC_calibration_window()

        # Set the default flow
        self._mw.doubleSpinBox_quadrant_flow.setValue(self._default_quadrant_flow)
        self.update_arena_config()

    def on_deactivate(self):
        """ Steps of deactivation required.
        """
        self._mw.close()

# ----------------------------------------------------------------------------------------------------------------------
# Methods handling GUI windows and dockwidgets
# ----------------------------------------------------------------------------------------------------------------------
    def show(self):
        """ To make the window visible and bring it to the front.
        """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()

    # def show_admin_Dock(self):
    #     """Show the dock widget"""
    #     self._mw.admin_dockWidget.show()
    #
    # def hide_admin_Dock(self):
    #     """Hide the dock widget"""
    #     self._mw.admin_dockWidget.hide()

    def show_MFC_calibration_window(self):
        """ Show the plot window
        """
        self._mfcw.show()

    def init_menu(self):
        """ Initialize actions controlled by menu
        """
        # self._mw.actionShow_Configuration_Dock.triggered.connect(self.show_admin_Dock)
        self._mw.actionShow_MFC_stability_check.triggered.connect(self.show_MFC_calibration_window)

    def init_toolbar(self):
        """ Initialize toolbar actions
        """
        # self._mw.actionMFC_ON_OFF.setText('MFC : OFF')
        # self._mw.actionMFC_ON_OFF.triggered.connect(self.mfc_on_off)
        self._mw.start_flow_measurement_Action.triggered.connect(self.measure_flow_clicked)
        # self.sigMFC_ON.connect(self.mfc_on)
        # self.sigMFC_OFF.connect(self._odor_logic.stop_air_flow)

        # Connect signals to logic
        self.sigStartFlowMeasure.connect(self._odor_logic.start_flow_measurement)
        self.sigStopFlowMeasure.connect(self._odor_logic.stop_flow_measurement)

        # Connect signals from logic
        self._odor_logic.sigUpdateFlowMeasurement.connect(self.update_flowrate)
        self._odor_logic.sigDisableFlowActions.connect(self.disable_flowcontrol_buttons)
        self._odor_logic.sigEnableFlowActions.connect(self.enable_flowcontrol_buttons)

    def init_MFC_calibration_window(self):
        """ Initialize actions handle by the MFC calibration window
        """
        # Initialize pushbutton
        self._mfcw.toolButton_abort_calibration.setDisabled(True)

        # Connect signals to methods
        self._mfcw.toolButton_abort_calibration.clicked.connect(self.abort_MFC_calibration)
        self._mfcw.toolButton_start_calibration.clicked.connect(self.start_MFC_calibration)
        self._mfcw.toolButton_select_folder.clicked.connect(self.select_folder)

        # initialize timer
        self.calibration_timer = QTimer()
        self.calibration_timer.timeout.connect(lambda: self.update_calibration_timer(
            self._mfcw.doubleSpinBox_calibration_duration.value()))

        # connect signal to logic
        self.sigStopFlowCalibration.connect(self._odor_logic.stop_flow_calibration)

    def init_flowcontrol_main_window(self):
        """Initialize the flowcontrol dockwidget, setting up plots, labels, and signal-slot connections.
        """
        # assign odor names & disable the empty names
        for n_odor in range(len(self._odors)):
            checkbox = getattr(self._mw, f'odor{n_odor + 1}_CheckBox', None)
            checkbox.setText(self._odors[n_odor])
            if self._odors[n_odor] == 'no odor':
                checkbox.setDisabled(True)

        # display the fluidics scheme
        self.display_fluidics_scheme(0)

        # Connect signals from pushButtons to methods
        self._mw.comboBox_quadrants_config.currentIndexChanged.connect(self.update_arena_config)
        self._mw.doubleSpinBox_quadrant_flow.editingFinished.connect(self.update_arena_config)
        self._mw.Prepare_odor_pushButton.clicked.connect(self.prepare_odor_clicked)
        self._mw.Prepare_odor_pushButton.clicked.connect(self.start_prep_timer)
        self._mw.Inject_odor_pushButton.clicked.connect(self.inject_odor_clicked)
        self._mw.Inject_odor_pushButton.clicked.connect(self.start_inject_timer)
        self._mw.Stop_odor_pushButton.clicked.connect(self.stop_odor_clicked)
        self._mw.Switch_quadrant_pushButton.clicked.connect(self.switch_quadrant_clicked)

        # Connect signals from logic
        self._odor_logic.sigUpdateValveState.connect(self.update_valves_status)
        self._odor_logic.sigUpdateValveState.connect(self.display_circuit_config)

        # Connect signals from checkBox to methods
        self._mw.odor1_CheckBox.toggled.connect(lambda checked: self.selected_odor_changed(1, checked))
        self._mw.odor2_CheckBox.toggled.connect(lambda checked: self.selected_odor_changed(2, checked))
        self._mw.odor3_CheckBox.toggled.connect(lambda checked: self.selected_odor_changed(3, checked))
        self._mw.odor4_CheckBox.toggled.connect(lambda checked: self.selected_odor_changed(4, checked))
        self._mw.valve_odor_1_checkBox.toggled.connect(lambda checked:
                                                       self._odor_logic.change_valve_state("odor_1", checked))
        self._mw.valve_odor_2_checkBox.toggled.connect(lambda checked:
                                                       self._odor_logic.change_valve_state("odor_2", checked))
        self._mw.valve_odor_3_checkBox.toggled.connect(lambda checked:
                                                       self._odor_logic.change_valve_state("odor_3", checked))
        self._mw.valve_odor_4_checkBox.toggled.connect(lambda checked:
                                                       self._odor_logic.change_valve_state("odor_4", checked))
        self._mw.valve_mixing_checkBox.toggled.connect(lambda checked:
                                                       self._odor_logic.change_valve_state("mixing", checked))
        self._mw.valve_switch_purge_arena_checkBox.toggled.connect(
            lambda checked: self._odor_logic.change_valve_state("switch_purge_arena", checked))
        self._mw.valve_switch_quadrants_checkBox.toggled.connect(
            lambda checked: self._odor_logic.change_valve_state("switch_quadrants", checked))
        self._mw.valve_3_way_checkBox.toggled.connect(lambda checked:
                                                      self._odor_logic.change_valve_state("3_way", checked))

        # initialize pushButtons for odor
        self.disable_enable_odor_pushbuttons()

        # initialize checkBox for valves control
        self.disable_enable_valves_checkbox(False)

        # Configure plot widget and define plot colors and labels
        plot_widget = self._mw.flowrate_PlotWidget_1
        plot_widget.setLabel('left', 'Flowrate', units='L/min')
        plot_widget.setLabel('bottom', 'Time', units='s')
        plot_widget.addLegend()
        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
        labels = [f'MFC{i + 1}' for i in range(self.MFC_number)]

        # Initialize data containers for the flowchart
        self.t_data = []
        self.flowrate_data = {i: [] for i in range(self.MFC_number)}
        self.mesure_data = {i: [] for i in range(self.MFC_number)}
        self.flowrate_timetraces = {
            i: plot_widget.plot(self.t_data, self.flowrate_data[i], pen=colors[i], name=labels[i])
            for i in range(self.MFC_number)
        }

        # Initialize timers
        self.prep_timer, self.inject_timer = QTimer(), QTimer()
        self.prep_timer.timeout.connect(self.update_prep_timer)
        self.inject_timer.timeout.connect(self.update_inject_timer)

    def disable_enable_odor_pushbuttons(self, prep=True, inject=True, stop=True):
        """ Disable / Enable push buttons related to odor injection in arena """
        self._mw.Prepare_odor_pushButton.setDisabled(prep)
        self._mw.Inject_odor_pushButton.setDisabled(inject)
        self._mw.Stop_odor_pushButton.setDisabled(stop)

    def close_function(self):
        """
        This method serves as a reimplementation of the close event. Continuous measurement modes are stopped
        when the main window is closed.
        """
        if self._odor_logic.measuring_flowrate:
            self.sigStopFlowMeasure.emit()
            self._mw.start_flow_measurement_Action.setText('Start flowrate measurement')
            self._mw.start_flow_measurement_Action.setChecked(False)

    def display_fluidics_scheme(self, config):
        """ Handle the display of the valves & MFC scheme, depending on the indicated configuration
        @param config (int) indicate the configuration of the circuit
        """
        self.pixmap_fluidics_scheme = QPixmap(self._config_path[config])
        self.pixmap_fluidics_scheme = self.pixmap_fluidics_scheme.scaled(1021, 551, Qt.KeepAspectRatio,
                                                                         Qt.SmoothTransformation)
        self._mw.label_circuit_scheme.setPixmap(self.pixmap_fluidics_scheme)

# ----------------------------------------------------------------------------------------------------------------------
# Methods handling arena configuration & odors
# ----------------------------------------------------------------------------------------------------------------------
    def update_arena_config(self):
        """ Based on the comboBox value & the flow-rate setpoint for the arena (for each quadrant), compute the
        flow-rate for each MFC.
        """
        # read the comboBox to define which configuration is selected. Same for the flow which will define the expected
        # air-flow in each quadrant
        index = self._mw.comboBox_quadrants_config.currentIndex()
        flow = self._mw.doubleSpinBox_quadrant_flow.value()

        # check if measurement of flowrate is running - if yes, suspend it to allow communication with MFCs
        flowrate_measurement = self._odor_logic.measuring_flowrate
        if flowrate_measurement:
            self.sigStopFlowMeasure.emit()
            sleep(2)

        # depending on the selected config, define the air-flow setpoint values for each MFC and send it to the logic.
        # Three configurations are available :
        # 1: all MFCs are off - all valves (except the switch valve for the quadrants) are set to their initial states
        # 2: the two pairs of quadrants are handle using two different circuits - quadrants 1/3 are connected to the
        # odor circuit through MFCs 1/2/3 (air or odor, depending on the state of the final valve) and quadrants 2/4 are
        # connected to MFC 4 (air)
        # 3: all quadrants are connected to the odor circuits - MFC4 is then turned off.
        if (index == 0) or (flow == 0):
            mfc_flow = [0, 0, 0, 0]
            self.disable_enable_valves_checkbox(False)
            self._odor_logic.stop_air_flow()
            self.disable_enable_odor_pushbuttons()
            self.preparing_odor = False
            self.injecting_odor = False

        elif index == 1:
            mfc_flow = [flow, flow, 2 * flow, 2 * flow]
            self.disable_enable_valves_checkbox(True)
            self._odor_logic.start_air_flow(mfc_flow, config=1)
            self.disable_enable_odor_pushbuttons(prep=False)
        else:
            mfc_flow = [2 * flow, 2 * flow, 4 * flow, 0]
            self.disable_enable_valves_checkbox(True)
            self._odor_logic.start_air_flow(mfc_flow, config=2)
            self.disable_enable_odor_pushbuttons(prep=False)

        # update the set-points for all MFCs
        self._mw.MFC1_setpoint.setText(f'{str(mfc_flow[0])} sL/min')
        self._mw.MFC2_setpoint.setText(f'{str(mfc_flow[1])} sL/min')
        self._mw.MFC3_setpoint.setText(f'{str(mfc_flow[2])} sL/min')
        self._mw.MFC4_setpoint.setText(f'{str(mfc_flow[3])} sL/min')

        # restart flowrate measurement if it was running
        if flowrate_measurement:
            self.sigStartFlowMeasure.emit()

    def selected_odor_changed(self, odor, state):
        """ Handle the change in the state of the odor selection checkboxes. Note that only one checkBox can be selected
        at a time.
        @param: odor (int) indicate which odor is selected (from the checkbox)
        @param: state (int) indicate whether the checkbox is checked or unchecked
        """
        if state:
            # make sure all the other checkboxes are unchecked
            for i in range(1, self.odor_number + 1):
                if i != odor:
                    checkbox = getattr(self._mw, f'odor{i}_CheckBox', None)
                    checkbox.setChecked(False)
            # define the selected odor
            self.selected_odor = odor
        else:
            self.selected_odor = 0

    def prepare_odor_clicked(self):
        """ Handle the click event to launch the odor preparation process. Note that when clicked the procedure is
        launched and can only be stopped either by using the "Stop odor" or the "Inject odor" pushButtons.
        """
        # check if one odor was selected
        if self.selected_odor == 0:
            self.log.error("You need to select at least one odor")
            self._mw.Prepare_odor_pushButton.setChecked(False)
            return

        # release the inject and stop pushbuttons
        self.disable_enable_odor_pushbuttons(prep=True, inject=False, stop=False)

        # prepare the selected odor
        # odor_prep_time = self._mw.doubleSpinBox_odor_prep_duration.value() * 60
        if not self.preparing_odor:
            self._mw.Prepare_odor_pushButton.setChecked(True)
            self._mw.Prepare_odor_pushButton.setText('Preparing odor ...')
            self._odor_logic.prepare_odor(self.selected_odor)
            self.preparing_odor = True

            # check if an injection was performed
            if self.injecting_odor:
                self._mw.Inject_odor_pushButton.setChecked(False)
                self._mw.Inject_odor_pushButton.setText('Inject odor')
                self.injecting_odor = False

    def inject_odor_clicked(self):
        """ Handle event to launch injection into the arena. Note that when clicked the procedure is
        launched and can only be stopped by using either the "Stop odor" or "Prepare odor" pushButtons
        """
        # check if an odor is already in preparation
        if not self.preparing_odor:
            self.log.error("No odor is in preparation")
            self._mw.Inject_odor_pushButton.setChecked(False)
            return

        # release the prep and stop pushbuttons
        self.disable_enable_odor_pushbuttons(prep=False, inject=True, stop=False)

        # stop the timer for odor preparation
        self.stop_prep_timer()

        # inject the selected odor in the arena
        if not self.injecting_odor:
            # release the prepare odor pushButton
            self._mw.Prepare_odor_pushButton.setChecked(False)
            self._mw.Prepare_odor_pushButton.setText('Prepare odor')

            # launch injection
            self._mw.Inject_odor_pushButton.setChecked(True)
            self._mw.Inject_odor_pushButton.setText('Injecting odor ...')
            self._odor_logic.inject_odor()
            self.injecting_odor = True
            self.preparing_odor = False

    def stop_odor_clicked(self):
        """ Stop any preparation or injection of odor
        """
        # enable pushbutton for prep and disable the others
        self.disable_enable_odor_pushbuttons(prep=False, inject=True, stop=True)

        # release the prepare odor pushButton
        self._mw.Prepare_odor_pushButton.setChecked(False)
        self._mw.Prepare_odor_pushButton.setText('Prepare odor')
        self.preparing_odor = False

        # release the inject odor pushButton
        self._mw.Inject_odor_pushButton.setChecked(False)
        self._mw.Inject_odor_pushButton.setText('Inject odor')
        self.injecting_odor = False

        # send to logic
        self._odor_logic.stop_odor(self.selected_odor)

    def switch_quadrant_clicked(self):
        """ Change the quadrants' configuration. By default, quadrants 1/3 are connected to the odor circuit and
        quadrants 2/4 to the MFC4 & 3-way valve. When the valve is activated, the quadrants 1/3 and 2/4 are inverted.
        """
        state = self._mw.Switch_quadrant_pushButton.isChecked()
        self._odor_logic.switch_quadrants(int(state))

# ----------------------------------------------------------------------------------------------------------------------
# Methods handling the timers
# ----------------------------------------------------------------------------------------------------------------------
    def start_prep_timer(self):
        """Starts the timer for the odor preparation (when the button is clicked)."""
        self.start_prep_time = QTime.currentTime()  # Store start time
        self.prep_timer.start(1000)  # Update every second

    def update_prep_timer(self):
        """Updates the QLineEdit with elapsed time."""
        if self.start_prep_time and self.preparing_odor:
            elapsed = self.start_prep_time.secsTo(QTime.currentTime())  # Get elapsed time in seconds
            self._mw.prep_timer_display.setText(f"{elapsed} sec")
        else:
            self.stop_prep_timer()

    def stop_prep_timer(self):
        """Stops the odor preparation timer and resets the display."""
        self.prep_timer.stop()
        self.start_prep_time = None
        self._mw.prep_timer_display.setText("")

    def start_inject_timer(self):
        """Starts the timer for the odor preparation (when the button is clicked)."""
        self.start_inject_time = QTime.currentTime()  # Store start time
        self.inject_timer.start(1000)  # Update every second

    def update_inject_timer(self):
        """Updates the QLineEdit with elapsed time."""
        if self.start_inject_time and self.injecting_odor:
            elapsed = self.start_inject_time.secsTo(QTime.currentTime())  # Get elapsed time in seconds
            self._mw.inject_timer_display.setText(f"{elapsed} sec")
        else:
            self.stop_inject_timer()

    def stop_inject_timer(self):
        """Stops the odor preparation timer and resets the display."""
        self.inject_timer.stop()
        self.start_inject_time = None
        self._mw.inject_timer_display.setText("")

    def start_calibration_timer(self):
        """Starts the timer for the MFC calibration (when the toolButton_start_calibration is clicked)."""
        self.start_calibration_time = QTime.currentTime()  # Store start time
        self.calibration_timer.start(1000)  # Update every second

    def update_calibration_timer(self, duration):
        """ Updates the QLineEdit with elapsed time.
        @param: duration (float): indicate the duration of the calibration in minutes.
        """
        if self.start_calibration_time and self.calibrating_MFCs:
            elapsed = self.start_calibration_time.secsTo(QTime.currentTime())  # Get elapsed time in seconds
            self._mfcw.calibration_timer_display.setText(f"{elapsed} sec")
            if elapsed >= duration * 60:
                self.stop_calibration_timer()
        else:
            self.stop_calibration_timer()

    def stop_calibration_timer(self):
        """ Stops the odor preparation timer and resets the display.
        """
        # reinitialize the timer
        self.calibration_timer.stop()
        self.start_calibration_time = None
        self._mfcw.calibration_timer_display.setText("")

        # send signal to logic indicating the calibration should be terminated
        self.sigStopFlowCalibration.emit()

        # stop the calibration
        self.abort_MFC_calibration()

# ----------------------------------------------------------------------------------------------------------------------
# Methods handling the valves states
# ----------------------------------------------------------------------------------------------------------------------
    @QtCore.Slot(dict)
    def update_valves_status(self, status_dict):
        """ Update the status of the valve on the GUI
        @param status_dict: (dict) indicate whether a valve is open or close
        """
        self.valve_status = status_dict
        for key in self.valve_status.keys():
            checkbox = getattr(self._mw, f'valve_{key}_checkBox', None)
            checkbox.blockSignals(True)
            if status_dict[key] == 0:
                checkbox.setChecked(False)
            else:
                checkbox.setChecked(True)
            checkbox.blockSignals(False)

    def disable_enable_valves_checkbox(self, disable):
        """ For security, the valve checkboxes will be disabled when the MFCs are ON (to avoid closing or opening a
        valve while an experiment is running). However, when the MFCs are OFF, the checkbox associated to the valves
        will remain enable to allow testing (for debugging for example).
        @param disable: (bool) True if the checkboxes need to be disabled.
        """
        for key in self.valve_status.keys():
            checkbox = getattr(self._mw, f'valve_{key}_checkBox', None)
            checkbox.setDisabled(disable)
            sleep(0.05)

    def display_circuit_config(self, status_dict):
        """ Read the status_dict and select the associated valve configuration to display an illustration of the
        fluidics circuit
        @param status_dict: (dict) indicate whether a valve is open or close
        """
        index = self._mw.comboBox_quadrants_config.currentIndex()
        if index > 0:
            # convert status dictionary into a list
            status_list = [status_dict[key] for key in status_dict.keys()]
            print(status_list)

            # compare the list to the self._config_valves
            matching_config = [n_config if config == status_list else None
                               for n_config, config in enumerate(self._config_valves)]
            print(matching_config)

            # look for the matching config that is not None
            matching_config = next((config for config in matching_config if config is not None), None)

            # display the matching config
            if matching_config is not None:
                print(f'matching_config: {matching_config}')
                print(self._config_path[matching_config])
                self.display_fluidics_scheme(matching_config)
            else:
                print(f'matching_config: {matching_config} does not exist')

        else:
            self.display_fluidics_scheme(0)

# ----------------------------------------------------------------------------------------------------------------------
# Methods handling the flow chart (live display of the MFCs flow-rate)
# ----------------------------------------------------------------------------------------------------------------------
    @QtCore.Slot()
    def disable_flowcontrol_buttons(self):
        """
        Disables flowrate measurement action button
        """
        self._mw.start_flow_measurement_Action.setDisabled(True)

    @QtCore.Slot()
    def enable_flowcontrol_buttons(self):
        """
        Enables flowrate measurement action button
        """
        self._mw.start_flow_measurement_Action.setDisabled(False)

    def measure_flow_clicked(self):
        """
        Callback of start flow measurement tool button. Handles the tool button state and initiates the start / stop
        of flowrate .
        """
        if self._odor_logic.measuring_flowrate:  # measurement already running
            self._mw.start_flow_measurement_Action.setText('Start flowrate measurement')
            self.sigStopFlowMeasure.emit()
        else:
            self._mw.start_flow_measurement_Action.setText('Stop flowrate measurement')
            self.t_data = []
            self.flowrate_data = {i: [] for i in range(self.MFC_number)}
            self.sigStartFlowMeasure.emit()

    @QtCore.Slot(list)
    def update_flowrate(self, flow_rates):
        """
        Callback of a signal emitted from logic informing the GUI about the new flowrate values.
        @param (list) flow_rates: current flow-rates retrieved from hardware MFCs
        """
        # self.G += 1
        # Update flow rate data - a maximum of 100 data points will be displayed on the ime trace.
        if len(self.flowrate_data[1]) < 100:
            self.t_data.append(len(self.t_data))
            for i in range(self.MFC_number):
                self.flowrate_data[i].append(flow_rates[i])
                getattr(self._mw, f'MFC{i + 1}').setText(f'{np.around(flow_rates[i], decimals=3)} sL/min')
        else:
            self.t_data[:-1] = self.t_data[1:]
            self.t_data[-1] += 1

            for i in range(self.MFC_number):
                self.flowrate_data[i][:-1] = self.flowrate_data[i][1:]  # Shift data
                self.flowrate_data[i][-1] = flow_rates[i]

        # Update the time trace on the flow chart
        for i in range(self.MFC_number):
            self.flowrate_timetraces[i].setData(self.t_data, self.flowrate_data[i])

# ----------------------------------------------------------------------------------------------------------------------
# Methods handling the characterization / calibration of the MFCs
# ----------------------------------------------------------------------------------------------------------------------
    def start_MFC_calibration(self):
        """
        Start calibration of the MFcs flow (noise)
        """
        # disable the main window to avoid race issues and the calibration button
        self._mw.setDisabled(True)
        self._mfcw.toolButton_start_calibration.setDisabled(True)

        # initialize variables
        self.calibrating_MFCs = True
        self._mfcw.toolButton_abort_calibration.setDisabled(False)
        self.calibration_time = self._mfcw.doubleSpinBox_calibration_duration.value()
        mfc_setpoint = self._mfcw.doubleSpinBox_MFCs_setpoint.value()

        # check if measurement of flowrate is running - if yes, suspend it to allow communication with MFCs
        flowrate_measurement = self._odor_logic.measuring_flowrate
        if flowrate_measurement:
            self.sigStopFlowMeasure.emit()
            sleep(2)

        # set the configuration of the arena to ALL-OFF
        self._mw.comboBox_quadrants_config.setCurrentIndex(0)

        # launch MFCs based on the indicated setpoints - all MFCs are set to the same values
        mfc_flow = [mfc_setpoint, mfc_setpoint, mfc_setpoint, mfc_setpoint]
        self._odor_logic.start_air_flow(mfc_flow, config=1)
        self._mw.MFC1_setpoint.setText(f'{str(mfc_flow[0])} sL/min')
        self._mw.MFC2_setpoint.setText(f'{str(mfc_flow[1])} sL/min')
        self._mw.MFC3_setpoint.setText(f'{str(mfc_flow[2])} sL/min')
        self._mw.MFC4_setpoint.setText(f'{str(mfc_flow[3])} sL/min')

        # launch calibration
        hist_saving_path = os.path.join(self._mfcw.Folder_LineEdit.text(), self._mfcw.File_LineEdit.text())
        self.start_calibration_timer()
        self._odor_logic.start_flow_calibration(hist_saving_path)

    def abort_MFC_calibration(self):
        """Cancel the MFC calibration"""
        self._odor_logic.stop_flow_measurement()
        self._mw.setDisabled(False)
        self._mfcw.toolButton_abort_calibration.setDisabled(True)
        self._mfcw.toolButton_start_calibration.setDisabled(False)

    def select_folder(self):
        """ Select the folder where to save the graph """
        folder = QFileDialog.getExistingDirectory(self._mfcw, "Select Folder", "E:\DATA")
        if folder:
            self._mfcw.Folder_LineEdit.setText(folder)

    # def plot_total(self):
    #     """
    #     Plot the all 3 calibration graphs of the mfc
    #     """
    #     path1 = f'MesureMFC1{self.date_str}'
    #     path2 = f'MesureMFC2{self.date_str}'
    #     path3 = f'MesureMFC3{self.date_str}'
    #     path4 = f'MFCPlot{self.date_str}.png'
    #     P1 = os.path.join(self._Path_MFC, path1)
    #     P2 = os.path.join(self._Path_MFC, path2)
    #     P3 = os.path.join(self._Path_MFC, path3)
    #     P4 = os.path.join(self._Path_MFC, path4)
    #     np.savetxt(P1, self.mesure1, fmt='%.6f')
    #     np.savetxt(P2, self.mesure2, fmt='%.6f')
    #     np.savetxt(P3, self.mesure3, fmt='%.6f')
    #     self.show_plot()
    #     plt.savefig(P4)

    # def measure_flow_clicked(self):
    #     """
    #     Callback of start flow measurement tool button. Handles the tool button state and initiates the start / stop
    #     of flowrate .
    #     """
    #     if self._odor_logic.measuring_flowrate:  # measurement already running
    #         self._mw.start_flow_measurement_Action.setText('Start flowrate measurement')
    #         self.sigStopFlowMeasure.emit()
    #         self._mw.actionMFC_ON_OFF.setDisabled(False)
    #     else:
    #         self._mw.start_flow_measurement_Action.setText('Stop flowrate measurement')
    #         self.t_data = []
    #         self.flowrate1_data = []
    #         self.flowrate2_data = []
    #         self.flowrate3_data = []
    #         self.flowrate4_data = []
    #         self.sigStartFlowMeasure.emit()
    #         self._mw.actionMFC_ON_OFF.setDisabled(True)

    # @staticmethod
    # def plot_histogram_with_density(data, label, color, ax):
    #     """
    #     Plot a histogram
    #     @param label : Name of the MFC
    #     @param color : color of the plot
    #     @param data : the mfc values
    #     @param ax : the place of the graph on the print
    #     """
    #     mean_value = np.mean(data)
    #     std_deviation = np.std(data)
    #
    #     count, bins, ignored = ax.hist(data, bins='auto', alpha=0.5, rwidth=0.85, color=color,
    #                                    edgecolor='black', density=True, label=f'{label} histogram')
    #
    #     bin_centers = 0.5 * (bins[1:] + bins[:-1])
    #     pdf = norm.pdf(bin_centers, mean_value, std_deviation)
    #
    #     ax.plot(bin_centers, pdf, linestyle='dashed', linewidth=2, color=color, label=f'{label} density')
    #
    #     ax.axvline(mean_value, color=color, linestyle='dashed', linewidth=1)
    #     ax.text(mean_value + 0.1 * (np.max(data) - np.min(data)), ax.get_ylim()[1] * 0.9,
    #             f'{label} Mean: {mean_value:.6f}', color=color)
    #     ax.text(mean_value + 0.1 * (np.max(data) - np.min(data)), ax.get_ylim()[1] * 0.85,
    #             f'{label} Std Dev: {std_deviation:.6f}', color=color)

    # def show_plot(self):
    #     """
    #     Show the Plot
    #     """
    #     fig, axes = plt.subplots(3, 1, figsize=(10, 18))
    #     self.plot_histogram_with_density(self.mesure1, 'MFC 1', 'b', axes[0])
    #     self.plot_histogram_with_density(self.mesure2, 'MFC 2', 'g', axes[1])
    #     self.plot_histogram_with_density(self.mesure3, 'MFC Purge', 'r', axes[2])
    #
    #     for i, ax in enumerate(axes):
    #         ax.set_xlabel('Valeurs')
    #         ax.set_ylabel('Densité')
    #         ax.legend()
    #
    #     fig.suptitle('Histograms and Density Curves for the MFCs')
    #     plt.show()




        # self.mesure1.append(flow_rates[0])
        # self.mesure2.append(flow_rates[1])
        # self.mesure3.append(flow_rates[2])
        # self.mesure4.append(flow_rates[3])

        # if self.G == self.Caltime * 60:
        #     self._odor_logic.stop_flow_measurement()
        #     self.plot_total()
        #     self._mfcw.toolButton_abort_calibration.setDisabled(True)
        #     self._mw.setDisabled(False)
        #     self._mfcw.toolButton.setDisabled(False)

    # def init_flowcontrol(self):
    #     """ This method initializes the flowcontrol dockwidget.
    #     It initializes the line plot and sets an adapted text on the labels on the flowcontrol dockwidget.
    #     It establishes the signal-slot connections for the toolbar actions.
    #     """
    #     # initialize the line plot
    #     # data for flowrate plot initialization
    #     self.t_data = []
    #     self.flowrate1_data = []
    #     self.flowrate2_data = []
    #     self.flowrate3_data = []
    #     self.flowrate4_data = []
    #     self.mesure1 = []
    #     self.mesure2 = []
    #     self.mesure3 = []
    #     self.mesure4 = []
    #
    #     # create a reference to the line object (this is returned when calling plot method of pg.PlotWidget)
    #     self._mw.flowrate_PlotWidget_1.setLabel('left', 'Flowrate', units='L/min')
    #     self._mw.flowrate_PlotWidget_1.setLabel('bottom', 'Time', units='s')
    #     self._mw.actionMFC_ON_OFF.setText('MFC : OFF')
    #     self._mw.flowrate_PlotWidget_1.addLegend()
    #
    #     # Initial plot setup
    #     self._flowrate1_timetrace = self._mw.flowrate_PlotWidget_1.plot(self.t_data, self.flowrate1_data,
    #                                                                     pen=(255, 0, 0), name='MFC1')
    #     self._flowrate2_timetrace = self._mw.flowrate_PlotWidget_1.plot(self.t_data, self.flowrate2_data,
    #                                                                     pen=(0, 255, 0), name='MFC2')
    #     self._flowrate3_timetrace = self._mw.flowrate_PlotWidget_1.plot(self.t_data, self.flowrate3_data,
    #                                                                     pen=(0, 0, 255), name='MFC3_purge')
    #     self._flowrate4_timetrace = self._mw.flowrate_PlotWidget_1.plot(self.t_data, self.flowrate4_data,
    #                                                                     pen=(255, 255, 255), name='MFC4')
    #
    #     # toolbar actions: internal signals
    #     self._mw.start_flow_measurement_Action.triggered.connect(self.measure_flow_clicked)
    #     self._mw.actionMFC_ON_OFF.triggered.connect(self.mfc_on_off)
    #     self._mw.actionShow_Configuration_Dock.triggered.connect(self.showDock)
    #     self._mw.actionShow_Configuration_Dock.triggered.connect(self.showDock)
    #     self._mw.actionShow_MFC_stability_check.triggered.connect(self.show_plotwindow)
    #
    #     # signals to logic
    #     self.sigStartFlowMeasure.connect(self._odor_logic.start_flow_measurement)
    #     self._mfcw.toolButton.clicked.connect(self.Start_measure)
    #     self.sigStopFlowMeasure.connect(self._odor_logic.stop_flow_measurement)
    #
    #     # signals from logic
    #     self._odor_logic.sigUpdateFlowMeasurement.connect(self.update_flowrate)
    #     self._odor_logic.sigDisableFlowActions.connect(self.disable_flowcontrol_buttons)
    #     self._odor_logic.sigEnableFlowActions.connect(self.enable_flowcontrol_buttons)
    #     self.sigMFC_ON.connect(self.mfc_on)
    #     self.sigMFC_OFF.connect(self._odor_logic.stop_air_flow)
    #
    #     self.timer1 = QTimer()
    #     self.timer2 = QTimer()
    #
    # @QtCore.Slot(list)
    # def update_flowrate(self, flow_rates):
    #     """
    #     Callback of a signal emitted from logic informing the GUI about the new flowrate values.
    #     @param (list) flow_rates: current flow-rates retrieved from hardware MFCs
    #     """
    #     self.G += 1
    #     if len(self.flowrate1_data) < 100:
    #         self.t_data.append(len(self.t_data))
    #         self.flowrate1_data.append(flow_rates[0])
    #         self.flowrate2_data.append(flow_rates[1])
    #         self.flowrate3_data.append(flow_rates[2])
    #         self.flowrate4_data.append(flow_rates[3])
    #         self._mw.MFC1.setText(f'{np.around(flow_rates[0], decimals=4)}')
    #         self._mw.MFC2.setText(f'{np.around(flow_rates[1], decimals=4)}')
    #         self._mw.MFC3.setText(f'{np.around(flow_rates[2], decimals=4)}')
    #         self._mw.MFC4.setText(f'{np.around(flow_rates[3], decimals=4)}')
    #     else:
    #         self.t_data[:-1] = self.t_data[1:]
    #         self.t_data[-1] += 1
    #
    #         self.flowrate1_data[:-1] = self.flowrate1_data[1:]  # shift data one position to the left
    #         self.flowrate1_data[-1] = flow_rates[0]
    #         self.flowrate2_data[:-1] = self.flowrate2_data[1:]  # shift data one position to the left
    #         self.flowrate2_data[-1] = flow_rates[1]
    #         self.flowrate3_data[:-1] = self.flowrate3_data[1:]  # shift data one position to the left
    #         self.flowrate3_data[-1] = flow_rates[2]
    #         self.flowrate4_data[:-1] = self.flowrate4_data[1:]  # shift data one position to the left
    #         self.flowrate4_data[-1] = flow_rates[3]
    #
    #     self.mesure1.append(flow_rates[0])
    #     self.mesure2.append(flow_rates[1])
    #     self.mesure3.append(flow_rates[2])
    #     self.mesure4.append(flow_rates[3])
    #     self._flowrate1_timetrace.setData(self.t_data, self.flowrate1_data)  # t axis running with time
    #     self._flowrate2_timetrace.setData(self.t_data, self.flowrate2_data)
    #     self._flowrate3_timetrace.setData(self.t_data, self.flowrate3_data)
    #     self._flowrate4_timetrace.setData(self.t_data, self.flowrate4_data)
    #
    #     if self.G == self.Caltime * 60:
    #         self._odor_logic.stop_flow_measurement()
    #         self.plot_total()
    #         self._mfcw.toolButton_abort_calibration.setDisabled(True)
    #         self._mw.setDisabled(False)
    #         self._mfcw.toolButton.setDisabled(False)

    # def check_odor_valves_states(self, valves_status):
    #     injected_odor = 0
    #
    #     # Check associations where both in and out valves are open
    #     for odor, (in_valve, out_valve) in self.valves_in_out.items():
    #         if valves_status[in_valve] == '1' and valves_status[out_valve] == '1':
    #             count_on_associations += 1
    #             active_associations.append(odor)
    #         elif valves_status[in_valve] == '1' and valves_status[out_valve] == '0':
    #             logger.error(f"You need to open {out_valve}")
    #             return 0
    #         elif valves_status[out_valve] == '1' and valves_status[in_valve] == '0':
    #             logger.error(f"You need to open {in_valve}")
    #             return 0
    #
    # def check_valves(self, valves_status):
    #     """
    #     Check valves status to permit the MFC2 to turn on
    #     @param valves_statues : is the dictionary of valves
    #     """
    #
    #     count_on_associations = 0
    #     active_associations = []
    #
    #     # Check associations where both in and out valves are '1'
    #     for odor, (in_valve, out_valve) in self.valves_in_out.items():
    #         if valves_status[in_valve] == '1' and valves_status[out_valve] == '1':
    #             count_on_associations += 1
    #             active_associations.append(odor)
    #         elif valves_status[in_valve] == '1' and valves_status[out_valve] == '0':
    #             logger.error(f"You need to open {out_valve}")
    #             return 0
    #         elif valves_status[out_valve] == '1' and valves_status[in_valve] == '0':
    #             logger.error(f"You need to open {in_valve}")
    #             return 0
    #
    #     # Determine action based on mixing valve status and count of active associations
    #     if count_on_associations > 1:
    #         logger.error('You need to close all but one pair of valves')
    #         return 0
    #     elif count_on_associations == 1 and valves_status['mixing_valve'] == '1':
    #         logger.info('The Mixing valve has been automatically closed')
    #         return 1
    #
    #     elif count_on_associations == 1 and valves_status['mixing_valve'] == '0':
    #         logger.info(f'MFC2 operates for {active_associations[0]}')
    #         return 1
    #     elif count_on_associations == 0 and valves_status['mixing_valve'] == '1':
    #         logger.info('MFC2 operates with mixing valve.')
    #         return 1
    #     elif count_on_associations == 0 and valves_status['mixing_valve'] == '0':
    #         logger.error('You need to open the Mixing Valve first')
    #         return 0
    #
    #
    #
    #
    # def clear(self):
    #     """
    #      Reset the valve statuses and update the labels.
    #     """
    #     self.valves_status['valve_odor_1_in'] = '0'
    #     self.valves_status['valve_odor_1_out'] = '0'
    #     self.valves_status['valve_odor_2_in'] = '0'
    #     self.valves_status['valve_odor_2_out'] = '0'
    #     self.valves_status['valve_odor_3_in'] = '0'
    #     self.valves_status['valve_odor_3_out'] = '0'
    #     self.valves_status['valve_odor_4_in'] = '0'
    #     self.valves_status['valve_odor_4_out'] = '0'
    #     self.update_valve_label(self._mw.label_1in_2, 0)
    #     self.update_valve_label(self._mw.label_1out_2, 0)
    #     self.update_valve_label(self._mw.label_2in_2, 0)
    #     self.update_valve_label(self._mw.label_2out_2, 0)
    #     self.update_valve_label(self._mw.label_3in_2, 0)
    #     self.update_valve_label(self._mw.label_3out_2, 0)
    #     self.update_valve_label(self._mw.label_4in_2, 0)
    #     self.update_valve_label(self._mw.label_4out_2, 0)
    #
    # a = 0
    #
    # # def odor_changed(self, state):
    #     """Handle the change in the state of the odor selection checkboxes."""
    #
    #     sender = self.sender()  # Get the QCheckBox that emitted the signal
    #     self.clear()
    #
    #     if sender == self._mw.odor1:
    #
    #         if state == 2:  # Qt.Checked
    #             self._mw.odor2.setChecked(False)
    #             self._mw.odor3.setChecked(False)
    #             self._mw.odor4.setChecked(False)
    #             self.valves_status['valve_odor_1_in'] = '1'
    #             self.update_valve_label(self._mw.label_1in_2, 1)
    #             self.valves_status['valve_odor_1_out'] = '1'
    #             self.update_valve_label(self._mw.label_1out_2, 1)
    #             self.a = 1
    #         else:
    #             self.valves_status['valve_odor_1_in'] = '0'
    #             self.update_valve_label(self._mw.label_1in_2, 0)
    #             self.valves_status['valve_odor_1_out'] = '0'
    #             self.update_valve_label(self._mw.label_1out_2, 0)
    #
    #     elif sender == self._mw.odor2:
    #
    #         if state == 2:  # Qt.Checked
    #             self._mw.odor3.setChecked(False)
    #             self._mw.odor4.setChecked(False)
    #             self._mw.odor1.setChecked(False)
    #             self.valves_status['valve_odor_2_in'] = '1'
    #             self.update_valve_label(self._mw.label_2in_2, 1)
    #             self.valves_status['valve_odor_2_out'] = '1'
    #             self.update_valve_label(self._mw.label_2out_2, 1)
    #             self.a = 2
    #         else:
    #             self.valves_status['valve_odor_2_in'] = '0'
    #             self.update_valve_label(self._mw.label_2in_2, 0)
    #             self.valves_status['valve_odor_2_out'] = '0'
    #             self.update_valve_label(self._mw.label_2out_2, 0)
    #     elif sender == self._mw.odor3:
    #
    #         if state == 2:  # Qt.Checked
    #             self._mw.odor2.setChecked(False)
    #             self._mw.odor4.setChecked(False)
    #             self._mw.odor1.setChecked(False)
    #             self.valves_status['valve_odor_3_in'] = '1'
    #             self.update_valve_label(self._mw.label_3in_2, 1)
    #             self.valves_status['valve_odor_3_out'] = '1'
    #             self.update_valve_label(self._mw.label_3out_2, 1)
    #             self.a = 3
    #         else:
    #             self.valves_status['valve_odor_3_in'] = '0'
    #             self.update_valve_label(self._mw.label_3in_2, 0)
    #             self.valves_status['valve_odor_3_out'] = '0'
    #             self.update_valve_label(self._mw.label_3out_2, 0)
    #
    #     elif sender == self._mw.odor4:
    #
    #         if state == 2:  # Qt.Checked
    #             self._mw.odor3.setChecked(False)
    #             self._mw.odor2.setChecked(False)
    #             self._mw.odor1.setChecked(False)
    #             self.valves_status['valve_odor_4_in'] = '1'
    #             self.update_valve_label(self._mw.label_4in_2, 1)
    #             self.valves_status['valve_odor_4_out'] = '1'
    #             self.update_valve_label(self._mw.label_4out_2, 1)
    #             self.a = 4
    #         else:
    #             self.valves_status['valve_odor_4_in'] = '0'
    #             self.update_valve_label(self._mw.label_4in_2, 0)
    #             self.valves_status['valve_odor_4_out'] = '0'
    #             self.update_valve_label(self._mw.label_4out_2, 0)
    #
    #
    #
    # def enable_valve_after_launch(self):
    #     """Enable the valves and update the labels after the launch process."""
    #     self._mw.checkBox_M_2.setChecked(False)
    #     self._mw.in1.setDisabled(False)
    #     self._mw.out1.setDisabled(False)
    #     self._mw.in2.setDisabled(False)
    #     self._mw.out2.setDisabled(False)
    #     self._mw.in3.setDisabled(False)
    #     self._mw.out3.setDisabled(False)
    #     self._mw.in4.setDisabled(False)
    #     self._mw.out4.setDisabled(False)
    #     self._mw.checkBox_F_2.setDisabled(False)
    #     self.valves_status['mixing_valve'] = '1'
    #     self.update_valve_label(self._mw.label_M_2, 1)
    #     self.valves_status['final_valve'] = '0'
    #     self.update_final_valve_label(0)
    #     self.clear()
    #     self.timer2.stop()
    #
    # def sendit(self):
    #     """Activate the final valve and update its label.
    #     """
    #     self.valves_status['final_valve'] = '1'
    #     self.update_final_valve_label(1)
    #     self._odor_logic.valve(self._final_valve, 1)
    #     self.timer1.stop()
    #
    # def flush(self):
    #     """Flush the odor circuit and activate the mixing valve."""
    #     self._odor_logic.flush_odor()
    #     self._odor_logic.valve(self._mixing_valve, 1)
    #     self.valves_status['Mixing_valve'] = '1'
    #


    # def LaunchClicked(self):
    #     """Handle the click event to launch the odor preparation process.
    #     """
    #     self._mw.Launch.setDisabled(True)
    #     Bodor = self._mw.Bodor.value() * 60
    #     Aodor = self._mw.Aodor.value() * 60
    #     self._odor_logic.prepare_odor(self.a)
    #     self._odor_logic.valve(self._mixing_valve, 0)
    #     self.valves_status['Mixing_valve'] = '0'
    #     self.timer1.timeout.connect(self.sendit)
    #     self.timer1.start(Bodor * 1000)
    #     self.timer2.timeout.connect(self.flush)
    #     self.timer2.timeout.connect(self.enable_valve_after_launch)
    #     self.timer2.start((Aodor * 1000) + Bodor * 1000)
    #     self._mw.stoplaunch.setDisabled(False)
    #
    # def stop_Launch(self):
    #     """
    #     Stops the QTimers if it is active.
    #     """
    #     self.flush()
    #     self.enable_valve_after_launch()
    #
    #     if self.timer1.isActive():
    #         self.timer1.stop()
    #         logger.info("Timer1 stopped.")
    #     if self.timer2.isActive():
    #         self.timer2.stop()
    #         logger.info("Timer2 stopped.")
    #
    #     self._mw.Launch.setDisabled(False)
    #     self._mw.stoplaunch.setDisabled(True)

    # @staticmethod
    # def update_valve_label(label, state):
    #     """
    #     Update the valve label to show 'opened' or 'closed'.
    #     @param label : the designated label related to the valves or MFCs
    #     @param state :  (bool) ON or OFF (1 or 0)
    #     """
    #     if state == 1:
    #         label.setText("Open")
    #     else:
    #         label.setText("Close")

    # def update_final_valve_label(self, state):
    #     """
    #     Update the final valve label to change background image.
    #     @param state :  (bool) ON or OFF (1 or 0)
    #     """
    #     if state == 1:
    #         self._mw.label_circuit_scheme.setPixmap(self.pixmap1)
    #     else:
    #         self._mw.label_circuit_scheme.setPixmap(self.pixmap2)

    # def check_box_changed(self, state):
    #     """
    #     Check the state of the valves box and turn on or off the devise
    #     if check, turn on; if unchecked, turn off.
    #     """
    #     sender = self.sender()  # Get the QCheckBox that emitted the signal
    #
    #     if sender == self._mw.in1:
    #         if state == 2:  # Qt.Checked
    #             self._odor_logic.valve(self._valve_odor_1_in, 1)
    #             self.valves_status['valve_odor_1_in'] = '1'
    #             self.update_valve_label(self._mw.label_1in_2, 1)
    #         else:
    #             self._odor_logic.valve(self._valve_odor_1_in, 0)
    #             self.valves_status['valve_odor_1_in'] = '0'
    #             self.update_valve_label(self._mw.label_1in_2, 0)
    #     elif sender == self._mw.out1:
    #         if state == 2:  # Qt.Checked
    #             self._odor_logic.valve(self._valve_odor_1_out, 1)
    #             self.valves_status['valve_odor_1_out'] = '1'
    #             self.update_valve_label(self._mw.label_1out_2, 1)
    #         else:
    #             self._odor_logic.valve(self._valve_odor_1_out, 0)
    #             self.valves_status['valve_odor_1_out'] = '0'
    #             self.update_valve_label(self._mw.label_1out_2, 0)
    #     elif sender == self._mw.in2:
    #         if state == 2:  # Qt.Checked
    #             self._odor_logic.valve(self._valve_odor_2_in, 1)
    #             self.valves_status['valve_odor_2_in'] = '1'
    #             self.update_valve_label(self._mw.label_2in_2, 1)
    #         else:
    #             self._odor_logic.valve(self._valve_odor_2_in, 0)
    #             self.valves_status['valve_odor_2_in'] = '0'
    #             self.update_valve_label(self._mw.label_2in_2, 0)
    #     elif sender == self._mw.out2:
    #         if state == 2:  # Qt.Checked
    #             self._odor_logic.valve(self._valve_odor_2_out, 1)
    #             self.valves_status['valve_odor_2_out'] = '1'
    #             self.update_valve_label(self._mw.label_2out_2, 1)
    #         else:
    #             self._odor_logic.valve(self._valve_odor_2_out, 0)
    #             self.valves_status['valve_odor_2_out'] = '0'
    #             self.update_valve_label(self._mw.label_2out_2, 0)
    #     elif sender == self._mw.in3:
    #         if state == 2:  # Qt.Checked
    #             self._odor_logic.valve(self._valve_odor_3_in, 1)
    #             self.valves_status['valve_odor_3_in'] = '1'
    #             self.update_valve_label(self._mw.label_3in_2, 1)
    #         else:
    #             self._odor_logic.valve(self._valve_odor_3_in, 0)
    #             self.valves_status['valve_odor_3_in'] = '0'
    #             self.update_valve_label(self._mw.label_3in_2, 0)
    #     elif sender == self._mw.out3:
    #         if state == 2:  # Qt.Checked
    #             self._odor_logic.valve(self._valve_odor_3_out, 1)
    #             self.valves_status['valve_odor_3_out'] = '1'
    #             self.update_valve_label(self._mw.label_3out_2, 1)
    #         else:
    #             self._odor_logic.valve(self._valve_odor_3_out, 0)
    #             self.valves_status['valve_odor_3_out'] = '0'
    #             self.update_valve_label(self._mw.label_3out_2, 0)
    #     elif sender == self._mw.in4:
    #         if state == 2:  # Qt.Checked
    #             self._odor_logic.valve(self._valve_odor_4_in, 1)
    #             self.valves_status['valve_odor_4_in'] = '1'
    #             self.update_valve_label(self._mw.label_4in_2, 1)
    #         else:
    #             self._odor_logic.valve(self._valve_odor_4_in, 0)
    #             self.valves_status['valve_odor_4_in'] = '0'
    #             self.update_valve_label(self._mw.label_4in_2, 0)
    #     elif sender == self._mw.out4:
    #         if state == 2:  # Qt.Checked
    #             self._odor_logic.valve(self._valve_odor_4_out, 1)
    #             self.valves_status['valve_odor_4_out'] = '1'
    #             self.update_valve_label(self._mw.label_4out_2, 1)
    #         else:
    #             self._odor_logic.valve(self._valve_odor_4_out, 0)
    #             self.valves_status['valve_odor_4_out'] = '0'
    #             self.update_valve_label(self._mw.label_4out_2, 0)
    #     elif sender == self._mw.checkBox_F_2:
    #         if state == 2:  # Qt.Checked
    #             self._odor_logic.valve(self._final_valve, 1)
    #             self.valves_status['final_valve_valve'] = '1'
    #             self.update_final_valve_label(1)
    #         else:
    #             self._odor_logic.valve(self._final_valve, 0)
    #             self.valves_status['final_valve_valve'] = '0'
    #             self.update_final_valve_label(0)
    #     elif sender == self._mw.checkBox_M_2:
    #         if state == 2:  # Qt.Checked
    #             self._odor_logic.valve(self._mixing_valve, 1)
    #             self.valves_status['mixing_valve'] = '1'
    #             self.update_valve_label(self._mw.label_M_2, 1)
    #         else:
    #             self._odor_logic.valve(self._mixing_valve, 0)
    #             self.valves_status['mixing_valve'] = '0'
    #             self.update_valve_label(self._mw.label_M_2, 0)
    #
    # def mfc_on(self):
    #     """
    #     Open the MFCs at the value indicated on the interface
    #     """
    #     flow_setpoints = [self._mw.doubleSpinBox_MFC1.value(), self._mw.doubleSpinBox_MFC2.value(),
    #                       self._mw.doubleSpinBox_MFC3_purge.value(), self._mw.doubleSpinBox_MFC4.value()]
    #     self._odor_logic.turn_MFC_on(flow_setpoints)
    #
    # def mfc_on_off(self):
    #     """
    #     Turn the MFCs on or off switching the MFC status
    #     """
    #
    #     if not self.MFC_status:
    #         self._odor_logic.valve(self._mixing_valve, 1)
    #         self.valves_status['mixing_valve'] = '1'
    #         self.update_valve_label(self._mw.label_M_2, 1)
    #         Permission = self.check_valves(self.valves_status)
    #         if Permission == 1:
    #             logger.info("Turning MFCs on")
    #             # self.mfc_on()
    #             self.sigMFC_ON.emit()
    #             self._mw.actionMFC_ON_OFF.setText('MFC : ON')
    #             self.MFC_status = True
    #             self._odor_logic.valve(self._mixing_valve, 1)
    #             self._mw.checkBox_M_2.setChecked(True)
    #             self.valves_status['mixing_valve'] = '1'
    #             self.update_valve_label(self._mw.label_M_2, 1)
    #             self.update_valve_label(self._mw.label_MFCpurge_2, 1)
    #             self.update_valve_label(self._mw.label_MFC1_2, 1)
    #             self.update_valve_label(self._mw.label_MFC2_2, 1)
    #         else:
    #             logger.info("Permission denied")
    #     else:
    #         logger.info("Closing air...")
    #         self._mw.actionMFC_ON_OFF.setText('MFC : OFF')
    #         self.sigMFC_OFF.emit()
    #         self.MFC_status = False
    #         self._odor_logic.valve(self._mixing_valve, 0)
    #         self._mw.checkBox_M_2.setChecked(False)
    #         self.valves_status['Mixing_valve'] = '0'
    #         self.update_valve_label(self._mw.label_M_2, 0)
    #         self.update_valve_label(self._mw.label_MFCpurge_2, 0)
    #         self.update_valve_label(self._mw.label_MFC1_2, 0)
    #         self.update_valve_label(self._mw.label_MFC2_2, 0)


