from data_provider import DataProvider
from filters import butter_bandpass_filter, notch_filter
import serial
import threading
import numpy as np
import time
import os
import queue

class SerialReader(DataProvider):
    def __init__(self, port='COM12', baudrate=230400, samples_per_update=100, viewer=None):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.samples_per_update = samples_per_update
        self.viewer = viewer

        self.ser = None
        self.running = False
        self.thread = None
        self.buffer_ch1 = []

        # Grabación
        self.csv_file = None
        self.write_queue = queue.Queue()
        self.writer_thread = None
        self.writer_running = False

    def start(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=0)
            self.running = True
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()
        except serial.SerialException as e:
            print(f"[SerialReader] Error al abrir el puerto {self.port}: {e}")

    def stop(self):
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.stop_recording()

    def run(self):
        input_buffer = []
        try:
            while self.running and self.ser and self.ser.is_open:
                data = self.ser.read(512)
                if data:
                    input_buffer += list(data)
                    while len(input_buffer) >= 2:
                        msb = input_buffer.pop(0)
                        if msb & 0x80:
                            if len(input_buffer) < 1:
                                break
                            lsb = input_buffer.pop(0)
                            if lsb & 0x80:
                                continue
                            val = ((msb & 0x7F) << 7) | (lsb & 0x7F)
                            value = val - 8192
                            self.buffer_ch1.append(value)

                            if len(self.buffer_ch1) >= self.samples_per_update:
                                chunk_size = self.viewer.chunk_size.value()
                                if len(self.buffer_ch1) < chunk_size:
                                    continue

                                chunk = np.array(self.buffer_ch1[-chunk_size:])
                                filtered = self.apply_filters(chunk)

                                if self.writer_running:
                                    for val in filtered[-self.samples_per_update:]:
                                        self.write_queue.put(f"{val}\n")

                                self.new_data.emit(filtered[-self.samples_per_update:], None)
                                del self.buffer_ch1[:self.samples_per_update]
                time.sleep(0.001)
        except Exception as e:
            print(f"[SerialReader] Error en run(): {e}")

    def apply_filters(self, data):
        if not self.viewer:
            return data

        fs = self.viewer.sample_rate

        try:
            if self.viewer.center_signal.isChecked():
                data = data - np.mean(data)

            if self.viewer.enable_notch.isChecked():
                f0 = self.viewer.notch_freq.value()
                Q = self.viewer.notch_q.value()
                harmonics = self.viewer.notch_harmonics.value()
                data = notch_filter(data, fs, f0=f0, Q=Q, harmonics=harmonics)

            if self.viewer.enable_butter.isChecked():
                lowcut = self.viewer.butter_lowcut.value()
                highcut = self.viewer.butter_highcut.value()
                order = self.viewer.butter_order.value()
                data = butter_bandpass_filter(data, fs, lowcut, highcut, order)

        except Exception as e:
            print(f"[SerialReader] Error aplicando filtros: {e}")

        return data

    def start_recording(self):
        if self.writer_running:
            return

        path = os.path.join(
            self.viewer.output_folder,
            self.viewer.filename_input.text() + ".csv"
        )

        try:
            self.csv_file = open(path, "w", buffering=1)  # línea por línea
            self.csv_file.write(f"# sample_rate: {self.viewer.sample_rate}\n")
            self.csv_file.write("valor\n")

            self.writer_running = True
            self.writer_thread = threading.Thread(target=self._write_loop, daemon=True)
            self.writer_thread.start()

            print(f"[SerialReader] Grabación iniciada en {path}")
        except Exception as e:
            print(f"[SerialReader] Error iniciando grabación: {e}")

    def _write_loop(self):
        try:
            while self.writer_running:
                try:
                    line = self.write_queue.get(timeout=0.5)
                    if self.csv_file:
                        self.csv_file.write(line)
                except queue.Empty:
                    continue
        except Exception as e:
            print(f"[SerialReader] Error en hilo de escritura: {e}")

    def stop_recording(self):
        if not self.writer_running:
            return

        print("[SerialReader] Deteniendo grabación...")
        self.writer_running = False

        if self.writer_thread:
            self.writer_thread.join(timeout=2)

        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
        print("[SerialReader] Grabación detenida")
