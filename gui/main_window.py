from __future__ import annotations

import csv
from datetime import datetime, timezone
import logging
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from bert.commands import (
    COMMANDS,
    POLL_KEYS,
    START_MEASUREMENT_COMMAND,
    STOP_MEASUREMENT_COMMAND,
)
from bert.driver import Bert, BertError
from gui.poller import Poller


class _LogEmitter(QObject):
    message = Signal(str)


class QtLogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.emitter = _LogEmitter()

    def emit(self, record: logging.LogRecord) -> None:
        self.emitter.message.emit(self.format(record))


def _decode_termination(text: str) -> str:
    return bytes(text, "utf-8").decode("unicode_escape")


class MainWindow(QMainWindow):
    def __init__(self, simulate: bool = False) -> None:
        super().__init__()
        self.setWindowTitle("Centellax TG1B1A / Keysight N4962A BERT")
        self.resize(1100, 800)
        self.settings = QSettings("OpenLabTools", "TG1B1A-BERT")
        self.bert: Bert | None = None
        self.poller: Poller | None = None
        self.control_widgets: dict[str, QWidget] = {}
        self.readouts: dict[str, QLabel] = {}
        self.csv_path: Path | None = None

        self._build_ui(simulate)
        self._install_log_handler()
        self.refresh_resources()
        if simulate:
            self.connect_instrument()

    def _build_ui(self, simulate: bool) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)

        connection = QHBoxLayout()
        self.resource = QComboBox()
        self.resource.setEditable(True)
        self.resource.setMinimumWidth(230)
        self.simulate = QCheckBox("Simulate")
        self.simulate.setChecked(simulate)
        refresh = QPushButton("Refresh")
        self.connect_button = QPushButton("Connect")
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setEnabled(False)
        refresh.clicked.connect(self.refresh_resources)
        self.simulate.toggled.connect(self.refresh_resources)
        self.connect_button.clicked.connect(self.connect_instrument)
        self.disconnect_button.clicked.connect(self.disconnect_instrument)
        connection.addWidget(QLabel("VISA resource:"))
        connection.addWidget(self.resource, 1)
        connection.addWidget(self.simulate)
        connection.addWidget(refresh)
        connection.addWidget(self.connect_button)
        connection.addWidget(self.disconnect_button)
        outer.addLayout(connection)
        self.idn_label = QLabel("Not connected")
        self.idn_label.setTextInteractionFlags(self.idn_label.textInteractionFlags())
        outer.addWidget(self.idn_label)

        splitter = QSplitter()
        tabs = QTabWidget()
        tabs.addTab(self._build_controls(), "Controls")
        tabs.addTab(self._build_settings(), "Settings")
        splitter.addWidget(tabs)
        splitter.addWidget(self._build_detector())
        splitter.setSizes([650, 450])
        outer.addWidget(splitter, 3)
        outer.addWidget(self._build_console(), 2)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Disconnected")

    def _build_controls(self) -> QWidget:
        panel = QWidget()
        form = QFormLayout(panel)
        for key, command in COMMANDS.items():
            if key in POLL_KEYS or key == "reset_counters":
                continue
            row = QHBoxLayout()
            if command.choices == ("OFF", "ON"):
                widget: QWidget = QCheckBox()
            elif command.choices:
                combo = QComboBox()
                combo.addItems(command.choices)
                widget = combo
            elif command.minimum is not None and command.maximum is not None:
                if command.integer:
                    spin = QSpinBox()
                    spin.setRange(int(command.minimum), int(command.maximum))
                    spin.setSingleStep(max(1, int(command.step)))
                else:
                    spin = QDoubleSpinBox()
                    spin.setDecimals(3)
                    spin.setRange(command.minimum, command.maximum)
                    spin.setSingleStep(command.step)
                spin.setSuffix(f" {command.units}" if command.units else "")
                widget = spin
            else:
                widget = QLabel("Not configured")
            self.control_widgets[key] = widget
            row.addWidget(widget, 1)

            apply_button = QPushButton("Apply")
            apply_button.setEnabled(command.set is not None)
            apply_button.clicked.connect(lambda _checked=False, name=key: self.apply_control(name))
            row.addWidget(apply_button)
            read_button = QPushButton("Read")
            read_button.setEnabled(command.query is not None)
            read_button.clicked.connect(lambda _checked=False, name=key: self.read_control(name))
            row.addWidget(read_button)

            if command.set is None:
                tip = "command not configured"
                widget.setEnabled(False)
                apply_button.setToolTip(tip)
                widget.setToolTip(tip)
            elif command.help:
                widget.setToolTip(command.help)
            label = command.label or key.replace("_", " ").title()
            form.addRow(label, row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        return scroll

    def _build_detector(self) -> QWidget:
        box = QGroupBox("Error detector")
        layout = QGridLayout(box)
        labels = {"sync_status": "Sync", "error_count": "Errors", "bit_count": "Bits", "ber": "BER"}
        for row, key in enumerate(POLL_KEYS):
            value = QLabel("—")
            value.setStyleSheet("font-size: 22px; font-weight: bold")
            self.readouts[key] = value
            layout.addWidget(QLabel(labels[key]), row, 0)
            layout.addWidget(value, row, 1)
        self.poll_button = QPushButton("Start polling")
        self.poll_button.clicked.connect(self.toggle_polling)
        self.poll_interval = QDoubleSpinBox()
        self.poll_interval.setRange(0.1, 3600)
        self.poll_interval.setValue(float(self.settings.value("poll_interval", 1.0)))
        self.poll_interval.setSuffix(" s")
        reset = QPushButton("Reset counters")
        reset.setEnabled(COMMANDS["reset_counters"].set is not None)
        reset.setToolTip("command not configured")
        choose_csv = QPushButton("Choose CSV…")
        choose_csv.clicked.connect(self.choose_csv)
        self.csv_label = QLabel("CSV logging off")
        layout.addWidget(self.poll_button, 5, 0)
        layout.addWidget(self.poll_interval, 5, 1)
        layout.addWidget(reset, 6, 0, 1, 2)
        layout.addWidget(choose_csv, 7, 0)
        layout.addWidget(self.csv_label, 7, 1)
        layout.setRowStretch(8, 1)
        return box

    def _build_console(self) -> QWidget:
        box = QGroupBox("Raw console and I/O log")
        layout = QVBoxLayout(box)
        command_row = QHBoxLayout()
        self.raw_command = QLineEdit()
        self.raw_command.setPlaceholderText("*IDN?")
        write = QPushButton("Write")
        query = QPushButton("Query")
        write.clicked.connect(lambda: self.run_raw(False))
        query.clicked.connect(lambda: self.run_raw(True))
        command_row.addWidget(self.raw_command, 1)
        command_row.addWidget(write)
        command_row.addWidget(query)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addLayout(command_row)
        layout.addWidget(self.log)
        return box

    def _build_settings(self) -> QWidget:
        panel = QWidget()
        form = QFormLayout(panel)
        self.timeout = QSpinBox()
        self.timeout.setRange(100, 120000)
        self.timeout.setValue(int(self.settings.value("timeout", 3000)))
        self.timeout.setSuffix(" ms")
        self.read_term = QLineEdit(str(self.settings.value("read_termination", r"\n")))
        self.write_term = QLineEdit(str(self.settings.value("write_termination", r"\n")))
        self.visa_library = QLineEdit(str(self.settings.value("visa_library", "")))
        self.visa_library.setPlaceholderText("Auto (or C:\\Windows\\System32\\visa64.dll)")
        form.addRow("Timeout", self.timeout)
        form.addRow("Read termination", self.read_term)
        form.addRow("Write termination", self.write_term)
        form.addRow("VISA library", self.visa_library)
        return panel

    def _install_log_handler(self) -> None:
        self.log_handler = QtLogHandler()
        self.log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        self.log_handler.emitter.message.connect(self.log.append)
        logging.getLogger("bert.io").addHandler(self.log_handler)
        logging.getLogger("bert.io").setLevel(logging.INFO)

    @Slot()
    def refresh_resources(self) -> None:
        current = self.resource.currentText() or str(
            self.settings.value("resource", "GPIB0::18::INSTR")
        )
        try:
            resources = Bert.list_resources(
                sim=self.simulate.isChecked(),
                visa_library=self.visa_library.text().strip() or None if hasattr(self, "visa_library") else None,
            )
        except BertError as exc:
            resources = ()
            self.set_error(str(exc))
        self.resource.clear()
        self.resource.addItems(resources)
        index = self.resource.findText(current)
        if index < 0:
            self.resource.addItem(current)
            index = self.resource.count() - 1
        self.resource.setCurrentIndex(index)

    @Slot()
    def connect_instrument(self) -> None:
        self.disconnect_instrument()
        try:
            self.bert = Bert(
                timeout=self.timeout.value(),
                read_termination=_decode_termination(self.read_term.text()),
                write_termination=_decode_termination(self.write_term.text()),
                visa_library=self.visa_library.text().strip() or None,
            )
            identity = self.bert.connect(self.resource.currentText(), self.simulate.isChecked())
        except Exception as exc:
            self.bert = None
            self.set_error(str(exc))
            QMessageBox.critical(self, "Connection failed", str(exc))
            return
        self.idn_label.setText(identity)
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        self.statusBar().showMessage("Connected")
        self.settings.setValue("resource", self.resource.currentText())

    @Slot()
    def disconnect_instrument(self) -> None:
        self.stop_polling(send_abort=False)
        if self.bert:
            self.bert.close()
            self.bert = None
        self.idn_label.setText("Not connected")
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.statusBar().showMessage("Disconnected")

    def _connected(self) -> Bert | None:
        if not self.bert or not self.bert.connected:
            self.set_error("instrument is not connected")
            return None
        return self.bert

    def _value_for(self, key: str) -> str:
        widget = self.control_widgets[key]
        if isinstance(widget, QCheckBox):
            return "ON" if widget.isChecked() else "OFF"
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            value = widget.value()
            return str(int(value)) if COMMANDS[key].integer else f"{value:g}"
        raise BertError("control has no configured value")

    @Slot(str)
    def apply_control(self, key: str) -> None:
        bert = self._connected()
        command = COMMANDS[key]
        if not bert or not command.set:
            return
        value = self._value_for(key)
        if key == "data_path" and value != "OFF":
            answer = QMessageBox.warning(
                self,
                "Enable RF output?",
                f"{value} enables the PRBS generator. Confirm attached equipment is safe for the configured level.",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return
        try:
            bert.write(command.set.format(value=value))
        except BertError as exc:
            self.set_error(str(exc))

    @Slot(str)
    def read_control(self, key: str) -> None:
        bert = self._connected()
        command = COMMANDS[key]
        if not bert or not command.query:
            return
        try:
            reply = bert.query(command.query)
            widget = self.control_widgets[key]
            if isinstance(widget, QCheckBox):
                widget.setChecked(command.parse(reply))
            elif isinstance(widget, QComboBox):
                index = widget.findText(reply.strip().upper())
                if index >= 0:
                    widget.setCurrentIndex(index)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.setValue(float(command.parse(reply)))
        except (BertError, ValueError) as exc:
            self.set_error(str(exc))

    @Slot()
    def toggle_polling(self) -> None:
        if self.poller and self.poller.isRunning():
            self.stop_polling()
            return
        bert = self._connected()
        if not bert:
            return
        try:
            bert.write(START_MEASUREMENT_COMMAND)
        except BertError as exc:
            self.set_error(str(exc))
            return
        self.poller = Poller(bert, self.poll_interval.value(), self)
        self.poller.values.connect(self.update_readouts)
        self.poller.failed.connect(self.poll_failed)
        self.poller.finished.connect(self.poll_finished)
        self.poller.start()
        self.poll_button.setText("Stop polling")
        self.poll_interval.setEnabled(False)

    def stop_polling(self, send_abort: bool = True) -> None:
        if self.poller:
            self.poller.stop()
            self.poller.wait(max(1000, self.timeout.value() + 500))
            self.poller = None
        if send_abort and self.bert and self.bert.connected:
            try:
                self.bert.write(STOP_MEASUREMENT_COMMAND)
            except BertError as exc:
                self.set_error(str(exc))
        if hasattr(self, "poll_button"):
            self.poll_button.setText("Start polling")
            self.poll_interval.setEnabled(True)

    @Slot(dict)
    def update_readouts(self, values: dict[str, object]) -> None:
        for key, value in values.items():
            if key == "sync_status":
                text = "CLOCK" if value else "NO RX CLOCK"
            elif key == "ber" and isinstance(value, float):
                text = f"{value:.3e}"
            else:
                text = str(value)
            self.readouts[key].setText(text)
        if self.csv_path:
            new_file = not self.csv_path.exists() or self.csv_path.stat().st_size == 0
            try:
                with self.csv_path.open("a", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=("timestamp", *POLL_KEYS))
                    if new_file:
                        writer.writeheader()
                    writer.writerow(
                        {"timestamp": datetime.now(timezone.utc).isoformat(), **values}
                    )
            except OSError as exc:
                self.set_error(f"CSV logging failed: {exc}")
                self.csv_path = None
                self.csv_label.setText("CSV logging off")

    @Slot(str)
    def poll_failed(self, message: str) -> None:
        self.set_error(message)
        self.stop_polling(send_abort=False)

    @Slot()
    def poll_finished(self) -> None:
        self.poll_button.setText("Start polling")
        self.poll_interval.setEnabled(True)

    @Slot()
    def choose_csv(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Measurement CSV", str(self.csv_path or Path.home() / "bert.csv"), "CSV (*.csv)"
        )
        if filename:
            self.csv_path = Path(filename)
            self.csv_label.setText(self.csv_path.name)
            self.csv_label.setToolTip(str(self.csv_path))

    def _confirm_reset(self, command: str) -> bool:
        if not command.strip().upper().startswith("*RST"):
            return True
        return (
            QMessageBox.warning(
                self,
                "Reset instrument?",
                "*RST changes instrument state. Continue?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            == QMessageBox.Yes
        )

    @Slot()
    def run_raw(self, query: bool) -> None:
        bert = self._connected()
        command = self.raw_command.text().strip()
        if not bert or not command or not self._confirm_reset(command):
            return
        try:
            if query:
                reply = bert.query(command)
                self.log.append(f"REPLY {reply}")
            else:
                bert.write(command)
        except BertError as exc:
            self.set_error(str(exc))

    def set_error(self, message: str) -> None:
        self.statusBar().showMessage(f"Error: {message}")
        logging.getLogger("bert.io").error(message)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.settings.setValue("timeout", self.timeout.value())
        self.settings.setValue("read_termination", self.read_term.text())
        self.settings.setValue("write_termination", self.write_term.text())
        self.settings.setValue("visa_library", self.visa_library.text())
        self.settings.setValue("poll_interval", self.poll_interval.value())
        self.disconnect_instrument()
        logging.getLogger("bert.io").removeHandler(self.log_handler)
        event.accept()
