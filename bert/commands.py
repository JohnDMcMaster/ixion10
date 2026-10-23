"""Documented N4962A commands.

Every instrument-specific string lives in this module.  References are to
N4962-91021, edition 6.0.  Add commands only after checking that manual (or a
TG1B1A manual); use ``None`` when the hardware has no documented command.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


def parse_bool(value: str) -> bool:
    return value.strip().upper() in {"1", "ON"}


def parse_count(value: str) -> int:
    # The TG1B1A reports counts in exponent form, e.g. "0.00000e0".
    return int(float(value))


@dataclass(frozen=True)
class Cmd:
    set: str | None = None
    query: str | None = None
    parse: Callable[[str], Any] = str
    choices: tuple[str, ...] | None = None
    units: str = ""
    doc_ref: str = ""
    minimum: float | None = None
    maximum: float | None = None
    step: float = 1.0
    integer: bool = False
    label: str = ""
    help: str = ""


COMMANDS: dict[str, Cmd] = {
    "clock_source": Cmd(
        ":SOURce:ROSCillator:SOURce {value}",
        ":SOURce:ROSCillator:SOURce?",
        choices=("INT", "EXT"),
        doc_ref="N4962A User's Guide pp. 60-61",
        label="Clock source",
    ),
    "data_rate": Cmd(
        ":SOURce:ROSCillator:INTernal:FREQuency {value}",
        ":SOURce:ROSCillator:INTernal:FREQuency?",
        parse=float,
        units="MHz",
        doc_ref="N4962A User's Guide pp. 60, 62-63",
        minimum=9900,
        maximum=11350,
        step=1,
        integer=True,
        label="Internal data rate",
        help="Guaranteed internal-clock range; external mode can report 500-12500 MHz.",
    ),
    "jitter_injection": Cmd(
        ":SOURce:ROSCillator:JITTer {value}",
        ":SOURce:ROSCillator:JITTer?",
        parse=parse_bool,
        choices=("OFF", "ON"),
        doc_ref="N4962A User's Guide pp. 60, 63-64",
        label="Jitter injection",
    ),
    "pattern": Cmd(
        ":SOURce:PATTern {value}",
        ":SOURce:PATTern?",
        choices=("PRBS7", "PRBS10", "PRBS15", "PRBS23", "PRBS31"),
        doc_ref="N4962A User's Guide pp. 60, 65",
        label="PRBS pattern",
    ),
    "mark_space": Cmd(
        ":SOURce:PRBS:MARKspace {value}",
        ":SOURce:PRBS:MARKspace?",
        choices=("MS2", "MS4", "MS8"),
        doc_ref="N4962A User's Guide pp. 60, 66",
        label="Mark density",
    ),
    "pattern_invert": Cmd(
        ":SOURce:PRBS:INVert {value}",
        ":SOURce:PRBS:INVert?",
        parse=parse_bool,
        choices=("OFF", "ON"),
        doc_ref="N4962A User's Guide pp. 60, 67",
        label="Pattern invert",
    ),
    "error_injection": Cmd(
        ":SOURce:PRBS:IERR:RATe {value}",
        ":SOURce:PRBS:IERR:RATe?",
        choices=("OFF", "ERR1E0", "ERR1E1", "ERR1E2", "ERR1E3", "ERR1E4", "ERR1E5", "ERR1E6", "ERR1E7"),
        doc_ref="N4962A User's Guide pp. 60, 68",
        label="Error injection",
    ),
    "output_amplitude": Cmd(
        ":SOURce:VOLTage:AMPLitude {value}",
        ":SOURce:VOLTage:AMPLitude?",
        parse=float,
        units="mVpp/side",
        doc_ref="N4962A User's Guide pp. 60, 69",
        minimum=300,
        maximum=1800,
        step=10,
        integer=True,
        label="Output amplitude",
    ),
    "output_enable": Cmd(
        label="Output enable",
        help="No separate output-enable command is documented; use Data path OFF/NORM/THRU.",
    ),
    "data_path": Cmd(
        ":MODe {value}",
        ":MODe?",
        choices=("OFF", "NORM", "THRU"),
        doc_ref="N4962A User's Guide p. 70",
        label="Data path / output",
        help="OFF is safe mode; NORM and THRU enable the PRBS generator.",
    ),
    "no_data_sense": Cmd(
        ":SENSe:NOData {value}",
        ":SENSe:NOData?",
        parse=parse_bool,
        choices=("OFF", "ON"),
        doc_ref="N4962A User's Guide p. 71",
        label="No-data sense",
    ),
    "autophase_time": Cmd(
        ":SENSe:APTime {value}",
        # The query times out on TG1B1A firmware 1.38.
        None,
        parse=int,
        units="0.1 ms",
        doc_ref="N4962A User's Guide pp. 72-73",
        minimum=1,
        maximum=5000,
        integer=True,
        label="Autophase dwell",
        help="TG1B1A firmware 1.38 does not answer the documented query.",
    ),
    "receiver_phase": Cmd(
        ":SENSe:ROSCillator:PHASe {value}",
        ":SENSe:ROSCillator:PHASe?",
        parse=float,
        units="degrees",
        doc_ref="N4962A User's Guide pp. 73-74",
        minimum=0,
        maximum=358,
        step=2,
        integer=True,
        label="Receiver phase",
    ),
    "measurement_time": Cmd(
        ":SENSe:SWEep:TIME {value}",
        ":SENSe:SWEep:TIME?",
        parse=float,
        units="s",
        doc_ref="N4962A User's Guide pp. 74-75",
        minimum=0.001,
        maximum=4194303.999,
        step=0.001,
        label="Measurement time",
    ),
    "training_delay": Cmd(
        ":SENSe:TRAIn {value}",
        ":SENSe:TRAIn?",
        parse=int,
        units="0.1 µs",
        doc_ref="N4962A User's Guide pp. 75-76",
        minimum=10,
        maximum=6500,
        integer=True,
        label="Training delay",
    ),
    "receiver": Cmd(
        ":TRIGger:{value}",
        None,
        choices=("ABORT", "INITIATE"),
        doc_ref="N4962A User's Guide p. 77",
        label="Receiver",
    ),
    "reset_on_standby": Cmd(label="Reset on standby"),
    "local_remote": Cmd(label="Local / remote"),
    "sync_status": Cmd(
        # ":SYSTem:STATus? NORXCLK" times out on TG1B1A firmware 1.38.
        query=None,
        parse=lambda value: value.strip() == "1",
        doc_ref="N4962A User's Guide p. 72",
        label="Sync",
        help="Unsupported by TG1B1A firmware 1.38.",
    ),
    "error_count": Cmd(
        query=":SENSe:DATA? ECOunt",
        parse=parse_count,
        doc_ref="N4962A User's Guide p. 78",
        label="Error count",
    ),
    "bit_count": Cmd(
        query=":SENSe:DATA? BCOunt",
        parse=parse_count,
        doc_ref="N4962A User's Guide p. 78",
        label="Bit count",
    ),
    "ber": Cmd(
        query=":SENSe:DATA? BER",
        parse=float,
        doc_ref="N4962A User's Guide p. 78",
        label="BER",
    ),
    "reset_counters": Cmd(label="Reset counters"),
}

POLL_KEYS = ("sync_status", "error_count", "bit_count", "ber")
SAMPLE_COMMAND = ":TRIGger:SAMPle"
START_MEASUREMENT_COMMAND = ":TRIGger:INITiate"
STOP_MEASUREMENT_COMMAND = ":TRIGger:ABORt"
