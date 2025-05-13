from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QDoubleSpinBox, QSpinBox,
    QLabel, QGroupBox, QFormLayout, QComboBox, QCheckBox, QFileDialog, QLineEdit, QMessageBox
)
from PyQt5.QtCore import QTimer, pyqtSignal
import pyqtgraph as pg
import numpy as np
import serial.tools.list_ports
from PyQt5.QtGui import QIcon
import os

class SignalViewer(QWidget):
    start_requested = pyqtSignal()

    def __init__(self, n_samples=30000, sample_rate=10000, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Human SpikerBox")
        self.setWindowIcon(QIcon("human_spikerbox_icon.ico"))
        self.sample_rate = sample_rate
        self.n_samples = n_samples
        self.running = False
        self.reader = None

        self.data_ch1 = np.zeros(self.n_samples)
        self.time_axis = np.linspace(-self.n_samples / self.sample_rate * 1000, 0, self.n_samples)

        self.active_filter = 'custom'
        self.last_selected_port = None

        self.output_folder = ""
        self.recording_enabled = False

        self.init_ui()
        self.update_ports()

        self.port_timer = QTimer()
        self.port_timer.timeout.connect(self.check_ports_update)
        self.port_timer.start(3000)
        self._last_ports = []

    def init_ui(self):
        # === PLOT ===
        self.plot_widget = pg.GraphicsLayoutWidget()
        self.plot1 = self.plot_widget.addPlot(title="Señal (Canal Único)")
        self.plot1.setLabel('bottom', 'Tiempo', units='ms')
        self.curve1 = self.plot1.plot(self.time_axis, self.data_ch1, pen='c')
        self.plot1.setMouseEnabled(x=True, y=True)

        # === BOTONES DE CONTROL PRINCIPAL ===
        self.port_combo = QComboBox()
        self.port_combo.currentIndexChanged.connect(self.save_selected_port)
        self.refresh_button = QPushButton("Actualizar Puertos")
        self.start_button = QPushButton("Iniciar")
        self.auto_button = QPushButton("Autocalibrar eje Y")
        self.exit_button = QPushButton("Salir")
        self.status_label = QLabel("Estado: Desconectado")

        self.refresh_button.clicked.connect(self.update_ports)
        self.start_button.clicked.connect(self.toggle_running)
        self.auto_button.clicked.connect(self.autoscale_y)
        self.exit_button.clicked.connect(self.close)

        # === CONTROLES DE SEÑAL ===
        self.y_min = QDoubleSpinBox(); self.y_min.setRange(-10000, 0); self.y_min.setValue(-3000)
        self.y_max = QDoubleSpinBox(); self.y_max.setRange(0, 10000); self.y_max.setValue(7000)
        self.x_ms = QDoubleSpinBox(); self.x_ms.setRange(50, 10000); self.x_ms.setValue(1000)
        self.gain = QDoubleSpinBox(); self.gain.setRange(0.1, 10.0); self.gain.setValue(1.0)
        self.center_signal = QCheckBox("Restar media (centrar señal)")
        self.center_signal.setChecked(False)
        self.y_min.valueChanged.connect(self.update_y_range)
        self.y_max.valueChanged.connect(self.update_y_range)
        self.x_ms.valueChanged.connect(self.update_x_range)

        # === FILTROS ===
        self.enable_butter = QCheckBox("Activar Bandpass Butter")
        self.butter_lowcut = QDoubleSpinBox(); self.butter_lowcut.setRange(0.1, 5000); self.butter_lowcut.setValue(20)
        self.butter_highcut = QDoubleSpinBox(); self.butter_highcut.setRange(1, 5000); self.butter_highcut.setValue(450)
        self.butter_order = QSpinBox(); self.butter_order.setRange(1, 10); self.butter_order.setValue(2)

        self.enable_notch = QCheckBox("Activar Notch")
        self.notch_freq = QDoubleSpinBox(); self.notch_freq.setRange(10, 100); self.notch_freq.setValue(60)
        self.notch_q = QDoubleSpinBox(); self.notch_q.setRange(1, 100); self.notch_q.setValue(30)
        self.notch_harmonics = QSpinBox(); self.notch_harmonics.setRange(1, 5); self.notch_harmonics.setValue(3)

        self.chunk_size = QSpinBox(); self.chunk_size.setRange(100, 100000); self.chunk_size.setValue(10000)

        # === CONTROLES DE GRABACIÓN ===
        self.filename_input = QLineEdit()
        self.folder_display = QLineEdit(); self.folder_display.setReadOnly(True); self.folder_display.setMaximumWidth(300)
        self.folder_button = QPushButton("Examinar...")
        self.record_button = QPushButton("Iniciar grabación")

        self.folder_button.clicked.connect(self.select_output_folder)
        self.record_button.clicked.connect(self.toggle_recording)

        # === LAYOUTS ===
        top_controls = QHBoxLayout()
        top_controls.addWidget(QLabel("Puerto:"))
        top_controls.addWidget(self.port_combo)
        top_controls.addWidget(self.refresh_button)
        top_controls.addWidget(self.status_label)
        top_controls.addStretch()
        top_controls.addWidget(self.start_button)
        top_controls.addWidget(self.auto_button)
        top_controls.addWidget(self.exit_button)

        signal_controls = QFormLayout()
        signal_controls.addRow(QLabel("<b>Controles de Señal:</b>"))
        signal_controls.addRow("Y Mín", self.y_min)
        signal_controls.addRow("Y Máx", self.y_max)
        signal_controls.addRow("Ventana (ms)", self.x_ms)
        signal_controls.addRow("Ganancia", self.gain)
        signal_controls.addRow(self.center_signal)

        butter_controls = QFormLayout()
        butter_controls.addRow(self.enable_butter)
        butter_controls.addRow("Lowcut (Hz)", self.butter_lowcut)
        butter_controls.addRow("Highcut (Hz)", self.butter_highcut)
        butter_controls.addRow("Orden", self.butter_order)

        notch_controls = QFormLayout()
        notch_controls.addRow(self.enable_notch)
        notch_controls.addRow("f0 (Hz)", self.notch_freq)
        notch_controls.addRow("Q", self.notch_q)
        notch_controls.addRow("Armónicos", self.notch_harmonics)

        general_controls = QFormLayout()
        general_controls.addRow(QLabel("<b>Parámetros Generales:</b>"))
        general_controls.addRow("Archivo", self.filename_input)
        general_controls.addRow("Carpeta", self.folder_display)
        general_controls.addRow(" ", self.folder_button)
        general_controls.addRow(" ", self.record_button)
        general_controls.addRow("Chunk Size", self.chunk_size)

        group1 = QGroupBox("Visualización")
        group1.setLayout(signal_controls)
        group2 = QGroupBox("Filtro Bandpass")
        group2.setLayout(butter_controls)
        group3 = QGroupBox("Filtro Notch")
        group3.setLayout(notch_controls)
        group4 = QGroupBox("Configuración")
        group4.setLayout(general_controls)

        bottom_controls = QHBoxLayout()
        bottom_controls.addWidget(group1)
        bottom_controls.addWidget(group2)
        bottom_controls.addWidget(group3)
        bottom_controls.addWidget(group4)

        layout = QVBoxLayout()
        layout.addWidget(self.plot_widget)
        layout.addLayout(top_controls)
        layout.addLayout(bottom_controls)
        self.setLayout(layout)

        self.update_y_range()

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta para guardar")
        if folder:
            self.output_folder = folder
            self.folder_display.setText(folder)

    def toggle_recording(self):
        if not self.recording_enabled:
            if not self.output_folder or not self.filename_input.text():
                self.status_label.setText("Falta carpeta o nombre de archivo")
                return
            full_path = os.path.join(self.output_folder, self.filename_input.text() + ".csv")
            if os.path.exists(full_path):
                reply = QMessageBox.question(self, 'Archivo existente',
                    f"El archivo {full_path} ya existe. ¿Deseas sobrescribirlo?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply == QMessageBox.No:
                    return
            self.recording_enabled = True
            self.record_button.setText("Detener grabación")
            self.status_label.setText("Grabando...")
            if self.reader and self.reader.running:
                self.reader.start_recording()
        else:
            self.recording_enabled = False
            self.record_button.setText("Iniciar grabación")
            self.status_label.setText("Grabación detenida")
            if self.reader:
                self.reader.stop_recording()

    def save_selected_port(self):
        self.last_selected_port = self.port_combo.currentText()

    def update_ports(self):
        selected = self.port_combo.currentText()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo.clear()
        self.port_combo.addItems(ports)
        if selected in ports:
            self.port_combo.setCurrentText(selected)
            self.last_selected_port = selected
        else:
            self.last_selected_port = None
        self._last_ports = ports

    def check_ports_update(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if ports != self._last_ports:
            self.update_ports()

    def toggle_running(self):
        if not self.running:
            if not self.reader:
                self.start_requested.emit()
            self.start_button.setText("Pausar")
        else:
            if self.reader:
                self.reader.stop()
                self.reader = None
            self.start_button.setText("Iniciar")
            self.recording_enabled = False
            self.record_button.setText("Iniciar grabación")
        self.running = not self.running

    def update_y_range(self):
        self.plot1.setYRange(self.y_min.value(), self.y_max.value())

    def update_x_range(self):
        ms = self.x_ms.value()
        samples = int((ms / 1000) * self.sample_rate)
        if samples > len(self.data_ch1):
            self.data_ch1 = np.pad(self.data_ch1, (samples - len(self.data_ch1), 0), constant_values=0)
        y = self.data_ch1[-samples:]
        x = np.linspace(-samples / self.sample_rate * 1000, 0, samples)
        if len(x) == len(y) and len(x) > 1:
            self.curve1.setData(x, y)

    def autoscale_y(self):
        if len(self.data_ch1) > 0:
            segment = self.data_ch1[-int((self.x_ms.value() / 1000) * self.sample_rate):]
            min_y, max_y = np.min(segment), np.max(segment)
            margin = (max_y - min_y) * 0.1
            self.y_min.setValue(min_y - margin)
            self.y_max.setValue(max_y + margin)

    def update_signals(self, ch1_new, _):
        if not self.running:
            return
        gain = self.gain.value()
        ch1_new = ch1_new * gain
        self.data_ch1 = np.roll(self.data_ch1, -len(ch1_new))
        self.data_ch1[-len(ch1_new):] = ch1_new
        self.update_x_range()

    def closeEvent(self, event):
        print("Cerrando app correctamente...")
        self.running = False
        if self.reader:
            self.reader.stop()
        event.accept()
