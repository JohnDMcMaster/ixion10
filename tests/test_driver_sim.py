from __future__ import annotations

import pytest

from bert.commands import COMMANDS
from bert.driver import Bert, BertError


def test_connect_and_idn() -> None:
    bert = Bert(timeout=500)
    try:
        identity = bert.connect("GPIB0::18::INSTR", sim=True)
        assert "CENTELLAX" in identity
        assert "TG1B1-A" in bert.idn()
    finally:
        bert.close()


def test_unknown_query_is_readable_error() -> None:
    bert = Bert(timeout=100)
    try:
        bert.connect("GPIB0::18::INSTR", sim=True)
        with pytest.raises(BertError, match=r"(timeout|VISA I/O failed)"):
            bert.query(":NOT:A:REAL:COMMAND?")
    finally:
        bert.close()


def test_every_set_command_has_documentation() -> None:
    undocumented = [name for name, command in COMMANDS.items() if command.set and not command.doc_ref]
    assert undocumented == []


def test_unconfigured_controls_cannot_emit_commands() -> None:
    assert COMMANDS["reset_counters"].set is None
    assert COMMANDS["local_remote"].set is None


def test_every_query_parses_simulated_reply() -> None:
    bert = Bert(timeout=500)
    try:
        bert.connect("GPIB0::18::INSTR", sim=True)
        for command in COMMANDS.values():
            if command.query:
                command.parse(bert.query(command.query))
        assert COMMANDS["bit_count"].parse("1.00000e10") == 10_000_000_000
    finally:
        bert.close()
