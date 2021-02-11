#!/usr/bin/env python
# -*- coding: utf-8 -*-

import numpy as np
from copy import copy
from scipy import signal


def DirTarget(msg):
    if int(msg[0][1][-1]) % 2:
        dir_target = 1
    else:
        dir_target = -1
        return dir_target


def Bias(msg):
    if msg[0][1][-3] == '0':
        bias = 0
    else:
        bias = 1
        return bias


def ScreenWidthPx(msg):
    for k in msg:
        if k[1].split(' ')[0] == 'GAZE_COORDS':
            return float(k[1].split(' ')[-2])


def ScreenHeightPx(msg):
    for k in msg:
        if k[1].split(' ')[0] == 'GAZE_COORDS':
            return float(k[1].split(' ')[-1])


def ScreenFramerate(msg):
    for k in msg:
        if k[1].split(' ')[0:2] == ['!MODE', 'RECORD']:
            return float(k[1].split(' ')[3])


def ScreenWidthDeg(screen_width_cm, viewing_Distance_cm):
    tan = np.arctan((screen_width_cm/2)/viewing_Distance_cm)
    return (2. * tan * 180/np.pi)


def ScreenHeightDeg(screen_height_cm, viewing_Distance_cm):
    tan = np.arctan((screen_height_cm/2)/viewing_Distance_cm)
    return (2. * tan * 180/np.pi)


def ScreenPixPerDeg(screen_width_px, screen_width_deg):
    return (screen_width_px / screen_width_deg)


def DetectMissac(V_deg, time):

    # Relative velocity threshold
    VFAC = 5
    # Minimal saccade duration (ms)
    mindur = 5
    # Maximal saccade duration (ms)
    maxdur = 100
    # Minimal time interval between two detected saccades (ms)
    minsep = 30

    t_0 = time[0]

    msdx = np.sqrt((np.nanmedian(V_deg['x']**2)) -
                   ((np.nanmedian(V_deg['x']))**2))
    msdy = np.sqrt((np.nanmedian(V_deg['y']**2)) -
                   ((np.nanmedian(V_deg['y']))**2))

    radiusx, radiusy = VFAC * msdx, VFAC * msdy

    test = (V_deg['x'] / radiusx) ** 2 + (V_deg['y'] / radiusy) ** 2
    index = [x for x in range(len(test)) if test[x] > 1]

    dur = 0
    start_misaccades = 0
    misaccades = []

    for i in range(len(index) - 1):
        if index[i + 1]-index[i] == 1:
            dur += 1
        else:
            if dur >= mindur and dur < maxdur:
                end_misaccades = i
                misaccades.append([index[start_misaccades] + t_0,
                                   index[end_misaccades] + t_0])
            start_misaccades = i + 1
            dur = 1
        i += 1

    if len(misaccades) > 1:
        s = 0
        while s < len(misaccades)-1:
            # Temporal separation between onset of
            # saccade s + 1 and offset of saccade s
            sep = misaccades[s + 1][0]-misaccades[s][1]
            if sep < minsep:
                # The two saccades are fused into one
                misaccades[s][1] = misaccades[s + 1][1]
                del(misaccades[s + 1])
                s -= 1
            s += 1

    s = 0
    while s < len(misaccades):
        # Duration of sth saccade
        dur = misaccades[s][1]-misaccades[s][0]
        if dur >= maxdur:
            del(misaccades[s])
            s = s-1
        s = s + 1

    return misaccades


def PositionDeg(P_px, px_per_deg):
    P_deg = copy(P_px)
    for k in P_deg:
        for j in P_deg[k]:
            j /= px_per_deg
    return P_deg


def Filtering(data, framerate):
    cutoff = 30
    ret = copy(data)

    # The Nyquist rate of the signal.
    nyq_rate = framerate/2
    Wn = cutoff/nyq_rate

    # The order of the filter.
    N = 2

    # Butterworth digital and analog filter design.
    b, a = signal.butter(N, Wn, 'lowpass')

    # Apply a digital filter forward and backward to a signal.

    for k in ret:
        s = np.ma.masked_array(ret[k], mask=np.isnan(ret[k])).compressed()
        s_f = signal.filtfilt(b, a, s)
        xf = 0
        for j in ret[k]:
            if np.isnan(j) is False:
                j = s_f[xf]
                xf += 1
            else:
                j = (np.nan)
    return ret


def Velocity(P_deg, framerate):
    ret = copy(P_deg)
    # Gradient in deg/sec or px/sec
    for k in ret:
        ret[k] = np.gradient(ret[k]) * framerate
    return ret


def SuppSaccades(V_deg, Saccades, microSaccades, time):
    # Time to delete before saccades
    before_sacc = 5
    # Time to delete after saccades
    after_sacc = 15
    # Optional, it removes also the detected micro saccades
    add_misacc = True

    saccades = copy(Saccades)
    t_0 = time[0]

    if add_misacc is True:
        saccades.extend(microSaccades)

    ret = copy(V_deg)
    for k in ret:
        for s in range(len(saccades)):
            if saccades[s][1]-t_0 + after_sacc <= (len(time)):
                for x_data in np.arange((saccades[s][0]-t_0 - before_sacc),
                                        (saccades[s][1]-t_0 + after_sacc)):
                    ret[k][x_data] = np.nan
            else:
                for x_data in np.arange((saccades[s][0]-t_0 - before_sacc),
                                        (len(time))):
                    ret[k][x_data] = np.nan
    return ret
