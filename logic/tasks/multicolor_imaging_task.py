# -*- coding: utf-8 -*-
"""
Created on Tue Feb 2 2021

@author: fbarho

This file is an extension to Qudi software
obtained from <https://github.com/Ulm-IQO/qudi/>

Task to perform multicolor imaging

Config example pour copy-paste:
    MulticolorImagingTask:
        module: 'multicolor_imaging_task'
        needsmodules:
            camera: 'camera_logic'
            daq: 'daq_ao_logic'
            filter: 'filterwheel_logic'
        config:
            path_to_user_config: '/home/barho/qudi-cbs-user-configs/multichannel_imaging_task.json'
"""
import yaml
from logic.generic_task import InterruptableTask
import json
from datetime import datetime
import os
import numpy as np
from time import sleep
import numpy as np


class Task(InterruptableTask):  # do not change the name of the class. it is always called Task !
    """ This task does an acquisition of a series of images from different channels or using different intensities
    """

    filter_pos = None
    imaging_sequence = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print('Task {0} added!'.format(self.name))
        # self.laser_allowed = False
        self.user_config_path = self.config['path_to_user_config']
        self.log.info('Task {0} using the configuration at {1}'.format(self.name, self.user_config_path))

    def startTask(self):
        """ """
        # control if live mode in basic gui is running. Task can not be started then.
        if self.ref['camera'].enabled:
            self.log.info('Task cannot be started: Please stop live mode first')
            # calling self.cleanupTask() here does not seem to guarantee that the taskstep is not performed. so put an additional safety check in taskstep
            return
        # control if video saving is currently running
        if self.ref['camera'].saving:
            self.log.info('Task cannot be started: Wait until saving finished')
            return
        
        
        self._load_user_parameters()
        
        
        # # control the config : laser allowed for given filter ?
        # self.laser_allowed = self._control_user_parameters()
        #
        # if not self.laser_allowed:
        #     self.log.warning('Task aborted. Please specify a valid filter / laser combination')
        #     return
        
        ### all conditions to start the task have been tested: Task can now be started safely   
        
        # set the filter to the specified position
        self.ref['filter'].set_position(self.filter_pos)
        # use only one filter. do not allow changing filter because this will be too slow
        # wait until filter position set
        pos = self.ref['filter'].get_position()
        while not pos == self.filter_pos:
            sleep(1)
            pos = self.ref['filter'].get_position()

        # initialize the digital output channel for trigger
        self.ref['daq'].set_up_do_channel()
        
        # initialize the analog input channel that reads the fire
        self.ref['daq'].set_up_ai_channel()
        
        self.err_count = 0  # initialize the error counter


        # prepare the camera  # this version is quite specific for andor camera -- implement compatibility later on
        self.ref['camera'].abort_acquisition()  # as safety
        self.ref['camera'].set_acquisition_mode('KINETICS')
        self.ref['camera'].set_trigger_mode('EXTERNAL')  
        # add eventually other settings that may be read from user config .. frame transfer etc. 
        self.ref['camera'].set_gain(self.gain)
        # set the exposure time
        self.ref['camera'].set_exposure(self.exposure) 
        # set the number of frames
        frames = len(self.imaging_sequence) * self.num_frames # num_frames: number of frames per channel
        self.ref['camera'].set_number_kinetics(frames)  # lets assume a single image per channel for this first version
        
        # set spooling
        # define save path
        complete_path = self.ref['camera']._create_generic_filename(self.save_path, '_Stack', 'testimg', '', False)
        
        if self.file_format == 'fits':
            self.ref['camera'].set_spool(1, 5, complete_path, 10)
        else:  # use 'tiff' as default case # add other options 
            self.ref['camera'].set_spool(1, 7, complete_path, 10)
        
        # open the shutter
        self.ref['camera'].set_shutter(0, 1, 0.1, 0.1)
        sleep(1)  # wait until shutter is opened
        # start the acquisition. Camera waits for trigger
        self.ref['camera'].start_acquisition()      


    def runTaskStep(self):
        """ Implement one work step of your task here.
        @return bool: True if the task should continue running, False if it should finish.
        """
        # control if live mode in basic gui is running. Taskstep will not be run then.
        if self.ref['camera'].enabled:
            return False
        # control if video saving is currently running
        if self.ref['camera'].saving:
            return False
        # add similar control for all other criteria
        # .. 
        
        
        # this task only has one step until a data set is prepared and saved (but loops over the channels)
        for i in range(len(self.imaging_sequence)):
            # reset the intensity dict to zero
            self.ref['daq'].reset_intensity_dict()
            # prepare the output value for the specified channel
            self.ref['daq'].update_intensity_dict(self.imaging_sequence[i][0], self.imaging_sequence[i][1])
            intensity_dict = self.ref['daq']._intensity_dict
            # waiting time for stability
            sleep(0.05)
            
            # inner loop over the number of frames per color
            for j in range(self.num_frames):
                # switch the laser on and send the trigger to the camera
                self.ref['daq'].apply_voltage()
                err = self.ref['daq'].send_trigger_and_control_ai()  
            
                # read fire signal of camera and switch of when low signal
                ai_read = self.ref['daq'].read_ai_channel()
                while not ai_read <= 2.5:
                    sleep(0.001)  # read every ms
                    ai_read = self.ref['daq'].read_ai_channel() 
                self.ref['daq'].voltage_off()
            
                # waiting time for stability
                sleep(0.05) 
            
                # repeat the (outer) loop if not all data acquired
                if err < 0:
                    self.err_count += 1  # control value to check how often a trigger was missed
                    i = 0
                    return True  # then the TaskStep will be repeated
            
        # to do: add metadata as header if fits format or as additional file if tiff format
        
        return False

    def pauseTask(self):
        """ """
        self.log.info('pauseTask called')

    def resumeTask(self):
        """ """
        self.log.info('resumeTask called')

    def cleanupTask(self):
        """ """
        self.ref['daq'].voltage_off()  # as security
        self.ref['daq'].reset_intensity_dict()
        self.ref['daq'].close_do_task()
        self.ref['daq'].close_ai_task()
        self.ref['camera'].abort_acquisition()
        self.ref['camera'].set_spool(0, 7, '', 10)
        self.ref['camera'].set_acquisition_mode('RUN_TILL_ABORT')
        self.ref['camera'].set_trigger_mode('INTERNAL') 
        # reactivate later. For tests avoid opening and closing all the time
        # self.ref['camera'].set_shutter(0, 0, 0.1, 0.1)
        self.log.debug(f'number of missed triggers: {self.err_count}')
        self.log.info('cleanupTask called')

    def _load_user_parameters(self):
        """ this function is called from startTask() to load the parameters given in a specified format by the user

        specify only the path to the user defined config in the (global) config of the experimental setup

        user must specify the following dictionary (here with example entries):
            save_path: '/home/barho/myfolder'
            num_planes: 15
            step: 5  # in um
            lightsource: 'laser1'
            intensity: 10
            filter_pos: 2
            n_frames: 5
            activate_display: 1
        """
        # this will be replaced by values read from a config
#        self.filter_pos = 1
#        self.exposure = 0.05  # in s
#        self.gain = 50
#        self.num_frames = 5
#        self.save_path = 'C:\\Users\\admin\\imagetest\\testmulticolorstack'
#        self.file_format = 'fits'
#        self.imaging_sequence = [('488 nm', 3), ('561 nm', 3), ('641 nm', 10)] 
        # a dictionary is not a good option for the imaging sequence. is a list better ? preserve order (dictionary would do as well), allows repeated entries
        
        
        
        try:
            with open(self.user_config_path, 'r') as stream:
                self.user_param_dict = yaml.safe_load(stream)
                
#                self.log.info(self.user_param_dict)
                self.filter_pos = self.user_param_dict['filter_pos']
                self.exposure = self.user_param_dict['exposure']
                self.gain = self.user_param_dict['gain']
                self.num_frames = self.user_param_dict['num_frames']
                self.save_path = self.user_param_dict['save_path']
                self.imaging_sequence = self.user_param_dict['imaging_sequence']
                self.log.info(self.imaging_sequence)  # remove after tests
                self.file_format = 'fits'
                
                
                
        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')
                
                
        # now we need to access the corresponding labels
        laser_dict = self.ref['daq'].get_laser_dict()
        imaging_sequence = [(*get_entry_nested_dict(laser_dict, self.imaging_sequence[i][0], 'label'), self.imaging_sequence[i][1]) for i in range(len(self.imaging_sequence))]
        self.log.info(imaging_sequence)
        self.imaging_sequence = imaging_sequence
        # new format should be self.imaging_sequence = [('laser2', 10), ('laser2', 20), ('laser3', 10)]

#    def _control_user_parameters(self):
#        """ this function checks if the specified laser is allowed given the filter setting
#        @return bool: valid ?"""
#        filterpos = self.filter_pos
#        key = 'filter{}'.format(filterpos)
#        filterdict = self.ref['filter'].get_filter_dict()
#        laserlist = filterdict[key]['lasers']  # returns a list of boolean elements, laser allowed ?
#        # this part should be improved using a correct addressing of the element
#        laser = self.lightsource
#        laser_index = int(laser.strip('laser'))-1
#        ##########
#        return laserlist[laser_index]




def get_entry_nested_dict(nested_dict, val, entry):
    """ helper function that searches for 'val' as value in a nested dictionary and returns the corresponding value in the category 'entry'
    example: search in laser_dict (nested_dict) for the label (entry) corresponding to a given wavelength (val)
    search in filter_dict (nested_dict) for the label (entry) corresponding to a given filter position (val)

    @param: dict nested dict
    @param: val: any data type, value that is searched for in the dictionary
    @param: str entry: key in the inner dictionary whose value needs to be accessed

    note that this function is not the typical way how dictionaries should be used. due to the unambiguity in the dictionaries used here,
    it can however be useful to try to find a key given a value.
    so in practical cases, list will consist of a single element only. """
    list = []
    for outer_key in nested_dict:
        item = [nested_dict[outer_key][entry] for inner_key, value in nested_dict[outer_key].items() if val == value]
        if item != []:
            list.append(*item)
    return list
