import sys
import numpy as np
import pickle
import easydict
import copy
import json
import csv
import os

import preprocessing
from edfreader import read_edf

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtWebEngineWidgets import *

from bokeh.plotting import *
from bokeh.models import *
from bokeh.transform import *
from bokeh import events
from bokeh import palettes
from bokeh.resources import CDN
from bokeh.embed import file_html
from bokeh.layouts import row, column

DATA = {}
METADATA = {}


def JsonLoadsCheck(read, origin):
    # This function simply reads JSON, and makes sure a wrong file will not crash the program
    try:
        return json.loads(read)
    except json.decoder.JSONDecodeError:
        origin.log.insertPlainText('ERROR : JSON READ ERROR(The JSON contains mistakes : Replaced content with empty dict, might cause errors)\n')
        return dict()


def GetNestedDic(dic, keys):
    # A tiny function to get values from dictionnaries nested into each other using a list of strings like an adress
    # If the dictionnary doens't exists, it creates an empty one
    for key in keys:
        try:
            dic = dic[key]
        except KeyError:
            dic[key] = dict()
            dic = dic[key]
    return dic


def SortPlotVariables(origin, settings):
    # This functions checks what variables are available for plottings and adds them as plottable variables
    # The condition being that the length of a list of numbers, must be the same as the length of time
    def rec_check(plot_variables, settings, lg, addr):
        for setting in settings:
            var = GetNestedDic(origin.CleanDATA[0], (addr + setting).split('.'))
            if type(var) is dict:
                rec_check(plot_variables, list(var.keys()), lg, setting + '.')
            elif type(var) is np.ndarray:
                if len(var) == lg:
                    plot_variables.append(addr + setting)
            elif type(var) is list and var:
                if type(var[0]) in [int, float] and len(var) == lg:
                    plot_variables.append(addr + setting)

    if 'time' not in settings:
        origin.check = False
        return
    origin.check = True
    lg = len(origin.CleanDATA[0]['time'])
    plot_variables = list()
    rec_check(plot_variables, settings, lg, '')

    origin.lock = True
    origin.plot_variables = plot_variables
    origin.dpdw1.clear()
    origin.dpdw2.clear()
    origin.dpdw3.clear()
    origin.dpdw1.addItems(origin.plot_variables)
    origin.dpdw2.addItems(origin.plot_variables)
    origin.dpdw3.addItems(origin.plot_variables)
    origin.lock = False


def FillTree(widget, value):
    # This function clears a PyQt Tree Widget, and then fills it with a dictionnary effectively updating it
    # It then calls a recursive function to go through the entire dictionnary and adds in every individual item
    def filltreeitem(item, value):
        item.setExpanded(True)
        i = 0
        if type(value) in [dict, easydict.EasyDict]:
            for key, val in value.items():
                child = QTreeWidgetItem()
                child.setText(0, str(key))
                item.addChild(child)
                filltreeitem(child, val)
        elif type(value) is list:
            for val in value:
                i += 1
                child = QTreeWidgetItem()
                item.addChild(child)
                if type(val) in [dict, easydict.EasyDict]:
                    child.setText(0, str(i) + ' - [dict]')
                    filltreeitem(child, val)
                elif type(val) is list:
                    child.setText(0, str(i) + ' - [list]')
                    filltreeitem(child, val)
                else:
                    child.setText(0, str(val))
                child.setExpanded(True)
        else:
            child = QTreeWidgetItem()
            child.setText(0, str(value))
            item.addChild(child)
    widget.clear()
    filltreeitem(widget.invisibleRootItem(), value)


def UpdatePlot(origin):
    def assigncdsvalues(origin, idx):
        cdsvalues = {}
        texts = [origin.dpdw1.currentText(),
                 origin.dpdw2.currentText(), origin.dpdw3.currentText()]
        for k in texts:
                cdsvalues[k] = GetNestedDic(origin.CacheDATA[idx], k.split('.'))
        return cdsvalues
    w = 500
    h = 500
    # Check some conditions to make that the plot can be created
    if origin.lock is True:
        return
    elif origin.check is False:
        origin.htmlreader.setHtml('The time must be selected in order to generate the plot!')
        return
    elif len(origin.plot_variables) == 0:
        origin.htmlreader.setHtml('No readable value selected!')
        return
    idx = origin.index.value() - 1
    # Creates a new filtered ColumnDataSource (custom data format for bokeh) with a copy of the selected values
    cdsvalues = assigncdsvalues(origin, idx)

    # Creates the color range
    color = linear_cmap(origin.dpdw3.currentText(), 'Plasma256',
                        np.nanmin(cdsvalues[origin.dpdw3.currentText()]),
                        np.nanmax(cdsvalues[origin.dpdw3.currentText()]))
    # Set the name of the plot axis according to
    # the selected values in x and y axis
    xaxis = origin.dpdw1.currentText()
    yaxis = origin.dpdw2.currentText()
    # Create the Bokeh plot, and adds the values as dots inside of it.
    p = figure(plot_width=w, plot_height=h, toolbar_location="above",
               tools='pan,wheel_zoom,box_zoom,reset,hover,crosshair')
    plot = column(p, width=w, height=h)
    p.circle(x=xaxis, y=yaxis, source=cdsvalues, line_color=color, fill_color=color)
    # Put label with the name of selected axis on the plot + flip if need be
    p.xaxis.axis_label = xaxis.upper()
    p.yaxis.axis_label = yaxis.upper()
    p.y_range.flipped = origin.flipy.isChecked()
    # Transforms the bokeh plot into an HTML file,
    # and assign this file to the PyQt HTML reader
    html = file_html(plot, CDN)
    origin.htmlreader.setHtml(html)


def Cleaner(origin, data, settings, addr):
    # Recursive functions goes throught a dictionnary (CleanData, wich is initially a copy of CacheData)
    # Then it reads all the selected variables, checking what is selected or not
    # Finally it removes every unwanted variables that wasn't selected by the user
    # (Like unselected Data that was calculated because it was needed for a selected one)
    tmp = copy.copy(data)
    for elem in tmp:
        if type(tmp) is not dict:
            Cleaner(origin, elem, settings, '')
        else:
            var = GetNestedDic(origin.variables, (addr + elem).split('.'))
            if (list(var.keys()) != ['desc', 'func', 'name', 'reqs']):
                    Cleaner(origin, tmp[elem], settings, addr + elem + '.')
                    if not data[elem]:
                        del data[elem]
            elif addr + elem not in settings:
                del data[elem]


def ComputeVariable(origin, setting, dic):
    def ChangeValue(dic, val, keys):
        for key in keys:
            if key != keys[-1]:
                dic = dic[key]
            else:
                dic[key] = val

    reqs = GetNestedDic(origin.variables, (setting + '.reqs').split('.'))
    for req in reqs:
        reqval = GetNestedDic(dic[0], req.split('.'))
        if type(reqval) is np.ndarray:
            if reqval.size == 0:
                tmp = ComputeVariable(origin, req, dic)
                if tmp:
                    return (tmp + ' for ' + setting)
        elif not reqval:
            tmp = ComputeVariable(origin, req, dic)
            if tmp:
                return (tmp + ' for ' + setting)

    function = GetNestedDic(origin.variables, (setting + '.func').split('.'))
    if function == {}:
        return (setting)
    if function == 'NONE':
        return
    function = getattr(preprocessing, function)

    for k in dic:
        args = []
        for req in reqs:
            args.append(GetNestedDic(k, req.split('.')))
        try:
            value = function(*args)
            if value:
                ChangeValue(k, value, setting.split('.'))
        except TypeError:
            return


def CreateVariables(origin, data, settingslist):
    ret = copy.deepcopy(data)
    for setting in settingslist:
        check = GetNestedDic(origin.variables, setting.split('.'))
        if type(check) is dict:
            if (list(check.keys()) != ['desc', 'func', 'name', 'reqs']):
                continue
        tmp = ComputeVariable(origin, setting, ret)
        if tmp:
            return tmp
    return ret


def GatherSettings(origin):
    def recurse(parent_item, parent_str):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            grand_children = child.childCount()
            if grand_children > 0:
                recurse(child, parent_str + child.text(0) + '.')
            if child.checkState(0) == Qt.Checked:
                checked_items.append(parent_str + child.text(0))

    checked_items = []
    recurse(origin.selecttree.invisibleRootItem(), "")
    origin.settings = checked_items


def PushApply(origin):
    # This function is called whenever the user clicks on the Apply button, starting the creation of a data structure
    def CheckUserInput(k, origin):
        if 'Screen' in DATA[k][0]:
            bol = False
            bswc, bshc, bvd = False, False, False
            if 'screen_width_cm' not in DATA[k][0]['Screen']:
                bswc = True
                swc = QInputDialog.getDouble(origin, 'INPUT REQUIRED : Screen Width in cm', k + ':\nScreen Width in cm',
                                             1, -2147483647, 2147483647, 3)
            if 'screen_height_cm' not in DATA[k][0]['Screen']:
                bshc = True
                shc = QInputDialog.getDouble(origin, 'INPUT REQUIRED : Screen Height in cm', k + ':\nScreen Height in cm',
                                             1, -2147483647, 2147483647, 3)
            if 'viewing_Distance_cm' not in DATA[k][0]['Screen']:
                bvd = True
                vd = QInputDialog.getDouble(origin, 'INPUT REQUIRED : User/Screen distance in cm', k + ':\nUser/Screen distance in cm',
                                            1, -2147483647, 2147483647, 3)
        else:
            bol = True
            bswc, bshc, bvd = True, True, True
            swc = QInputDialog.getDouble(origin, 'INPUT REQUIRED : Screen Width in cm', k + ':\nScreen Width in cm',
                                         1, -2147483647, 2147483647, 3)
            shc = QInputDialog.getDouble(origin, 'INPUT REQUIRED : Screen Height in cm', k + ':\nScreen Height in cm',
                                         1, -2147483647, 2147483647, 3)
            vd = QInputDialog.getDouble(origin, 'INPUT REQUIRED : User/Screen distance in cm', k + ':\nUser/Screen distance in cm',
                                        1, -2147483647, 2147483647, 3)
        for j in DATA[k]:
            if bol is True:
                j['Screen'] = dict()
            if bswc is True:
                j['Screen']['screen_width_cm'] = swc[0]
            if bshc is True:
                j['Screen']['screen_height_cm'] = shc[0]
            if bvd is True:
                j['Screen']['viewing_Distance_cm'] = vd[0]

    def LoadMetadata(origin, data):
        def rec_remove_list(dic, datalen, idx):
            for key, item in dic.items():
                if type(item) is dict:
                    rec_remove_list(item, datalen, idx)
                elif type(item) is list:
                    lg = len(item)
                    if lg == datalen:
                        dic[key] = item[idx]
        datalen = len(data)
        for elem in METADATA:
            i = 0
            while i < datalen:
                tmp = copy.copy(METADATA[elem])
                rec_remove_list(tmp, datalen, i)
                data[i].update(tmp)
                i += 1

    # Check if there is any data loaded
    if not DATA:
        origin.log.insertPlainText('ERROR : NO DATA (You either have not loaded any data files, or data did not read correctly)\n')
        return
    # Read the selected settings in the variable trees, creating a list of adresses, used later or for calculations
    GatherSettings(origin)
    # Create or reset the CacheDATA
    origin.CacheDATA = []
    for k in DATA:
        # For every loaded data file: Add all the Metadata, ask what is the screen size in cm and user distance
        LoadMetadata(origin, DATA[k])
        CheckUserInput(k, origin)
        # Creates the data structure, and then check if there is no error returned, if not, adds it to CacheData
        tmp = CreateVariables(origin, DATA[k], origin.settings)
        if type(tmp) is str:
            origin.log.insertPlainText('ERROR : MISSING REQUIREMENT :' + tmp + '(Your loaded files do not have the required data needed for calculations)\n')
            return
        else:
            origin.CacheDATA += tmp
    # When all computation is done, creates copy of CacheData, and then call Cleaner on this copy, removing unwanted data
    origin.CleanDATA = copy.deepcopy(origin.CacheDATA)
    Cleaner(origin, origin.CleanDATA, origin.settings, '')
    # Create a "tag" data, allowing the user to comment every trial, tagging them to their liking
    for k in origin.CleanDATA:
        k['tag'] = ''
    # Check the amount of trials for trial selection in plotting later on
    origin.index.setMaximum(len(origin.CacheDATA))
    # Clear and then fill the data structure previsualisation tree
    origin.prevtree.clear()
    FillTree(origin.prevtree, origin.CleanDATA)
    origin.prevtree.collapseAll()
    # Sort wich data is plottable, and wich is not, and then creates the plot
    SortPlotVariables(origin, origin.settings)
    UpdatePlot(origin)


def PushReset(origin):
    # This function is called whenever the user clicks on the Reset button
    # It deletes and reset absolutely everything, be it loaded data, settings, metadata, or edf configuration
    DATA.clear()
    METADATA.clear()
    origin.savesettings = []
    origin.mdatafiles = ()
    origin.datafiles = ()
    origin.edfstart = None
    origin.edfevents = []
    origin.log.clear()
    LoadSettings(origin)
    ResetMetadata(origin)


def Export(origin):
    # This function is called and the user wants to export the CleanDATA structure
    # The jsonify class and the tsvify function are here to get rid of some python specifict data format
    # making the data code agnostic and not Python only
    class jsonify(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            else:
                return super(jsonify, self).default(obj)

    def tsvify(data):
        for k in data:
            if type(data) is dict:
                if type(data[k]) in [list, tuple, dict]:
                    tsvify(data[k])
                elif type(data[k]) is np.ndarray:
                    data[k] = data[k].tolist()
                elif type(data[k]) is np.floating:
                    data[k] = float(data[k])
                elif type(data[k]) is np.integer:
                    data[k] = int(data[k])
            elif type(k) in [list, tuple, dict]:
                tsvify(k)
            elif type(k) is np.floating:
                k = float(k)
            elif type(k) is np.integer:
                k = int(k)
            elif type(k) is np.ndarray:
                k = k.to_list()

    # Ask the user where and under what name and format the file will be save
    addr = QFileDialog.getSaveFileName(directory='finalstructures', filter='Pickle format(*.pkl);;JavaScript Object Notation(*.json);;Comma Separated Values(*.csv);;Tabulation Separated Values(*.tsv)')
    # Check what file format was selected and writes down the data structure accordingly
    i, j = os.path.splitext(addr[0])
    if j == '.pkl':
        with open(addr[0], 'wb') as file:
            f = pickle.Pickler(file)
            f.dump(origin.CleanDATA)
    elif j == '.json':
        with open(addr[0], 'w') as file:
            file.write(json.dumps(origin.CleanDATA, cls=jsonify, indent=1))
    elif j == '.tsv' or j == 'csv':
        with open(addr[0], 'w') as file:
            if j == '.tsv':
                w = csv.DictWriter(file, origin.CleanDATA[0].keys(), delimiter='\t')
            else:
                w = csv.DictWriter(file, origin.CleanDATA[0].keys())
            tmp = copy.deepcopy(origin.CleanDATA)
            tsvify(tmp)
            w.writeheader()
            w.writerows(tmp)


def OpenFile(origin, boot=False, clean=False):
    # This function is used when the user wants to load data into the programm
    # readdata is used and an EDF (asc format) is loaded in, reading the file and returning a python dict
    # updatevariables is a function that updates the selectable data list, adding anything that is new
    def readdata(path):
        while not origin.edfstart:
            ret = QInputDialog.getText(origin, 'EDF READER SETTINGS', 'Trial separator message')
            if ret[1] is True:
                origin.edfstart = ret[0]
        while not origin.edfevents:
            ret = QInputDialog.getText(origin, 'EDF READER SETTINGS', 'List of User-defined events in the edf file (format exemple= "event0,event1,event2,...")')
            if ret[1] is True:
                origin.edfevents = ret[0].split(',')
        return(read_edf(path, origin.edfstart, list_events=origin.edfevents))

    def updatevariables(origin):
        def recursivecheck(newvars):
            for k in newvars:
                bol = True
                if type(newvars[k]) is dict:
                    if list(newvars[k].keys()) == ['x', 'y']:
                        bol = True
                    else:
                        bol = False
                        recursivecheck(newvars[k])
                if bol is True:
                    newvars[k] = dict()
                    newvars[k]['desc'] = "DATA"
                    newvars[k]['func'] = "NONE"
                    newvars[k]['name'] = "DATA"
                    newvars[k]['reqs'] = []

        def recursiveupdate(old, new):
            for k in old:
                if list(old[k].keys()) != ['desc', 'func', 'name', 'reqs']:
                    if k in list(new.keys()):
                        recursiveupdate(old[k], new[k])
                        new[k].update(old[k])

        newvars = {}
        for k in DATA:
            newvars.update(DATA[k][0])
        tmp = copy.deepcopy(newvars)
        recursivecheck(tmp)
        recursiveupdate(origin.variables, tmp)
        origin.variables.update(tmp)
        SetTreeSettings(origin)

    # Check if the function was called at the start, wich loads in previously loaded data, when PRPG was closed
    if boot is True:
        if not origin.datafiles:
            return
    else:
        origin.datafiles = QFileDialog.getOpenFileNames(directory='data', filter='Data Format (*.asc *.pkl *.json)')
    # Check if the user is loading the Clear Data function, wich removes all loaded data before loading the new one
    if clean is True:
        DATA.clear()
    # Read the data with the appropriate function, returning a dictionnary
    # If the Data is an EDF (under asc format) file, it does have to call edfreader function
    for k in origin.datafiles[0]:
        with open(k, 'rb') as file:
            i, j = os.path.splitext(k)
            if j == '.json':
                DATA[k] = json.load(file, encoding='latin1')
            elif j == '.pkl':
                DATA[k] = pickle.load(file, encoding='latin1')
            else:
                DATA[k] = readdata(k)
    # Check if the Data exists and adds it in the program, otherwise don't add it, and put a message in the error log
        if DATA[k]:
            updatevariables(origin)
        else:
            del DATA[k]
            origin.log.insertPlainText('ERROR : COULD NOT FIND ANY TRIAL FOR FILE :' + i + '(The file may be wrong or the EDF Reader trial separator event is not set correctly)\n')
    # Update the lists in the Data Manager
    UpdateDataLists(origin.datamanager, origin)


def OpenMetadata(origin, boot=False):
    # Very similar to OpenFile, but for Metadata files
    # loadseparatedvalues is called when csv or tsv files are loaded in and need to be sorted in a dictionnary
    def loadseparatedvalues(name, origin, j):
        data = list()
        if j == '.csv':
            with open(name, 'r') as file:
                tmp = csv.reader(file, delimiter=',')
                for line in tmp:
                    data.append(line)
        elif j == '.tsv':
            with open(name, 'r') as file:
                tmp = csv.reader(file, delimiter='\t')
                for line in tmp:
                    data.append(line)
        names = copy.copy(data[0])
        del data[0]
        ret = dict()
        y = 0
        for k in names:
            ret[k] = []
            for i in data:
                ret[k].append(i[y])
            y += 1
        for k in ret:
            if len(ret[k]) == 1:
                ret[k] = ret[k][0]
        return ret

    def updatevariables(origin):
        def recursivecheck(newvars):
            for k in newvars:
                bol = True
                if type(newvars[k]) is dict:
                    if list(newvars[k].keys()) == ['x', 'y']:
                        bol = True
                    else:
                        bol = False
                        recursivecheck(newvars[k])
                if bol is True:
                    newvars[k] = dict()
                    newvars[k]['desc'] = "DATA"
                    newvars[k]['func'] = "NONE"
                    newvars[k]['name'] = "DATA"
                    newvars[k]['reqs'] = []

        def recursiveupdate(old, new):
            for k in old:
                if list(old[k].keys()) != ['desc', 'func', 'name', 'reqs']:
                    if k in list(new.keys()):
                        recursiveupdate(old[k], new[k])
                        new[k].update(old[k])

        newvars = {}
        for k in METADATA:
            newvars.update(METADATA[k])
        tmp = copy.deepcopy(newvars)
        recursivecheck(tmp)
        recursiveupdate(origin.variables, tmp)
        origin.variables.update(tmp)
        SetTreeSettings(origin)

    if boot is True:
        if not origin.mdatafiles:
            return
    else:
        origin.mdatafiles = QFileDialog.getOpenFileNames(directory='data', filter='Metadata Format (*.pkl *.json *.tsv *.csv)')
    for k in origin.mdatafiles[0]:
        with open(k, 'rb') as file:
            i, j = os.path.splitext(k)
            if j == '.tsv' or j == '.csv':
                METADATA[k] = loadseparatedvalues(k, origin, j)
            elif j == '.pkl':
                METADATA[k] = pickle.load(file, encoding='latin1')
            else:
                METADATA[k] = JsonLoadsCheck(file.read(), origin)
    updatevariables(origin)
    UpdateDataLists(origin.datamanager, origin)


def ResetMetadata(origin):
    # Called in PushReset or when the users clics on Reset Metadata, it simply removes all the Metadata
    origin.variables = copy.copy(origin.safevariables)
    METADATA = {}
    SetTreeSettings(origin)
    UpdateDataLists(origin.datamanager, origin)


def SaveSettings(origin):
    # Saves what are the selected settings in the variables tree widgets
    GatherSettings(origin)
    origin.savesettings = origin.settings


def LoadSettings(origin):
    # Loads the saved settings, and then automatically selects item in the variables trees
    def recurseclear(parent_item):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            grand_children = child.childCount()
            if grand_children > 0:
                recurseclear(child)
            child.setCheckState(0, Qt.Unchecked)

    def recurse(parent_item, setting, idx=0):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            grand_children = child.childCount()
            try:
                if grand_children > 0:
                    recurse(child, setting, idx + 1)
                elif child.text(0) == setting[idx]:
                    child.setCheckState(0, Qt.Checked)
            except IndexError:
                pass

    origin.settings = origin.savesettings
    recurseclear(origin.selecttree.invisibleRootItem())
    for setting in origin.settings:
        recurse(origin.selecttree.invisibleRootItem(), setting.split('.'))


def ChangeEDFReaderStart(origin):
    # Called when the user wants to change the trial separator event, or when it is needed
    val = QInputDialog.getText(origin, 'EDF READER SETTINGS : Trial Separator Event', 'Insert wich event is used to define the beginning of a single trial')
    if val[1] is True:
        origin.edfstart = val[0]


def ChangeEDFReaderEvents(origin):
    # Called when the user wants to change the events that need to be found in the edf file or when needed
    val = QInputDialog.getText(origin, 'EDF READER SETTINGS : Event list', 'List of User-defined events in the edf file (format exemple= "event0,event1,event2,...")')
    if val[1] is True:
        origin.edfevents = val[0].split(',')


def SavePreset(origin, close=False):
    # Save a preset of settings, containing the loaded data, metadata, edfreader settings, and the selected variables
    # The file is saved as a JSON, either a user made one, or an invisible one when the programm is closed
    SaveSettings(origin)
    preset = dict()
    preset['settings'] = origin.settings
    preset['mdatafiles'] = origin.mdatafiles
    preset['datafiles'] = origin.datafiles
    preset['edfstart'] = origin.edfstart
    preset['edfevents'] = origin.edfevents
    if close is True:
        file = open('presets/.lastpreset.json', 'w')
    else:
        file = open(QFileDialog.getSaveFileName(directory='presets', filter='JavaScript Object Notation(*.json)')[0], 'w')
    file.write(json.dumps(preset, sort_keys=True, indent=4))
    file.close()


def LoadPreset(origin, boot=False):
    # This reads a preset of settings, either user made, or the invisible one made when the programm exits
    if boot is True:
        try:
            file = open('presets/.lastpreset.json')
            preset = JsonLoadsCheck(file.read(), origin)
        except FileNotFoundError:
            preset = {}
    else:
        file = open(QFileDialog.getOpenFileName(directory='presets', filter='JavaScript Object Notation (*.json)')[0], 'r')
        preset = JsonLoadsCheck(file.read(), origin)

    try:
        origin.mdatafiles = preset['mdatafiles']
    except KeyError:
        origin.mdatafiles = ()
    try:
        origin.datafiles = preset['datafiles']
    except KeyError:
        origin.datafiles = ()
    try:
        origin.edfstart = preset['edfstart']
    except KeyError:
        origin.edfstart = ()
    try:
        origin.edfevents = preset['edfevents']
    except KeyError:
        origin.edfevents = ()
    OpenMetadata(origin, True)
    OpenFile(origin, True)
    try:
        origin.savesettings = preset['settings']
    except KeyError:
        origin.savesettings = []
    LoadSettings(origin)


def SetTreeSettings(origin):
    # This function clears and then fills the variable selection tree
    def SubTreeSettings(origin, lst, parent):
        child = QTreeWidgetItem(parent)
        child.setText(0, lst)
        child.setFlags(child.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
        child.setCheckState(0, Qt.Unchecked)

    SaveSettings(origin)
    origin.selecttree.clear()
    headerItem = QTreeWidgetItem()
    item = QTreeWidgetItem()
    for k in origin.variables:
        parent = QTreeWidgetItem(origin.selecttree)
        parent.setText(0, k)
        parent.setFlags(parent.flags() | Qt.ItemIsTristate | Qt.ItemIsUserCheckable)
        parent.setCheckState(0, Qt.Unchecked)
        for j in origin.variables[k]:
            if (list(origin.variables[k].keys()) != ['desc', 'func', 'name', 'reqs']):
                SubTreeSettings(origin, j, parent)
    LoadSettings(origin)


def OpenDataManager(origin):
    # This function is used when the user wants to access the data manager windows
    # It either creates it, or places it in front of the main window
    if origin.datamanageropen is False:
        origin.datamanageropen = True
        origin.datamanager = (DataManager(origin))
    else:
        origin.datamanager.hide()
        origin.datamanager.show()


def UpdateDataLists(manager, origin):
    # This functions updates the loaded data lists in the data manager, it uses the dict keys of DATA and METADATA
    if origin.datamanageropen is False:
        return()
    manager.datalist.clear()
    manager.metadatalist.clear()
    for k in DATA:
        manager.datalist.insertItem(0, k)
    for k in METADATA:
        manager.metadatalist.insertItem(0, k)


def DeleteData(manager, origin):
    # This function removes loaded data that is selected in the data manager tree
    elems = list()
    for k in manager.datalist.selectedItems():
        elems.append(k.text())
    for k in elems:
        del DATA[k]
    UpdateDataLists(manager, origin)


def DeleteMetadata(manager, origin):
    # This function removes loaded metadata that is selected in the data manager tree
    elems = list()
    for k in manager.metadatalist.selectedItems():
        elems.append(k.text())
    for k in elems:
        del METADATA[k]
    UpdateDataLists(manager, origin)


class DataManager(QMainWindow):
    # The Data manager windows is a small windows that is used to check what is the currently loaded data and metadata
    # It does contains a small amount of push buttons, useful for deletion and addition of datafiles
    def __init__(self, origin):
        QWidget.__init__(self)
        self.area = QWidget()
        self.setWindowTitle("PREPROGUI Data Manager")
        self.setCentralWidget(self.area)
        self.layt = QGridLayout()
        self.area.setLayout(self.layt)
        self.InitDataLists(origin)
        self.InitButtons(origin)
        self.show()

    def InitDataLists(self, origin):
        self.datalabel = QLabel('Loaded Data List')
        self.metadatalabel = QLabel('Loaded Metadata List')
        self.layt.addWidget(self.datalabel, 0, 0, 1, 2)
        self.layt.addWidget(self.metadatalabel, 0, 2, 1, 2)
        self.datalist = QListWidget()
        self.metadatalist = QListWidget()
        self.datalist.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.metadatalist.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.layt.addWidget(self.datalist, 1, 0, 1, 2)
        self.layt.addWidget(self.metadatalist, 1, 2, 1, 2)
        UpdateDataLists(self, origin)

    def InitButtons(self, origin):
        self.deldata = QPushButton('Delete Selected Data')
        self.adddata = QPushButton('Add Data')
        self.delmetadata = QPushButton('Delete Selected Metadata')
        self.addmetadata = QPushButton('Add Metadata')
        self.deldata.clicked.connect(lambda: DeleteData(self, origin))
        self.adddata.clicked.connect(lambda: OpenFile(origin))
        self.delmetadata.clicked.connect(lambda: DeleteMetadata(self, origin))
        self.addmetadata.clicked.connect(lambda: OpenMetadata(origin))
        self.layt.addWidget(self.deldata, 2, 0)
        self.layt.addWidget(self.adddata, 2, 1)
        self.layt.addWidget(self.delmetadata, 2, 2)
        self.layt.addWidget(self.addmetadata, 2, 3)


class MainWindow(QMainWindow):
    # Init a new window and all the PyQt5 widgets required to run the GUI
    def __init__(self):
        def Start(self):
            LoadPreset(self, True)
            self.show()

        QWidget.__init__(self)
        self.area = QWidget()
        self.resize(1280, 800)
        self.setWindowTitle("PREPROGUI")
        self.setCentralWidget(self.area)

        self.CacheDATA = []
        self.CleanDATA = []
        self.InitLayouts()
        self.InitSettings()
        self.InitPreview()
        self.InitPlot()
        self.InitMenu()

        Start(self)

    def closeEvent(self, event):
        SavePreset(self, close=True)
        # reply = QMessageBox.question(self, 'Window Close', 'Are you sure you want to close the window?',
        # 		QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        # if reply == QMessageBox.Yes:
        # 	event.accept()
        # pront('Window closed')
        # else:
        # 	event.ignore()

    def InitLayouts(self):
        self.layt = QGridLayout()
        self.area.setLayout(self.layt)
        self.settingslayt = QVBoxLayout()
        self.previewlayt = QGridLayout()
        self.plotlayt = QVBoxLayout()
        self.layt.addLayout(self.settingslayt, 0, 1)
        self.layt.addLayout(self.previewlayt, 0, 2)
        self.layt.addLayout(self.plotlayt, 0, 3, 1, 3)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)

    def InitSettings(self):

        # User selection Groupbox
            groupbox = QGroupBox()
            layt = QGridLayout()
            groupbox.setLayout(layt)
            layt.setSpacing(3)

        # Selection Tree Widget
            with open('variables.json', 'r') as file:
                self.safevariables = JsonLoadsCheck(file.read(), self)
            self.variables = copy.copy(self.safevariables)
            self.selecttree = QTreeWidget()
            SetTreeSettings(self)
            self.settingslayt.addWidget(self.selecttree)

        # Initializing some variables used later
            self.edfstart = ''
            self.edfevents = []
            self.settings = []
            self.savesettings = []
            self.mdatafiles = ()
            self.datafiles = ()

        # Apply & Reset Buttons
            pushreset = QPushButton('Clear Everything')
            pushapply = QPushButton('Apply')
            pushreset.clicked.connect(lambda: PushReset(self))
            pushapply.clicked.connect(lambda: PushApply(self))
            layt.addWidget(pushreset, 2, 0)
            layt.addWidget(pushapply, 2, 1)

            self.settingslayt.addWidget(groupbox)

    def InitPreview(self):
        self.prevtree = QTreeWidget()
        FillTree(self.prevtree, self.CleanDATA)
        self.prevtree.collapseAll()
        self.previewlayt.addWidget(self.prevtree, 0, 0, 1, 1)
        self.previewlayt.addWidget(self.log, 1, 0, 40, 1)

    def InitPlot(self):
        self.check = False
        self.htmlreader = QWebEngineView()
        self.htmlreader.setFixedSize(600, 600)
        self.plot_variables = list()

        groupbox = QGroupBox('Axis Selection')
        groupbox.setFixedSize(600, 50)
        self.index = QSpinBox()
        self.index.setMinimum(1)
        self.index.setMaximumWidth(60)
        self.index.setMaximum(2)
        self.index.setWrapping(True)
        self.index.valueChanged.connect(lambda checked: UpdatePlot(self))

        self.dpdw1 = QComboBox()
        self.dpdw2 = QComboBox()
        self.dpdw3 = QComboBox()
        self.flipy = QCheckBox('Flip Y')

        layt = QHBoxLayout()
        layt.setContentsMargins(3, 3, 3, 3)
        groupbox.setLayout(layt)
        layt.addWidget(QLabel('Trial Index'))
        layt.addWidget(self.index)
        layt.addWidget(QLabel('X-Axis'))
        layt.addWidget(self.dpdw1)
        layt.addWidget(QLabel('Y-Axis'))
        layt.addWidget(self.dpdw2)
        layt.addWidget(QLabel('Color'))
        layt.addWidget(self.dpdw3)
        layt.addWidget(self.flipy)
        self.lock = False
        self.dpdw1.currentTextChanged.connect(lambda checked: UpdatePlot(self))
        self.dpdw2.currentTextChanged.connect(lambda checked: UpdatePlot(self))
        self.dpdw3.currentTextChanged.connect(lambda checked: UpdatePlot(self))
        self.flipy.stateChanged.connect(lambda checked: UpdatePlot(self))

        self.plotlayt.addWidget(self.htmlreader)
        self.plotlayt.addWidget(groupbox)

    def InitMenu(self):
        self.datamanager = 0
        self.datamanageropen = False
        menubar = self.menuBar()

        filemenu = menubar.addMenu('File')
        placeholder = filemenu.addAction('Open Datafiles (Clear Data)')
        placeholder.triggered.connect(lambda: OpenFile(self, clean=True))
        placeholder = filemenu.addAction('Add Datafiles')
        placeholder.triggered.connect(lambda: OpenFile(self))
        filemenu.addSeparator()
        placeholder = filemenu.addAction('Add Metadata')
        placeholder.triggered.connect(lambda: OpenMetadata(self))
        placeholder = filemenu.addAction('Clear Metadata')
        placeholder.triggered.connect(lambda: ResetMetadata(self))
        filemenu.addSeparator()
        placeholder = filemenu.addAction('Data Manager')
        placeholder.triggered.connect(lambda: OpenDataManager(self))

        exportmenu = menubar.addMenu('Export')
        placeholder = exportmenu.addAction('Export Data Structure')
        placeholder.triggered.connect(lambda: Export(self))

        edfreadermenu = menubar.addMenu('EDF Reader')
        placeholder = edfreadermenu.addAction('Change EDF Reader trial separator')
        placeholder.triggered.connect(lambda: ChangeEDFReaderStart(self))
        placeholder = edfreadermenu.addAction('Change EDF Reader events')
        placeholder.triggered.connect(lambda: ChangeEDFReaderEvents(self))

        presetmenu = menubar.addMenu('Preset')
        placeholder = presetmenu.addAction('Save Preset')
        placeholder.triggered.connect(lambda: SavePreset(self))
        placeholder = presetmenu.addAction('Load Preset')
        placeholder.triggered.connect(lambda: LoadPreset(self))


app = QApplication(sys.argv)
ex = MainWindow()
ex.show()
sys.exit(app.exec_())
