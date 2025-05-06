# data_provider.py
from PyQt5.QtCore import QObject, pyqtSignal

class DataProvider(QObject):
    new_data = pyqtSignal(object, object)  # ch1, ch2

    def __init__(self):
        super().__init__()

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError
