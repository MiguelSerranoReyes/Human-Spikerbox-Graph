from scipy.signal import butter, sosfiltfilt, iirnotch, filtfilt
import numpy as np

def butter_bandpass_filter(data, fs, lowcut, highcut, order=4):
    if len(data) < 3 * order:
        return data
    sos = butter(order, [lowcut, highcut], btype='bandpass', fs=fs, output='sos')
    return sosfiltfilt(sos, data)

def notch_filter(data, fs, f0=60.0, Q=30.0, harmonics=3):
    for h in range(1, harmonics + 1):
        b, a = iirnotch(f0 * h, Q, fs)
        data = filtfilt(b, a, data)
    return data
