"""Thread-safe PyVISA driver for the TG1B1A / N4962A."""

from __future__ import annotations

import logging
from pathlib import Path
import sys
import threading
import time
import warnings

import pyvisa
from pyvisa.errors import VisaIOError


LOG = logging.getLogger("bert.io")
EXPECTED_ID = ("TG1B1", "N4962A")


class BertError(RuntimeError):
    """Readable instrument communication error."""


class Bert:
    def __init__(
        self,
        *,
        timeout: int = 3000,
        read_termination: str = "\n",
        write_termination: str = "\n",
        visa_library: str | None = None,
    ) -> None:
        self.timeout = timeout
        self.read_termination = read_termination
        self.write_termination = write_termination
        self.visa_library = visa_library
        self._rm: pyvisa.ResourceManager | None = None
        self._session = None
        self._lock = threading.Lock()
        self._error_query_supported = True
        self.identity = ""

    @property
    def connected(self) -> bool:
        return self._session is not None

    @staticmethod
    def _sim_library() -> str:
        return f"{Path(__file__).with_name('sim.yaml')}@sim"

    @staticmethod
    def _default_library() -> str | None:
        # PyVISA-py is the FOSS backend used with Linux-GPIB. Other platforms
        # retain PyVISA's normal vendor-backend discovery unless overridden.
        return "@py" if sys.platform.startswith("linux") else None

    @classmethod
    def list_resources(
        cls, *, sim: bool = False, visa_library: str | None = None
    ) -> tuple[str, ...]:
        try:
            library = cls._sim_library() if sim else visa_library or cls._default_library()
            rm = pyvisa.ResourceManager(library)
            try:
                return tuple(rm.list_resources())
            finally:
                rm.close()
        except Exception as exc:
            raise BertError(f"could not list VISA resources: {exc}") from exc

    def connect(self, resource: str, sim: bool = False) -> str:
        self.close()
        library = self._sim_library() if sim else self.visa_library or self._default_library()
        try:
            self._rm = pyvisa.ResourceManager(library)
        except Exception as first:
            if sim or self.visa_library or sys.platform.startswith("linux"):
                raise BertError(f"could not load VISA: {first}") from first
            try:
                self._rm = pyvisa.ResourceManager(r"C:\Windows\System32\visa64.dll")
            except Exception as second:
                raise BertError(
                    f"could not load VISA ({first}); visa64.dll fallback failed ({second})"
                ) from second

        try:
            with self._lock:
                self._session = self._rm.open_resource(resource)
                self._session.timeout = self.timeout
                self._session.read_termination = self.read_termination
                self._session.write_termination = self.write_termination
            self._error_query_supported = True
            self.identity = self.idn()
        except Exception as exc:
            self.close()
            if isinstance(exc, BertError):
                raise
            raise BertError(f"could not connect to {resource!r}: {exc}") from exc

        if not any(token in self.identity.upper() for token in EXPECTED_ID):
            warnings.warn(
                f"unexpected instrument identity: {self.identity}", RuntimeWarning
            )
        return self.identity

    def close(self) -> None:
        with self._lock:
            if self._session is not None:
                try:
                    self._session.close()
                finally:
                    self._session = None
            if self._rm is not None:
                try:
                    self._rm.close()
                finally:
                    self._rm = None
        self.identity = ""

    def _require_session(self):
        if self._session is None:
            raise BertError("instrument is not connected")
        return self._session

    @staticmethod
    def _format_error(exc: Exception, cmd: str, timeout: int) -> BertError:
        if isinstance(exc, VisaIOError) and exc.error_code == pyvisa.constants.StatusCode.error_timeout:
            return BertError(
                f"timeout: instrument did not answer {cmd!r} within {timeout / 1000:g} s"
            )
        return BertError(f"VISA I/O failed for {cmd!r}: {exc}")

    def write(self, cmd: str) -> None:
        cmd = cmd.strip()
        if not cmd:
            raise BertError("command is empty")
        started = time.monotonic()
        try:
            with self._lock:
                self._require_session().write(cmd)
        except Exception as exc:
            error = self._format_error(exc, cmd, self.timeout)
            LOG.error("WRITE %s failed after %.3f s: %s", cmd, time.monotonic() - started, error)
            raise error from exc
        LOG.info("WRITE %s (%.3f s)", cmd, time.monotonic() - started)

    def query(self, cmd: str) -> str:
        cmd = cmd.strip()
        if not cmd:
            raise BertError("command is empty")
        started = time.monotonic()
        try:
            with self._lock:
                reply = self._require_session().query(cmd).strip()
        except Exception as exc:
            error = self._format_error(exc, cmd, self.timeout)
            LOG.error("QUERY %s failed after %.3f s: %s", cmd, time.monotonic() - started, error)
            raise error from exc
        LOG.info("QUERY %s -> %s (%.3f s)", cmd, reply, time.monotonic() - started)
        return reply

    def idn(self) -> str:
        return self.query("*IDN?")

    def clear_status(self) -> None:
        self.write("*CLS")

    def check_error(self) -> str | None:
        if not self._error_query_supported:
            return None
        try:
            return self.query("SYST:ERR?")
        except BertError:
            self._error_query_supported = False
            LOG.warning("SYST:ERR? unsupported; disabling automatic error checks")
            return None

    def __enter__(self) -> "Bert":
        return self

    def __exit__(self, *_args) -> None:
        self.close()
