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
with open('variables2.json', 'r') as file:
    variables = json.loads(file.read())


def GetNestedDic(dic, keys):
    for key in keys:
        try:
            dic = dic[key]
        except KeyError:
            dic[key] = dict()
            dic = dic[key]
    return dic


def SortPlotVariables(origin, settings):

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


def AssignCdsValues(origin, idx):
    cdsvalues = {}
    texts = [origin.dpdw1.currentText(),
             origin.dpdw2.currentText(), origin.dpdw3.currentText()]
    for k in texts:
            cdsvalues[k] = GetNestedDic(origin.CacheDATA[idx], k.split('.'))
    return cdsvalues


def UpdatePlot(origin):
    w = 500
    h = 500
    # First creates a new filtered ColumnDataSource with a copy of the values
    if origin.lock is True:
        return
    elif origin.check is False:
        origin.htmlreader.setHtml('The time must be selected in order to generate the plot!')
        return
    elif len(origin.plot_variables) == 0:
        origin.htmlreader.setHtml('No readable value selected!')
        return
    # Event if the selection is changed
    # in the bokeh plot using some JS dark magic
    # origin.filtered.selected.js_on_change('indices', CustomJS(code="""
    #    var inds = cb_obj.indices;
    #    console.log(inds)
    # """)
    # )
    idx = origin.index.value() - 1
    cdsvalues = AssignCdsValues(origin, idx)

    # Select the color range according to the selected value in "Color"
    color = linear_cmap(origin.dpdw3.currentText(), 'Plasma256',
                        np.nanmin(cdsvalues[origin.dpdw3.currentText()]),
                        np.nanmax(cdsvalues[origin.dpdw3.currentText()]))
    # Set the name of the axis according to
    # the selected values in x and y axis
    xaxis = origin.dpdw1.currentText()
    yaxis = origin.dpdw2.currentText()
    # Create the Bokeh plot, and adds the scattered filtered values as circles.
    p = figure(plot_width=w, plot_height=h, toolbar_location="above",
               tools='pan,wheel_zoom,box_zoom,reset,box_select,lasso_select,tap,hover,crosshair')
    plot = column(p, width=w, height=h)
    p.circle(x=xaxis, y=yaxis, source=cdsvalues, line_color=color, fill_color=color)
    # Put label with the name of selected axis on the plot
    p.xaxis.axis_label = xaxis.upper()
    p.yaxis.axis_label = yaxis.upper()
    # Transforms the bokeh plot into an HTML file,
    # and assign this file to the PyQt HTML reader
    html = file_html(plot, CDN)
    origin.htmlreader.setHtml(html)


def Cleaner(origin, data, settings, addr):
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


def UpdateTreeAndPlot(origin, settings):
    origin.index.setMaximum(len(origin.CacheDATA))
    origin.prevtree.clear()
    FillTree(origin.prevtree, origin.CleanDATA)
    origin.prevtree.collapseAll()
    SortPlotVariables(origin, settings)
    UpdatePlot(origin)


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
                if tmp: return (tmp + ' for ' + setting)
        elif not reqval:
            tmp = ComputeVariable(origin, req, dic)
            if tmp: return (tmp + ' for ' + setting)

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
        ChangeValue(k, function(*args), setting.split('.'))


def CreateVariables(origin, data, settingslist):
    ret = copy.deepcopy(data)
    for setting in settingslist:
        check = GetNestedDic(origin.variables, setting.split('.'))
        if type(check) is dict:
            if (list(check.keys()) != ['desc', 'func', 'name', 'reqs']):
                continue
        tmp = ComputeVariable(origin, setting, ret)
        if tmp : return tmp
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
    def CheckUserInput(k, origin):
        if 'Screen' in DATA[k][0]:
            bol = False
            bswc, bshc, bvd = False, False, False
            if 'screen_width_cm' not in DATA[k][0]['Screen']:
                bswc = True
                swc = QInputDialog.getDouble(origin, 'INPUT REQUIRED', 'Screen Width in cm',
                                             1, -2147483647, 2147483647, 3)
            if 'screen_height_cm' not in DATA[k][0]['Screen']:
                bshc = True
                shc = QInputDialog.getDouble(origin, 'INPUT REQUIRED', 'Screen Height in cm',
                                             1, -2147483647, 2147483647, 3)
            if 'viewing_Distance_cm' not in DATA[k][0]['Screen']:
                bvd = True
                vd = QInputDialog.getDouble(origin, 'INPUT REQUIRED', 'User/Screen distance in cm',
                                            1, -2147483647, 2147483647, 3)
        else:
            bol = True
            bswc, bshc, bvd = True, True, True
            swc = QInputDialog.getDouble(origin, 'INPUT REQUIRED', 'Screen Width in cm',
                                         1, -2147483647, 2147483647, 3)
            shc = QInputDialog.getDouble(origin, 'INPUT REQUIRED', 'Screen Height in cm',
                                         1, -2147483647, 2147483647, 3)
            vd = QInputDialog.getDouble(origin, 'INPUT REQUIRED', 'User/Screen distance in cm',
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

    if DATA == {}:
        return
    GatherSettings(origin)
    origin.CacheDATA = []
    for k in DATA:
        LoadMetadata(origin, DATA[k])
        CheckUserInput(k, origin)
        tmp = CreateVariables(origin, DATA[k], origin.settings)
        if type(tmp) is str:
            print('MISSING REQUIREMENT :', tmp)
            return
        else:
            origin.CacheDATA += tmp
    origin.CleanDATA = copy.deepcopy(origin.CacheDATA)
    Cleaner(origin, origin.CleanDATA, origin.settings, '')
    for k in origin.CleanDATA:
        k['tag'] = ''
    UpdateTreeAndPlot(origin, origin.settings)


def PushReset(origin):
    DATA.clear()
    METADATA.clear()
    origin.savesettings = []
    origin.mdatafiles = ()
    origin.datafiles = ()
    origin.edfstart = None
    origin.edfevents = []
    LoadSettings(origin)
    ResetMetadata(origin)


def Export(origin):
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

    addr = QFileDialog.getSaveFileName(directory='finalstructures', filter='Pickle format(*.pkl);;JavaScript Object Notation(*.json);;Comma Separated Values(*.csv);;Tabulation Separated Values(*.tsv)')
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


def OpenFile(origin, boot=False):
    def readdata(path):
        while not origin.edfstart:
            ret = QInputDialog.getText(origin, 'EDF READER SETTINGS', 'Trial start message')
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

    if boot is True:
        if not origin.datafiles:
            return
    else:
        origin.datafiles = QFileDialog.getOpenFileNames(directory='data', filter='Data (*.asc *.pkl *.json)')
    for k in origin.datafiles[0]:
        with open(k, 'rb') as file:
            print(k)
            i, j = os.path.splitext(k)
            print(i, j)
            if j == '.json':
                DATA[k] = json.load(file, encoding='latin1')
            elif j == '.pkl':
                DATA[k] = pickle.load(file, encoding='latin1')
            else:
                DATA[k] = readdata(k)
        updatevariables(origin)


def OpenMetadata(origin, boot=False):
    def recursivecheck(newvars):
        for k in newvars:
            if type(newvars[k]) is dict:
                recursivecheck(newvars[k])
            else:
                newvars[k] = dict()
                newvars[k]['desc'] = "METADATA"
                newvars[k]['func'] = "NONE"
                newvars[k]['name'] = "METADATA"
                newvars[k]['reqs'] = []

    if boot is True:
        if not origin.mdatafiles:
            return
    else:
        origin.mdatafiles = QFileDialog.getOpenFileNames(directory='data', filter='JavaScript Object Notation (*.json);;Pickle Data Structure = (*.pkl)')
    for k in origin.mdatafiles[0]:
        with open(k, 'rb') as file:
            i, j = os.path.splitext(k)
            if j == '.pkl':
                METADATA[k] = pickle.load(file, encoding='latin1')
            else:
                METADATA[k] = json.loads(file.read())
    newvars = {}
    for k in METADATA:
        newvars.update(METADATA[k])
    tmp = copy.deepcopy(METADATA)
    recursivecheck(newvars)
    METADATA.update(tmp)
    origin.variables.update(newvars)
    SetTreeSettings(origin)


def ResetMetadata(origin):
    origin.variables = copy.copy(variables)
    METADATA = {}
    SetTreeSettings(origin)


def SaveSettings(origin):
    GatherSettings(origin)
    origin.savesettings = origin.settings


def LoadSettings(origin):
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
            except:
                pass

    origin.settings = origin.savesettings
    recurseclear(origin.selecttree.invisibleRootItem())
    for setting in origin.settings:
        recurse(origin.selecttree.invisibleRootItem(), setting.split('.'))


def ChangeEDFReaderStart(origin):
    val = QInputDialog.getText(origin, 'EDF READER SETTINGS', 'Insert wich event is used to define the beginning of a trial')
    if val[1] is True:
        origin.edfstart = val[0]


def ChangeEDFReaderEvents(origin):
    val = QInputDialog.getText(origin, 'EDF READER SETTINGS', 'List of User-defined events in the edf file (format exemple= "event0,event1,event2,...")')
    if val[1] is True:
        origin.edfevents = val[0].split(',')


def SavePreset(origin, close=False):
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
    if boot is True:
        try:
            file = open('presets/.lastpreset.json')
            preset = json.loads(file.read())
        except FileNotFoundError:
            preset = {}
    else:
        file = open(QFileDialog.getOpenFileName(directory='presets', filter='JavaScript Object Notation (*.json)')[0], 'r')
        preset = json.loads(file.read())

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


class MainWindow(QMainWindow):
    # Init a new window and all the PyQt5 widgets required to run the GUI
    def __init__(self):
        def Start(self):
            LoadPreset(self, True)
            self.show()

        QWidget.__init__(self)
        self.area = QWidget()
        self.resize(1100, 620)
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
        # 	print('Window closed')
        # else:
        # 	event.ignore()

    def InitLayouts(self):
        self.layt = QHBoxLayout()
        self.area.setLayout(self.layt)
        self.settingslayt = QVBoxLayout()
        self.previewlayt = QVBoxLayout()
        self.plotlayt = QVBoxLayout()
        self.layt.addLayout(self.settingslayt)
        self.layt.addLayout(self.previewlayt)
        self.layt.addLayout(self.plotlayt)

    def InitSettings(self):

        # User selection Groupbox, these checkboxes will define the structure later
            groupbox = QGroupBox()
            layt = QGridLayout()
            groupbox.setLayout(layt)
            layt.setSpacing(3)

        # Selection Tree Widget
            self.variables = copy.copy(variables)
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
            pushreset = QPushButton('Reset')
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
        self.previewlayt.addWidget(self.prevtree)

    def InitPlot(self):
        self.check = False
        self.htmlreader = QWebEngineView()
        self.htmlreader.setFixedSize(500, 500)
        self.plot_variables = list()

        groupbox = QGroupBox('Axis Selection')
        groupbox.setFixedSize(500, 50)
        self.index = QSpinBox()
        self.index.setMinimum(1)
        self.index.setMaximumWidth(60)
        self.index.setMaximum(2)
        self.index.setWrapping(True)
        self.index.valueChanged.connect(lambda checked: UpdatePlot(self))

        self.dpdw1 = QComboBox()
        self.dpdw2 = QComboBox()
        self.dpdw3 = QComboBox()

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
        self.lock = False
        self.dpdw1.currentTextChanged.connect(lambda checked: UpdatePlot(self))
        self.dpdw2.currentTextChanged.connect(lambda checked: UpdatePlot(self))
        self.dpdw3.currentTextChanged.connect(lambda checked: UpdatePlot(self))

        self.plotlayt.addWidget(self.htmlreader)
        self.plotlayt.addWidget(groupbox)

    def InitMenu(self):
        menubar = self.menuBar()

        filemenu = menubar.addMenu('File')
        placeholder = filemenu.addAction('Open...')
        placeholder.triggered.connect(lambda: OpenFile(self))

        exportmenu = menubar.addMenu('Export')
        placeholder = exportmenu.addAction('Export Data Structure')
        placeholder.triggered.connect(lambda: Export(self))

        edfreadermenu = menubar.addMenu('EDF Reader')
        placeholder = edfreadermenu.addAction('Change EDF Reader start')
        placeholder.triggered.connect(lambda: ChangeEDFReaderStart(self))
        placeholder = edfreadermenu.addAction('Change EDF Reader events')
        placeholder.triggered.connect(lambda: ChangeEDFReaderEvents(self))

        presetmenu = menubar.addMenu('Preset')
        placeholder = presetmenu.addAction('Save Preset')
        placeholder.triggered.connect(lambda: SavePreset(self))
        placeholder = presetmenu.addAction('Load Preset')
        placeholder.triggered.connect(lambda: LoadPreset(self))

        importmenu = menubar.addMenu('Metadata')
        placeholder = importmenu.addAction('Import Metadata')
        placeholder.triggered.connect(lambda: OpenMetadata(self))
        placeholder = importmenu.addAction('Reset Metadata')
        placeholder.triggered.connect(lambda: ResetMetadata(self))


app = QApplication(sys.argv)
ex = MainWindow()
ex.show()
sys.exit(app.exec_())
