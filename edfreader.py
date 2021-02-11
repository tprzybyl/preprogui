# EDF Reader
#
# Does not actually read EDFs directly, but the ASC files that are produced
# by edf2asc (SR Research). Information on saccades, fixations and blinks is
# read from the EDF, therefore based on SR Research algorithms. For optimal
# event detection, it might be better to use a different algorithm, e.g.



import copy
import os.path

import numpy as np


def replace_missing(value, missing=np.nan):

    """Returns missing code if passed value is missing, or the passed value
    if it is not missing; a missing value in the EDF contains only a
    period, no numbers; NOTE: this function is for gaze position values
    only, NOT for pupil size, as missing pupil size data is coded '0.0'

    arguments
    value       -   either an X or a Y gaze position value (NOT pupil
                    size! This is coded '0.0')

    keyword arguments
    missing     -   the missing code to replace missing data with
                    (default = 0.0)

    returns
    value       -   either a missing code, or a float value of the
                    gaze position
    """

    if value.replace(' ','') == '.':
        return missing
    else:
        return float(value)

def read_edf(filename, start, stop=None, list_events=None, event_start=None, missing=np.nan, debug=False):

    """
    This code comes from PyGazeAnalyser available `here <https://github.com/esdalmaijer/PyGazeAnalyser>`_.

    ©Edwin Dalmaijer, 2013-2014
    edwin.dalmaijer@gmail.com

    Does not actually read EDFs directly, but ASC files that are produced  by edf2asc (SR Research).
    Information on saccades, fixations and blinks is read from the EDF, hence based on SR Research algorithms.

    Returns a list with dicts for every trial. A trial dict contains the following keys:

        - ``x``           -  numpy array of x positions
        - ``y``           -  numpy array of y positions
        - ``size``        -  numpy array of pupil size
        - ``time``        -   numpy array of timestamps, t=0 at trialstart
        - ``trackertime`` -  numpy array of timestamps, according to EDF
        - ``events``      -  dict with the following keys:
            - ``Sfix`` -  list of lists, each containing ``[start_fixation]``
            - ``Ssac`` -  list of lists, each containing ``[start_saccade]``
            - ``Sblk`` -  list of lists, each containing ``[start_blink]``
            - ``Efix`` -  list of lists, each containing ``[start_fixation, end_fixation, duration_fixation, endx_fixation, endy_fixation]``
            - ``Esac`` -  list of lists, each containing ``[start_saccade, end_saccade, duration_saccade, startx_saccade, starty_saccade, endx_saccade, endy_saccade]``
            - ``Eblk`` -  list of lists, each containing ``[start_blink, end_blink, duration_blink]``
            - ``msg``  -  list of lists, each containing ``[time, message]``

    Note
    ----
    timing is in EDF time!

    Parameters
    ----------
    filename :
        path to the file that has to be read
    start : str
        trial start string

    keyword arguments
    ----------
    stop : str (default None)
        trial ending string
    missing : float (default 0.0)
        value to be used for missing data
    debug : bool (default False)
        Boolean indicating if DEBUG mode should be on or off;
        if DEBUG mode is on, information on what the script
        currently is doing will be printed to the console


    Returns
    -------
    data : list
        a list with a dict for every trial (see above)
    """

    # # # # #
    # debug mode

    if debug:
        def message(msg): print(msg)
    else:
        def message(msg): pass


    # # # # #
    # file handling

    # check if the file exists
    if os.path.isfile(filename):
        # open file
        message("opening file '%s'" % filename)
        f = open(filename, 'r')
    # raise exception if the file does not exist
    else:
        raise Exception("Error in read_edf: file '%s' does not exist" % filename)

    # read file contents
    message("reading file '%s'" % filename)
    raw = f.readlines()

    # close file
    message("closing file '%s'" % filename)
    f.close()


    # # # # #
    # parse lines

    # variables
    data = []

    x, y, size = [], [], []
    time, trackertime = [], []
    events = {'Fixations':[],'Saccades':[],'Blinks':[],'msg':[]}

    if list_events is not None :
        for evt in list_events :
            events[evt] = []

    starttime = None
    started, trialend = False, False
    finalline = raw[-1]

    # loop through all lines
    for line in raw:

        # check if trial has already started
        if started:
            # only check for stop if there is one
            if stop != None:
                if stop in line:
                    started, trialend = False, True
            # check for new start otherwise
            else:
                if (start in line) or (line == finalline):
                    started, trialend = True, True

            # # # # #
            # trial ending

            if trialend:
                message("trialend %d; %d samples found" % (len(data),len(x)))
                # trial dict
                trial = {}
                trial['P_px'] = {'x' : np.array(x),
                                   'y' : np.array(y)}

                #trial['x_pix'] = np.array(x)
                #trial['y_pix'] = np.array(y)
                trial['pupil_size'] = np.array(size)

                if starttime is None :
                    starttime = np.array(trackertime)[0]


                trial['time'] = np.array(trackertime) - starttime
                trial['events'] = copy.deepcopy(events)

                for evt in trial['events'].keys() :
                    if evt in ['Fixations','Saccades','Blinks', 'msg']:
                        for e in trial['events'][evt] :
                            e[0] = e[0]-starttime
                            if evt!='msg':
                                e[1] = e[1]-starttime
                    elif len(trial['events'][evt])==1:
                        trial['events'][evt] = trial['events'][evt][0]-starttime
                    else :
                        for m in range(len(trial['events'][evt])) :
                            trial['events'][evt][m] = trial['events'][evt][m]-starttime


                # add trial to data
                data.append(trial)
                # reset stuff
                x, y, size = [], [], []
                time, trackertime = [], []
                events = {'Fixations':[],'Saccades':[],'Blinks':[],'msg':[]}
                if list_events is not None :
                    for evt in list_events :
                        events[evt] = []

                starttime = None
                trialend = False

        # check if the current line contains start message
        else:
            if start in line:
                message("trialstart %d" % len(data))
                # set started to True
                started = True

        # # # # #
        # parse line

        if started:

            # find starting time
            if event_start :
                if event_start in line:
                    starttime = int(line[line.find('\t')+1:line.find(' ')])

            # message lines will start with MSG, followed by a tab, then a
            # timestamp, a space, and finally the message, e.g.:
            #   "MSG\t12345 something of importance here"
            if line[0:3] == "MSG":
                ms = line.find(" ") # message start
                t = int(line[4:ms]) # time
                m = line[ms+1:] # message
                if m[-1:]=='\n' : m = m[:-1]

                try :
                    if m in list_events : events[m].append(t)
                    else :                events['msg'].append([t,m])
                except :
                    events['msg'].append([t,m])

            # EDF event lines are constructed of 9 characters, followed by
            # tab separated values; these values MAY CONTAIN SPACES, but
            # these spaces are ignored by float() (thank you Python!)

            # fixation start
            elif line[0:4] == "SFIX":
                message("fixation start")
            # fixation end
            elif line[0:4] == "EFIX":
                message("fixation end")
                l = line[9:]
                l = l.split('\t')
                st = int(l[0]) # starting time
                et = int(l[1]) # ending time
                #dur = int(l[2]) # duration
                #sx = replace_missing(l[3], missing=missing) # x position
                #sy = replace_missing(l[4], missing=missing) # y position
                events['Fixations'].append([st, et])#, dur, sx, sy])

            # saccade start
            elif line[0:5] == 'SSACC':
                message("saccade start")
            # saccade end
            elif line[0:5] == "ESACC":
                message("saccade end")
                l = line[9:]
                l = l.split('\t')
                st = int(l[0]) # starting time
                et = int(l[1]) # endint time
                #dur = int(l[2]) # duration
                #sx = replace_missing(l[3], missing=missing) # start x position
                #sy = replace_missing(l[4], missing=missing) # start y position
                #ex = replace_missing(l[5], missing=missing) # end x position
                #ey = replace_missing(l[6], missing=missing) # end y position
                events['Saccades'].append([st, et])#, dur, sx, sy, ex, ey])

            # blink start
            elif line[0:6] == "SBLINK":
                message("blink start")
            # blink end
            elif line[0:6] == "EBLINK":
                message("blink end")
                l = line[9:]
                l = l.split('\t')
                st = int(l[0])
                et = int(l[1])
                #dur = int(l[2])
                events['Blinks'].append([st,et])#,dur])

            # regular lines will contain tab separated values, beginning with
            # a timestamp, follwed by the values that were asked to be stored
            # in the EDF and a mysterious '...'. Usually, this comes down to
            # timestamp, x, y, pupilsize, ...
            # e.g.: "985288\t  504.6\t  368.2\t 4933.0\t..."
            # NOTE: these values MAY CONTAIN SPACES, but these spaces are
            # ignored by float() (thank you Python!)
            else:
                # see if current line contains relevant data
                try:
                    # split by tab
                    l = line.split('\t')
                    # if first entry is a timestamp, this should work
                    int(l[0])
                except:
                    message("line '%s' could not be parsed" % line)
                    continue # skip this line

                # check missing
                if float(l[3]) == 0.0:
                    l[1] = np.nan
                    l[2] = np.nan

                # extract data
                x.append(float(l[1]))
                y.append(float(l[2]))
                size.append(float(l[3]))
                trackertime.append(int(l[0]))


    # # # # #
    # return

    return data
