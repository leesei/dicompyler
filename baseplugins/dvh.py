#!/usr/bin/env python
# -*- coding: ISO-8859-1 -*-
# dvh.py
"""dicompyler plugin that displays a dose volume histogram (DVH)
    with adjustable constraints via wxPython and matplotlib."""
# Copyright (c) 2009-2010 Aditya Panchal
# This file is part of dicompyler, relased under a BSD license.
#    See the file license.txt included with this distribution, also
#    available at http://code.google.com/p/dicompyler/
#
# It is assumed that the reference (prescription) dose is in cGy.

import wx
from wx.xrc import XmlResource, XRCCTRL, XRCID
from wx.lib.pubsub import Publisher as pub
import guiutil, util
import wxmpl
import numpy as np
import dvhdata, guidvh

def pluginProperties():
    """Properties of the plugin."""

    props = {}
    props['name'] = 'DVH'
    props['description'] = "Display and evaluate dose volume histogram (DVH) data"
    props['author'] = 'Aditya Panchal'
    props['version'] = 0.2
    props['plugin_type'] = 'main'
    props['plugin_version'] = 1
    props['min_dicom'] = ['rtss', 'rtdose']
    props['recommended_dicom'] = ['rtss', 'rtdose', 'rtplan']

    return props

def pluginLoader(parent):
    """Function to load the plugin."""

    # Load the XRC file for our gui resources
    res = XmlResource(util.GetBasePluginsPath('dvh.xrc'))

    panelDVH = res.LoadPanel(parent, 'pluginDVH')
    panelDVH.Init(res)

    return panelDVH

class pluginDVH(wx.Panel):
    """Plugin to display DVH data with adjustable constraints."""

    def __init__(self):
        pre = wx.PrePanel()
        # the Create step is done by XRC.
        self.PostCreate(pre)

    def Init(self, res):
        """Method called after the panel has been initialized."""

        self.guiDVH = guidvh.guiDVH(self)
        res.AttachUnknownControl('panelDVH', self.guiDVH.panelDVH, self)

        # Initialize the Constraint selector controls
        self.radioVolume = XRCCTRL(self, 'radioVolume')
        self.radioDose = XRCCTRL(self, 'radioDose')
        self.radioDosecc = XRCCTRL(self, 'radioDosecc')
        self.txtConstraint = XRCCTRL(self, 'txtConstraint')
        self.sliderConstraint = XRCCTRL(self, 'sliderConstraint')
        self.lblConstraintUnits = XRCCTRL(self, 'lblConstraintUnits')
        self.lblConstraintPercent = XRCCTRL(self, 'lblConstraintPercent')

        # Initialize the Constraint selector labels
        self.lblConstraintType = XRCCTRL(self, 'lblConstraintType')
        self.lblConstraintTypeUnits = XRCCTRL(self, 'lblConstraintTypeUnits')
        self.lblConstraintResultUnits = XRCCTRL(self, 'lblConstraintResultUnits')

        # Bind ui events to the proper methods
        wx.EVT_RADIOBUTTON(self, XRCID('radioVolume'), self.OnToggleConstraints)
        wx.EVT_RADIOBUTTON(self, XRCID('radioDose'), self.OnToggleConstraints)
        wx.EVT_RADIOBUTTON(self, XRCID('radioDosecc'), self.OnToggleConstraints)
        wx.EVT_SPINCTRL(self, XRCID('txtConstraint'), self.OnChangeConstraint)
        wx.EVT_COMMAND_SCROLL_THUMBTRACK(self, XRCID('sliderConstraint'), self.OnChangeConstraint)
        wx.EVT_COMMAND_SCROLL_CHANGED(self, XRCID('sliderConstraint'), self.OnChangeConstraint)

        # Initialize variables
        self.structures = {} # structures from initial DICOM data
        self.checkedstructures = {} # structures that need to be shown
        self.dvhs = {} # raw dvhs from initial DICOM data
        self.dvhdata = {} # dict of dvh constraint functions
        self.dvharray = {} # dict of dvh data processed from dvhdata
        self.plan = {} # used for rx dose
        self.structureid = 1 # used to indicate current constraint structure

        self.EnableConstraints(False)

        # Set up pubsub
        pub.subscribe(self.OnUpdatePatient, 'patient.updated.parsed_data')
        pub.subscribe(self.OnStructureCheck, 'structures.checked')
        pub.subscribe(self.OnStructureSelect, 'structure.selected')

    def OnUpdatePatient(self, msg):
        """Update and load the patient data."""

        self.structures = msg.data['structures']
        self.dvhs = msg.data['dvhs']
        self.plan = msg.data['plan']
        # show an empty plot when (re)loading a patient
        self.guiDVH.Replot()

    def OnStructureCheck(self, msg):
        """When a structure changes, update the interface and plot."""

        # Make sure that the volume has been calculated for each structure
        # before setting it
        self.checkedstructures = msg.data
        for id, structure in self.checkedstructures.iteritems():
            if not self.structures[id].has_key('volume'):
                self.structures[id]['volume'] = structure['volume']

            # make sure that the dvh has been calculated for each structure
            # before setting it
            if self.dvhs.has_key(id):
                self.EnableConstraints(True)
                # Create an instance of the dvhdata class to can access its functions
                self.dvhdata[id] = dvhdata.DVH(self.dvhs[id])
                # Create an instance of the dvh arrays so that guidvh can plot it
                self.dvharray[id] = dvhdata.DVH(self.dvhs[id]).dvh
                # 'Toggle' the radio box to refresh the dose data
                self.OnToggleConstraints(None)
        if not len(self.checkedstructures):
            self.EnableConstraints(False)
            # Make an empty plot on the DVH
            self.guiDVH.Replot(None, None)

    def OnStructureSelect(self, msg):
        """Load the constraints for the currently selected structure."""

        if (msg.data['id'] == None):
            self.EnableConstraints(False)
        else:
            self.structureid = msg.data['id']
            if self.dvhdata.has_key(self.structureid):
                self.OnToggleConstraints(None)
            else:
                self.EnableConstraints(False)
                self.guiDVH.Replot(self.dvharray, self.checkedstructures)

    def EnableConstraints(self, value):
        """Enable or disable the constraint selector."""

        self.radioVolume.Enable(value)
        self.radioDose.Enable(value)
        self.radioDosecc.Enable(value)
        self.txtConstraint.Enable(value)
        self.sliderConstraint.Enable(value)
        if not value:
            self.lblConstraintUnits.SetLabel('-            ')
            self.lblConstraintPercent.SetLabel('-            ')
            self.txtConstraint.SetValue(0)

    def OnToggleConstraints(self, evt):
        """Switch between different constraint modes."""

        # Replot the remaining structures and disable the constraints
        # if a structure that has no DVH calculated is selected
        if not self.dvhs.has_key(self.structureid):
            self.guiDVH.Replot(self.dvharray, self.checkedstructures)
            self.EnableConstraints(False)
            return
        else:
            self.EnableConstraints(True)

        # Check if the function was called via an event or not
        if not (evt == None):
            label = evt.GetEventObject().GetLabel()
        else:
            if self.radioVolume.GetValue():
                label = 'Volume Constraint (V__)'
            elif self.radioDose.GetValue():
                label = 'Dose Constraint (D__)'
            elif self.radioDosecc.GetValue():
                label = 'Dose Constraint (D__cc)'

        constraintrange = 0
        if (label == 'Volume Constraint (V__)'):
            self.lblConstraintType.SetLabel('   Dose:')
            self.lblConstraintTypeUnits.SetLabel('%  ')
            self.lblConstraintResultUnits.SetLabel(u'cm�')
            rxDose = float(self.plan['rxdose'])
            dvhdata = len(self.dvhs[self.structureid]['data'])
            constraintrange = int(dvhdata*100/rxDose)
            # never go over the max dose as data does not exist
            if (constraintrange > int(self.dvhs[self.structureid]['max'])):
                constraintrange = int(self.dvhs[self.structureid]['max'])
        elif (label == 'Dose Constraint (D__)'):
            self.lblConstraintType.SetLabel('Volume:')
            self.lblConstraintTypeUnits.SetLabel(u'%  ')
            self.lblConstraintResultUnits.SetLabel(u'cGy')
            constraintrange = 100
        elif (label == 'Dose Constraint (D__cc)'):
            self.lblConstraintType.SetLabel('Volume:')
            self.lblConstraintTypeUnits.SetLabel(u'cm�')
            self.lblConstraintResultUnits.SetLabel(u'cGy')
            constraintrange = int(self.structures[self.structureid]['volume'])

        self.sliderConstraint.SetRange(0, constraintrange)
        self.sliderConstraint.SetValue(constraintrange)
        self.txtConstraint.SetRange(0, constraintrange)
        self.txtConstraint.SetValue(constraintrange)

        self.OnChangeConstraint(None)

    def OnChangeConstraint(self, evt):
        """Update the results when the constraint value changes."""

        # Check if the function was called via an event or not
        if not (evt == None):
            slidervalue = evt.GetInt()
        else:
            slidervalue = self.sliderConstraint.GetValue()

        self.txtConstraint.SetValue(slidervalue)
        self.sliderConstraint.SetValue(slidervalue)
        rxDose = self.plan['rxdose']
        id = self.structureid

        if self.radioVolume.GetValue():
            absDose = rxDose * slidervalue / 100
            volume = self.structures[self.structureid]['volume']
            cc = self.dvhdata[id].GetVolumeConstraintCC(absDose, volume)
            constraint = self.dvhdata[id].GetVolumeConstraint(absDose)

            self.lblConstraintUnits.SetLabel("%.3f" % cc)
            self.lblConstraintPercent.SetLabel("%.3f" % constraint)
            self.guiDVH.Replot(self.dvharray, self.checkedstructures,
                ([absDose], [constraint]), id)

        elif self.radioDose.GetValue():
            dose = self.dvhdata[id].GetDoseConstraint(slidervalue)

            self.lblConstraintUnits.SetLabel("%.3f" % dose)
            self.lblConstraintPercent.SetLabel("%.3f" % (dose*100/rxDose))
            self.guiDVH.Replot(self.dvharray, self.checkedstructures,
                ([dose], [slidervalue]), id)

        elif self.radioDosecc.GetValue():
            volumepercent = slidervalue*100/self.structures[self.structureid]['volume']

            dose = self.dvhdata[id].GetDoseConstraint(volumepercent)

            self.lblConstraintUnits.SetLabel("%.3f" % dose)
            self.lblConstraintPercent.SetLabel("%.3f" % (dose*100/rxDose))
            self.guiDVH.Replot(self.dvharray, self.checkedstructures,
                ([dose], [volumepercent]), id)
