# -*- coding: utf-8 -*-
"""
Qudi-CBS

An extension to Qudi.

This module contains a task to simulate a Hi-M experiment.

@author: F. Barho

Created on Tue May 04 2021
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
import yaml
from datetime import datetime
import numpy as np
import pandas as pd
import os
import time
from tqdm import tqdm
from logic.generic_task import InterruptableTask
from logic.task_helper_functions import save_z_positions_to_file, save_injection_data_to_csv, create_path_for_injection_data
from logic.task_logging_functions import update_default_info, write_status_dict_to_file, add_log_entry


class Task(InterruptableTask):  # do not change the name of the class. it is always called Task !
    """ This task simulates a complete Hi-M experiment.

    Config example pour copy-paste:

    HiMTask:
        module: 'HiM_task_dummy'
        needsmodules:
            laser: 'lasercontrol_logic'
            bf: 'brightfield_logic'
            cam: 'camera_logic'
            focus: 'focus_logic'
            roi: 'roi_logic'
            valves: 'valve_logic'
            pos: 'positioning_logic'
            flow: 'flowcontrol_logic'
        config:
            path_to_user_config: '/home/barho/qudi_files/qudi_task_config_files/hi_m_task_RAMM.yml'
    """
    # ===============================================================================================================
    # Generic Task methods
    # ===============================================================================================================

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print('Task {0} added!'.format(self.name))
        self.user_config_path = self.config['path_to_user_config']
        self.probe_counter = None
        self.user_param_dict = {}
        self.logging = True

    def startTask(self):
        """ """
        self.start = time.time()

        self.log.info('started Task')

        self.default_exposure = self.ref['cam'].get_exposure()  # store this value to reset it at the end of task

        # stop all interfering modes on GUIs and disable GUI actions
        self.ref['roi'].disable_tracking_mode()
        self.ref['roi'].disable_roi_actions()

        self.ref['cam'].stop_live_mode()
        self.ref['cam'].disable_camera_actions()

        self.ref['laser'].stop_laser_output()
        self.ref['bf'].led_off()
        self.ref['laser'].disable_laser_actions()  # includes also disabling of brightfield on / off button

        self.ref['valves'].disable_valve_positioning()
        self.ref['flow'].disable_flowcontrol_actions()
        self.ref['pos'].disable_positioning_actions()

        # control if experiment can be started : origin defined in position logic ?
        if not self.ref['pos'].origin:
            self.log.warning('No position 1 defined for injections. Experiment can not be started. Please define position 1')
            return

        # set stage velocity
        self.ref['roi'].set_stage_velocity({'x': 1, 'y': 1})

        # read all user parameters from config
        self.load_user_parameters()

        # create a directory in which all the data will be saved
        self.directory = self.create_directory(self.save_path)

        # log file paths -----------------------------------------------------------------------------------------------
        self.log_folder = os.path.join(self.directory, 'hi_m_log')
        os.makedirs(self.log_folder)  # recursive creation of all directories on the path

        # default info file is used on start of the bokeh app to configure its display elements. It is needed only once
        self.default_info_path = os.path.join(self.log_folder, 'default_info.yaml')
        # the status dict 'current_status.yaml' contains basic information and updates regularly
        self.status_dict_path = os.path.join(self.log_folder, 'current_status.yaml')
        # the log file contains more detailed information about individual steps and is a user readable format.
        # It is also useful after the experiment has finished.
        self.log_path = os.path.join(self.log_folder, 'log.csv')

        if self.logging:
            # initialize the status dict yaml file
            self.status_dict = {'cycle_no': None, 'process': None, 'start_time': self.start, 'cycle_start_time': None}
            write_status_dict_to_file(self.status_dict_path, self.status_dict)
            # initialize the log file
            log = {'timestamp': [], 'cycle_no': [], 'process': [], 'event': [], 'level': []}
            df = pd.DataFrame(log, columns=['timestamp', 'cycle_no', 'process', 'event', 'level'])
            df.to_csv(self.log_path, index=False, header=True)

        # update the default_info file that is necessary to run the bokeh app
        if self.logging:
            # hybr_list = [item for item in self.hybridization_list if item['time'] is None]
            # photobl_list = [item for item in self.photobleaching_list if item['time'] is None]
            last_roi_number = int(self.roi_names[-1].strip('ROI_'))
            update_default_info(self.default_info_path, self.user_param_dict, self.directory, self.file_format,
                                self.probe_dict, last_roi_number, self.hybridization_list, self.photobleaching_list)
        # logging prepared ---------------------------------------------------------------------------------------------

        # prepare the camera
        self.num_frames = self.num_z_planes * self.num_laserlines
        self.ref['cam'].prepare_camera_for_multichannel_imaging(self.num_frames, self.exposure, None, None, None)

        # initialize a counter to iterate over the number of probes to inject
        self.probe_counter = 0

    def runTaskStep(self):
        """ Implement one work step of your task here.
        :return: bool: True if the task should continue running, False if it should finish.
        """
        # go directly to cleanupTask if position 1 is not defined
        if not self.ref['pos'].origin:
            return False

        if not self.aborted:   # need to add regularly check if the aborted variable was set to True
            now = time.time()
            # info message
            self.probe_counter += 1
            self.log.info(f'Probe number {self.probe_counter}: {self.probe_list[self.probe_counter-1][1]}')

            if self.logging:
                self.status_dict['cycle_no'] = self.probe_counter
                self.status_dict['cycle_start_time'] = now
                write_status_dict_to_file(self.status_dict_path, self.status_dict)
                add_log_entry(self.log_path, self.probe_counter, 0, f'Started cycle {self.probe_counter}', 'info')

            # position the needle in the probe
            self.ref['pos'].start_move_to_target(self.probe_list[self.probe_counter-1][0])
            self.ref['pos'].disable_positioning_actions()  # to disable again the move stage button

        # --------------------------------------------------------------------------------------------------------------
        # Hybridization
        # --------------------------------------------------------------------------------------------------------------
        if not self.aborted:

            if self.logging:
                self.status_dict['process'] = 'Hybridization'
                write_status_dict_to_file(self.status_dict_path, self.status_dict)
                add_log_entry(self.log_path, self.probe_counter, 1, 'Started Hybridization', 'info')

            # position the valves for hybridization sequence
            self.ref['valves'].set_valve_position('b', 2)  # RT rinsing valve: inject probe
            self.ref['valves'].wait_for_idle()
            self.ref['valves'].set_valve_position('c', 2)  # Syringe valve: towards pump
            self.ref['valves'].wait_for_idle()

            # iterate over the steps in the hybridization sequence
            for step in range(len(self.hybridization_list)):
                if self.aborted:
                    break

                self.log.info(f'Hybridisation step {step+1}')
                if self.logging:
                    add_log_entry(self.log_path, self.probe_counter, 1, f'Started injection {step + 1}')

                if self.hybridization_list[step]['product'] is not None:  # an injection step
                    # set the 8 way valve to the position corresponding to the product
                    product = self.hybridization_list[step]['product']
                    valve_pos = self.buffer_dict[product]
                    self.ref['valves'].set_valve_position('a', valve_pos)
                    self.ref['valves'].wait_for_idle()

                    self.log.info(f'Injection of {product} ... ')
                    time.sleep(1)

                    # simulate pressure, volume and flowrate data and save these data ----------------------------------
                    pressure = [0]
                    volume = [0]
                    flowrate = [0]

                    for i in range(100):
                        new_pressure = np.random.normal()
                        pressure.append(new_pressure)
                        new_volume = abs(np.random.normal()) + volume[i]
                        volume.append(new_volume)
                        new_flowrate = np.random.normal() + 150
                        flowrate.append(new_flowrate)

                    complete_path = create_path_for_injection_data(self.directory, self.probe_list[self.probe_counter-1][1], 'hybridization', step)
                    save_injection_data_to_csv(pressure, volume, flowrate, complete_path)
                    # end of simulate pressure, volume and flowrate data and save these data ---------------------------

                else:  # an incubation step
                    t = self.hybridization_list[step]['time']
                    self.log.info(f'Incubation time.. {t} s')
                    self.ref['valves'].set_valve_position('c', 1)
                    self.ref['valves'].wait_for_idle()

                    # allow abort by splitting the waiting time into small intervals of 30 s
                    num_steps = t // 30
                    remainder = t % 30
                    for i in range(num_steps):
                        if not self.aborted:
                            time.sleep(30)
                    time.sleep(remainder)

                    self.ref['valves'].set_valve_position('c', 2)
                    self.ref['valves'].wait_for_idle()
                    self.log.info('Incubation time finished')

                if self.logging:
                    add_log_entry(self.log_path, self.probe_counter, 1, f'Finished injection {step + 1}')

            # set valves to default positions
            self.ref['valves'].set_valve_position('a', 1)  # 8 way valve
            self.ref['valves'].wait_for_idle()
            self.ref['valves'].set_valve_position('b', 1)  # RT rinsing valve: Rinse needle
            self.ref['valves'].wait_for_idle()
            self.ref['valves'].set_valve_position('c', 1)  # Syringe valve: towards syringe
            self.ref['valves'].wait_for_idle()

            if self.logging:
                add_log_entry(self.log_path, self.probe_counter, 1, 'Finished Hybridization', 'info')
        # Hybridization finished ---------------------------------------------------------------------------------------

        # --------------------------------------------------------------------------------------------------------------
        # Imaging for all ROI
        # --------------------------------------------------------------------------------------------------------------
        if not self.aborted:

            if self.logging:
                self.status_dict['process'] = 'Imaging'
                write_status_dict_to_file(self.status_dict_path, self.status_dict)
                add_log_entry(self.log_path, self.probe_counter, 2, 'Started Imaging', 'info')

            # iterate over all ROIs
            for item in self.roi_names:
                if self.aborted:
                    break

                # create the save path for each roi --------------------------------------------------------------------
                cur_save_path = self.get_complete_path(self.directory, item, self.probe_list[self.probe_counter-1][1])

                # move to roi ------------------------------------------------------------------------------------------
                self.ref['roi'].active_roi = None
                self.ref['roi'].set_active_roi(name=item)
                self.ref['roi'].go_to_roi()
                self.log.info('Moved to {}'.format(item))
                self.ref['roi'].stage_wait_for_idle()
                if self.logging:
                    add_log_entry(self.log_path, self.probe_counter, 2, f'Moved to {item}')

                # autofocus ------------------------------------------------------------------------------------------------
                # self.ref['focus'].start_search_focus()
                reference_position = self.ref['focus'].get_position() + np.random.normal()  # save it to go back to this plane after imaging
                # for simulatied task only
                self.ref['focus'].go_to_position(reference_position)
                start_position = self.calculate_start_position(self.centered_focal_plane)

                # imaging sequence -----------------------------------------------------------------------------------------
                # self.ref['cam'].stop_acquisition()   # for safety
                # self.ref['cam'].start_acquisition()

                # initialize arrays to save the target and current z positions
                z_target_positions = []
                z_actual_positions = []

                # iterate over all planes in z
                for plane in tqdm(range(self.num_z_planes)):

                    # position the piezo
                    position = start_position + plane * self.z_step
                    self.ref['focus'].go_to_position(position)
                    # print(f'target position: {position} um')
                    time.sleep(0.03)
                    cur_pos = self.ref['focus'].get_position()
                    # print(f'current position: {cur_pos} um')
                    z_target_positions.append(position)
                    z_actual_positions.append(cur_pos)

                self.ref['focus'].go_to_position(reference_position)

                # data handling ----------------------------------------------------------------------------------------
                image_data = np.random.normal(size=(self.num_frames, 125, 125))  # self.ref['cam'].get_acquired_data()

                if self.file_format == 'fits':
                    metadata = self.get_fits_metadata()
                    self.ref['cam'].save_to_fits(cur_save_path, image_data, metadata)
                else:  # use tiff as default format
                    self.ref['cam'].save_to_tiff(self.num_frames, cur_save_path, image_data)
                    metadata = self.get_metadata()
                    file_path = cur_save_path.replace('tif', 'yaml', 1)
                    self.save_metadata_file(metadata, file_path)

                # save file with z positions (same procedure for either file format)
                file_path = os.path.join(os.path.split(cur_save_path)[0], 'z_positions.yaml')
                save_z_positions_to_file(z_target_positions, z_actual_positions, file_path)

                if self.logging:  # to modify: check if data saved correctly before writing this log entry
                    add_log_entry(self.log_path, self.probe_counter, 2, 'Image data saved', 'info')

            # go back to first ROI (to avoid a long displacement just before restarting imaging)
            self.ref['roi'].set_active_roi(name=self.roi_names[0])
            self.ref['roi'].go_to_roi_xy()

            if self.logging:
                add_log_entry(self.log_path, self.probe_counter, 2, 'Finished Imaging', 'info')
        # Imaging (for all ROIs) finished ------------------------------------------------------------------------------

        # --------------------------------------------------------------------------------------------------------------
        # Photobleaching
        # --------------------------------------------------------------------------------------------------------------
        if not self.aborted:

            if self.logging:
                self.status_dict['process'] = 'Photobleaching'
                write_status_dict_to_file(self.status_dict_path, self.status_dict)
                add_log_entry(self.log_path, self.probe_counter, 3, 'Started Photobleaching', 'info')

            # position the valves for photobleaching sequence
            self.ref['valves'].set_valve_position('b', 1)  # RT rinsing valve: rinse needle
            self.ref['valves'].wait_for_idle()
            # self.ref['daq'].start_rinsing(60)

            self.ref['valves'].set_valve_position('c', 2)  # Syringe valve: towards pump
            self.ref['valves'].wait_for_idle()

            # iterate over the steps in the photobleaching sequence
            for step in range(len(self.photobleaching_list)):
                if self.aborted:
                    break

                self.log.info(f'Photobleaching step {step+1}')
                if self.logging:
                    add_log_entry(self.log_path, self.probe_counter, 3, f'Started injection {step + 1}')

                if self.photobleaching_list[step]['product'] is not None:  # an injection step
                    # set the 8 way valve to the position corresponding to the product
                    product = self.photobleaching_list[step]['product']
                    valve_pos = self.buffer_dict[product]
                    self.ref['valves'].set_valve_position('a', valve_pos)
                    self.ref['valves'].wait_for_idle()

                    self.log.info(f'Injection of {product} ... ')
                    time.sleep(1)

                    # add here simulated data for pressure value and total volume
                    pressure = [0]
                    volume = [0]
                    flowrate = [0]

                    for i in range(100):
                        new_pressure = np.random.normal()
                        pressure.append(new_pressure)
                        new_volume = abs(np.random.normal()) + volume[i]
                        volume.append(new_volume)
                        new_flowrate = np.random.normal() + 150
                        flowrate.append(new_flowrate)

                    complete_path = create_path_for_injection_data(self.directory, self.probe_list[self.probe_counter-1][1], 'photobleaching', step)
                    save_injection_data_to_csv(pressure, volume, flowrate, complete_path)

                else:  # an incubation step
                    t = self.photobleaching_list[step]['time']
                    self.log.info(f'Incubation time .. {t} s')
                    self.ref['valves'].set_valve_position('c', 1)
                    self.ref['valves'].wait_for_idle()

                    # allow abort by splitting the waiting time into small intervals of 30 s
                    num_steps = t // 30
                    remainder = t % 30
                    for i in range(num_steps):
                        if not self.aborted:
                            time.sleep(30)
                    time.sleep(remainder)

                    self.ref['valves'].set_valve_position('c', 2)
                    self.ref['valves'].wait_for_idle()
                    self.log.info('Incubation time finished')

                if self.logging:
                    add_log_entry(self.log_path, self.probe_counter, 3, f'Finished injection {step + 1}')

            # set valves to default positions
            self.ref['valves'].set_valve_position('a', 1)  # 8 way valve
            self.ref['valves'].wait_for_idle()
            self.ref['valves'].set_valve_position('b', 1)  # RT rinsing valve: Rinse needle
            self.ref['valves'].wait_for_idle()
            self.ref['valves'].set_valve_position('c', 1)  # Syringe valve: towards syringe
            self.ref['valves'].wait_for_idle()

            if self.logging:
                add_log_entry(self.log_path, self.probe_counter, 3, 'Finished Photobleaching', 'info')
        # Photobleaching finished --------------------------------------------------------------------------------------

        if not self.aborted:
            if self.logging:
                add_log_entry(self.log_path, self.probe_counter, 0, f'Finished cycle {self.probe_counter}', 'info')

        return self.probe_counter < len(self.probe_list)

    def pauseTask(self):
        """ """
        self.log.info('pauseTask called')

    def resumeTask(self):
        """ """
        self.log.info('resumeTask called')

    def cleanupTask(self):
        """ """
        self.log.info('cleanupTask called')

        if self.logging:
            try:
                self.status_dict = {}
                write_status_dict_to_file(self.status_dict_path, self.status_dict)
            except Exception:  # in case cleanup task was called before self.status_dict_path is defined
                pass

        if self.aborted:  # some extra actions to reset a proper state in case abort was called
            if self.logging:
                try:
                    add_log_entry(self.log_path, self.probe_counter, 0, 'Task was aborted.', level='warning')
                except Exception:
                    pass

            # in real experiment: stop the pressure regulation  and set pressure to 0
            # set valves to default positions
            self.ref['valves'].set_valve_position('a', 1)  # 8 way valve
            self.ref['valves'].wait_for_idle()
            self.ref['valves'].set_valve_position('b', 1)  # RT rinsing valve: Rinse needle
            self.ref['valves'].wait_for_idle()
            self.ref['valves'].set_valve_position('c', 1)  # Syringe valve: towards syringe
            self.ref['valves'].wait_for_idle()

        # reset the camera to default state
        self.ref['cam'].reset_camera_after_multichannel_imaging()
        self.ref['cam'].set_exposure(self.default_exposure)

        # reset stage velocity to default
        self.ref['roi'].set_stage_velocity({'x': 6, 'y': 6})  # 5.74592

        # enable gui actions
        # roi gui
        self.ref['roi'].enable_tracking_mode()
        self.ref['roi'].enable_roi_actions()
        # basic imaging gui
        self.ref['cam'].enable_camera_actions()
        self.ref['laser'].enable_laser_actions()
        self.ref['valves'].enable_valve_positioning()
        self.ref['flow'].enable_flowcontrol_actions()
        self.ref['pos'].enable_positioning_actions()

        total = time.time() - self.start
        print(f'total time with logging = {self.logging}: {total} s')

        self.log.info('cleanupTask finished')

    # ==================================================================================================================
    # Helper functions
    # ==================================================================================================================

    # ------------------------------------------------------------------------------------------------------------------
    # user parameters
    # ------------------------------------------------------------------------------------------------------------------

    def load_user_parameters(self):
        """ This function is called from startTask() to load the parameters given by the user in a specific format.

        Specify the path to the user defined config for this task in the (global) config of the experimental setup.

        user must specify the following dictionary (here with example entries):
            sample_name: 'Mysample'
            exposure: 0.05  # in s
            num_z_planes: 50
            z_step: 0.25  # in um
            centered_focal_plane: False
            imaging_sequence: [('488 nm', 3), ('561 nm', 3), ('641 nm', 10)]
            save_path: 'E:/'
            file_format: 'tif'
            roi_list_path: 'pathstem/qudi_files/qudi_roi_lists/roilist_20210101_1128_23_123243.json'
            injections_path: 'pathstem/qudi_files/qudi_injection_parameters/injections_2021_01_01.yml'
            dapi_path: 'E:/imagedata/2021_01_01/001_HiM_MySample_dapi'
        """
        try:
            with open(self.user_config_path, 'r') as stream:
                self.user_param_dict = yaml.safe_load(stream)

                self.sample_name = self.user_param_dict['sample_name']
                self.exposure = self.user_param_dict['exposure']
                self.num_z_planes = self.user_param_dict['num_z_planes']
                self.z_step = self.user_param_dict['z_step']  # in um
                self.centered_focal_plane = self.user_param_dict['centered_focal_plane']
                self.imaging_sequence = self.user_param_dict['imaging_sequence']
                self.save_path = self.user_param_dict['save_path']
                self.file_format = self.user_param_dict['file_format']
                self.roi_list_path = self.user_param_dict['roi_list_path']
                self.injections_path = self.user_param_dict['injections_path']
                self.dapi_path = self.user_param_dict['dapi_path']

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')

        # establish further user parameters derived from the given ones

        # load rois from file and create a list ------------------------------------------------------------------------
        self.ref['roi'].load_roi_list(self.roi_list_path)
        self.roi_names = self.ref['roi'].roi_names

        # imaging ------------------------------------------------------------------------------------------------------
        self.num_laserlines = len(self.imaging_sequence)
        # not needed for dummy him task (maybe for metadata..)
        self.wavelengths = [self.imaging_sequence[i][0] for i, item in enumerate(self.imaging_sequence)]
        self.intensities = [self.imaging_sequence[i][1] for i, item in enumerate(self.imaging_sequence)]

        # injections ---------------------------------------------------------------------------------------------------
        self.load_injection_parameters()

        self.log.info('user parameters loaded and processed')

    def load_injection_parameters(self):
        """ Load relevant information from the document containing the injection parameters in a specific format.
        This document is configured using the Qudi injections module to obtain the correct format.
        It is a dictionary with keys 'buffer', 'probes', 'hybridization list' and 'photobleaching list'.
        'buffer' and 'probes' contain themselves subdictionaries as value.
        """
        try:
            with open(self.injections_path, 'r') as stream:
                documents = yaml.safe_load(stream)  # yaml.full_load when yaml package updated
                buffer_dict = documents['buffer']
                self.probe_dict = documents['probes']
                self.hybridization_list = documents['hybridization list']
                self.photobleaching_list = documents['photobleaching list']

            # invert the buffer dict to address the valve by the product name as key
            self.buffer_dict = dict([(value, key) for key, value in buffer_dict.items()])
            # create a list out of probe_dict and order by ascending position
            # (for example: probes in pos 2, 5, 6, 9, 10 is ok but not 10, 2, 5, 6, 9)
            self.probe_list = sorted(self.probe_dict.items())  # list of tuples, such as [(1, 'RT1'), (2, 'RT2')]

        except Exception as e:
            self.log.warning(f'Could not load hybridization sequence for task {self.name}: {e}')

    def calculate_start_position(self, centered_focal_plane):
        """
        This method calculates the piezo position at which the z stack will start. It can either start in the
        current plane or calculate an offset so that the current plane will be centered inside the stack.

        :param: bool centered_focal_plane: indicates if the scan is done below and above the focal plane (True)
                                            or if the focal plane is the bottommost plane in the scan (False)

        :return: float piezo start position
        """
        current_pos = self.ref['focus'].get_position()

        if centered_focal_plane:  # the scan should start below the current position so that the focal plane will be the central plane or one of the central planes in case of an even number of planes
            # even number of planes:
            if self.num_z_planes % 2 == 0:
                start_pos = current_pos - self.num_z_planes / 2 * self.z_step  # focal plane is the first one of the upper half of the number of planes
            # odd number of planes:
            else:
                start_pos = current_pos - (self.num_z_planes - 1)/2 * self.z_step
            return start_pos
        else:
            return current_pos  # the scan starts at the current position and moves up

    # ------------------------------------------------------------------------------------------------------------------
    # file path handling
    # ------------------------------------------------------------------------------------------------------------------

    def create_directory(self, path_stem):
        """ Create the directory (based on path_stem given as user parameter),
        in which the folders for the ROI will be created
        Example: path_stem/YYYY_MM_DD/001_HiM_samplename

        :param: str pathstem
        :return: str path to directory
        """
        cur_date = datetime.today().strftime('%Y_%m_%d')

        path_stem_with_date = os.path.join(path_stem, cur_date)

        # check if folder path_stem_with_date exists, if not: create it
        if not os.path.exists(path_stem_with_date):
            try:
                os.makedirs(path_stem_with_date)  # recursive creation of all directories on the path
            except Exception as e:
                self.log.error('Error {0}'.format(e))

        # count the subdirectories in the directory path (non recursive !) to generate an incremental prefix
        dir_list = [folder for folder in os.listdir(path_stem_with_date) if os.path.isdir(os.path.join(path_stem_with_date, folder))]
        number_dirs = len(dir_list)

        prefix = str(number_dirs+1).zfill(3)
        # make prefix accessible to include it in the filename generated in the method get_complete_path
        self.prefix = prefix

        foldername = f'{prefix}_HiM_{self.sample_name}'

        path = os.path.join(path_stem_with_date, foldername)

        # create the path  # no need to check if it already exists due to incremental prefix
        try:
            os.makedirs(path)  # recursive creation of all directories on the path
        except Exception as e:
            self.log.error('Error {0}'.format(e))

        return path

    def get_complete_path(self, directory, roi_number, probe_number):
        """ Create the complete path for a file containing image data,
        based on the directory for the experiment that was already created,
        the ROI number and the probe number,
        such as directory/ROI_007/RT2/scan_num_RT2_007_ROI.tif

        :param: str directory
        :param: str roi_number: identifier of the current ROI
        :param: str probe_number: identifier of the current RT

        :return: str complete path (as in the example above)
        """
        path = os.path.join(directory, roi_number, probe_number)

        if not os.path.exists(path):
            try:
                os.makedirs(path)  # recursive creation of all directories on the path
            except Exception as e:
                self.log.error('Error {0}'.format(e))

        roi_number_inv = roi_number.strip('ROI_')+'_ROI'  # for compatibility with analysis format

        file_name = f'scan_{self.prefix}_{probe_number}_{roi_number_inv}.{self.file_format}'

        complete_path = os.path.join(path, file_name)
        return complete_path

    # ------------------------------------------------------------------------------------------------------------------
    # metadata
    # ------------------------------------------------------------------------------------------------------------------

    def get_metadata(self):
        """ Get a dictionary containing the metadata in a plain text easy readable format.

        :return: dict metadata
        """
        metadata = {}
        metadata['Sample name'] = self.sample_name
        metadata['Exposure time (s)'] = self.exposure
        metadata['Scan step length (um)'] = self.z_step
        metadata['Scan total length (um)'] = self.z_step * self.num_z_planes
        metadata['Number laserlines'] = self.num_laserlines
        for i in range(self.num_laserlines):
            metadata[f'Laser line {i+1}'] = self.imaging_sequence[i][0]
            metadata[f'Laser intensity {i+1} (%)'] = self.imaging_sequence[i][1]
        # to check where the problem comes from :
        # metadata['x position'] = self.ref['roi'].stage_position[0]
        # metadata['y position'] = self.ref['roi'].stage_position[1]
        # pixel size ???
        return metadata

    def get_fits_metadata(self):
        """ Get a dictionary containing the metadata in a fits header compatible format.

        :return: dict metadata
        """
        metadata = {}
        metadata['SAMPLE'] = (self.sample_name, 'sample name')
        metadata['EXPOSURE'] = (self.exposure, 'exposure time (s)')
        metadata['Z_STEP'] = (self.z_step, 'scan step length (um)')
        metadata['Z_TOTAL'] = (self.z_step * self.num_z_planes, 'scan total length (um)')
        metadata['CHANNELS'] = (self.num_laserlines, 'number laserlines')
        for i in range(self.num_laserlines):
            metadata[f'LINE{i+1}'] = (self.imaging_sequence[i][0], f'laser line {i+1}')
            metadata[f'INTENS{i+1}'] = (self.imaging_sequence[i][1], f'laser intensity {i+1}')
        metadata['X_POS'] = (self.ref['roi'].stage_position[0], 'x position')
        metadata['Y_POS'] = (self.ref['roi'].stage_position[1], 'y position')
        # pixel size
        return metadata

    def save_metadata_file(self, metadata, path):
        """ Save a txt file containing the metadata dictionary.

        :param dict metadata: dictionary containing the metadata
        :param str path: pathname
        """
        with open(path, 'w') as outfile:
            yaml.safe_dump(metadata, outfile, default_flow_style=False)
        self.log.info('Saved metadata to {}'.format(path))
