"""Non-blocking measurement poller."""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QThread, Signal

from bert.commands import COMMANDS, POLL_KEYS, SAMPLE_COMMAND
from bert.driver import Bert


class Poller(QThread):
    values = Signal(dict)
    failed = Signal(str)

    def __init__(self, bert: Bert, interval: float = 1.0, parent=None) -> None:
        super().__init__(parent)
        self.bert = bert
        self.interval = interval
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            result: dict[str, object] = {}
            try:
                data_keys = [key for key in POLL_KEYS if key != "sync_status" and COMMANDS[key].query]
                if data_keys:
                    self.bert.write(SAMPLE_COMMAND)
                for key in POLL_KEYS:
                    command = COMMANDS[key]
                    if command.query:
                        result[key] = command.parse(self.bert.query(command.query))
                if result:
                    self.values.emit(result)
            except Exception as exc:
                self.failed.emit(str(exc))
                return
            remaining = max(0.0, self.interval - (time.monotonic() - started))
            self._stop.wait(remaining)
