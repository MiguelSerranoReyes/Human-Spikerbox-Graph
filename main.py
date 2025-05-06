import sys
from PyQt5.QtWidgets import QApplication
from ui import SignalViewer
from serial_reader import SerialReader
from PyQt5.QtGui import QIcon
import ctypes

ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(u"human.spikerbox.app")

def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("human_spikerbox_icon.ico"))
    viewer = SignalViewer()
    viewer.show()

    def start_acquisition():
        port = viewer.port_combo.currentText()
        print(f"[MAIN] Conectando a {port}...")
        try:
            viewer.reader = SerialReader(port=port, viewer=viewer)
            viewer.reader.new_data.connect(viewer.update_signals)
            viewer.reader.start()
            viewer.status_label.setText(f"Estado: Conectado a {port}")
        except Exception as e:
            viewer.status_label.setText(f"Error al conectar: {e}")

    viewer.start_requested.connect(start_acquisition)

    exit_code = app.exec_()
    if viewer.reader:
        viewer.reader.stop()
    print("Saliendo correctamente...")
    sys.exit(exit_code)

if __name__ == "__main__":
    main()