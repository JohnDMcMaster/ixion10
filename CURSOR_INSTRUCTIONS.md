# Build spec: MVP control GUI for a Centellax TG1B1A (Keysight N4962A) BERT

Paste this whole file into Cursor, or put it in the repo root and point Cursor at it.

## 1. Context (all verified on the real hardware)

- **Instrument:** Centellax TG1B1A "10G BERT", serial SN5048, firmware 1.38. Keysight later sold the same instrument as the **N4962A Serial BERT 12.5 Gb/s**.
- **Why a custom app:** Keysight's N4980A software (versions 3.3.2905 and 3.2.2888) reaches the instrument but rejects its identity string, so the vendor GUI can't be used.
- **PC:** Windows 11 x64, running as a VMware VM.
- **GPIB adapter:** Keysight 82357B USB-GPIB, with Keysight IO Libraries Suite 21.4.204. The Keysight VISA shipped with that suite is installed and working.
- **VISA resource:** `GPIB0::18::INSTR`
- **`*IDN?` works.** It returns `CENTELLAX, TG1B1-A BERT, SN5048, 1.38\n`, so replies end with a line feed (`\n`).
- **Remote interface:** GPIB only, as far as we know. The N4962A User's Guide has a "Remote GPIB Interface" chapter that covers GPIB command syntax, the IEEE common commands, the SCPI mandated commands, the N4962A device commands, and examples.

## 2. Rule #1: do not invent instrument commands

We don't have the TG1B1A/N4962A command list in this repo yet. **Never guess SCPI commands** for pattern, rate, amplitude, error count, BER and so on. Put every instrument-specific command in one table (`bert/commands.py`), leave them as `None` with a `TODO` until the user fills them in from the N4962A User's Guide, and make the GUI disable any control whose command is `None`.

The only commands the app may send without being configured are `*IDN?`, `*CLS`, and `SYST:ERR?`. `SYST:ERR?` must be optional: if it times out or errors, treat it as unsupported and stop sending it.

Never send `*RST` or anything else that changes instrument state unless the user clicks the control for it. `*RST` also needs a confirmation dialog.

## 3. Tech stack

- Python 3.11+ (64-bit).
- **PyVISA** using the installed Keysight VISA: `pyvisa.ResourceManager()`. If it can't find the library, fall back to `ResourceManager(r"C:\Windows\System32\visa64.dll")`.
- **PySide6** for the GUI.
- **pyvisa-sim** for a simulated instrument, so the app can be developed and tested without the hardware.
- `pytest` for tests.
- No other dependencies unless they're clearly needed.

(Alternative, not for the MVP: **PyMeasure** gives you an instrument-driver base class and a ready-made experiment GUI. Mention it in the README as a possible upgrade path.)

## 4. Project layout

```
tg1b1a-bert-gui/
  README.md
  requirements.txt
  bert/
    __init__.py
    commands.py      # the ONLY place instrument-specific commands live
    driver.py        # thin PyVISA wrapper: connect, write, query, idn, error check
    sim.yaml         # pyvisa-sim definition (IDN + placeholder responses)
  gui/
    main.py          # entry point: python -m gui.main [--sim]
    main_window.py
    poller.py        # QThread / QObject worker for periodic queries
  tests/
    test_driver_sim.py
```

## 5. Driver (`bert/driver.py`)

- `class Bert` with `connect(resource: str, sim: bool = False)`, `close()`, `idn()`, `write(cmd)`, `query(cmd)`, `check_error()`.
- Session settings: `read_termination="\n"`, `write_termination="\n"`, `timeout=3000` ms. Make all three configurable.
- One `threading.Lock` around every I/O call. GPIB sessions must not be used by two threads at once.
- Log every write/query, with its reply and duration, through Python `logging`. The GUI shows this log.
- Wrap VISA errors in a custom `BertError` with a readable message, for example "timeout: instrument did not answer 'XYZ?' within 3 s".
- `connect()` checks `*IDN?`. If the reply doesn't contain `TG1B1` or `N4962A`, warn but still allow the connection.

## 6. Command table (`bert/commands.py`)

A plain dataclass or dict per function, for example:

```python
@dataclass
class Cmd:
    set: str | None = None       # e.g. "XXXX {value}"; None = unknown
    query: str | None = None     # e.g. "XXXX?"; None = unknown
    parse: Callable[[str], Any] = str
    choices: list[str] | None = None
    units: str = ""
    doc_ref: str = ""            # page in the N4962A User's Guide
```

Add entries named for what a BERT normally needs, with `set`/`query` left as `None`:

- data rate / clock source
- pattern (PRBS type) and pattern invert
- output amplitude and output enable
- data path select (the front panel shows Disabled / Enabled / Thru)
- receiver on/off and "reset on standby"
- error detector: sync status, error count, bit count, BER, reset counters
- local/remote (the front panel has a Local button)

Include a short comment at the top explaining how to fill the table from the manual.

## 7. GUI (`gui/`)

One window with four areas:

1. **Connection bar.** A resource dropdown filled from `rm.list_resources()`, defaulting to `GPIB0::18::INSTR`; buttons for Refresh, Connect, and Disconnect; a "Simulate" checkbox; and a label showing the `*IDN?` reply.
2. **Controls panel.** Built automatically from `commands.py`: a dropdown for entries with `choices`, a spin box for numbers, a toggle for on/off. A control is disabled, with a tooltip saying "command not configured", when its `set` is `None`. Each control has a "Read" button when its `query` is set.
3. **Error detector panel.** Big readouts for Sync, Error count, Bit count, and BER, plus a Start/Stop polling button, a poll interval (default 1 s), and "Reset counters". Only the queries that are configured get polled. Polling runs in a worker thread and must never block the UI.
4. **Raw console.** A text box to type any command, buttons for Write and Query, and a scrolling log of everything sent and received, with timestamps. This is the main tool for trying commands from the manual.

Also:

- **Log to CSV.** When polling is on, append a timestamp plus each polled value to a CSV file the user picks.
- A status bar showing the connection state and the last error.
- Settings (resource, timeout, terminations, poll interval) saved with `QSettings`.

## 8. Simulator (`bert/sim.yaml`)

A pyvisa-sim device at `GPIB0::18::INSTR` that:

- answers `*IDN?` with `CENTELLAX, TG1B1-A BERT, SN5048, 1.38`,
- accepts `*CLS`,
- returns fake values for whatever query strings end up in `commands.py`. Document how to add them.

Run with: `python -m gui.main --sim`

## 9. Tests

`tests/test_driver_sim.py` covers:

- connecting to the simulator,
- reading `*IDN?`,
- getting a `BertError` on timeout, or on an unknown command if pyvisa-sim returns an error,
- the command table: every entry that has `set` also has a `doc_ref`.

## 10. README

- Install steps: `py -m venv .venv`, activate it, then `pip install -r requirements.txt`.
- A check that Keysight Connection Expert sees `GPIB0::18::INSTR` before you run the app.
- How to fill `commands.py` from the N4962A User's Guide ("N4962A Device Commands" section).
- How to run the app for real and with `--sim`.
- Troubleshooting:
  - VISA library not found: pass the `visa64.dll` path.
  - Timeouts: check the terminations and the GPIB address.
  - Close Keysight Interactive IO and the N4980A software first so they don't hold the session.

## 11. Acceptance criteria for the MVP

- `python -m gui.main --sim` opens, connects, and shows the IDN with no hardware attached.
- On the real PC, Connect shows `CENTELLAX, TG1B1-A BERT, SN5048, 1.38`.
- The raw console can send `*IDN?` and show the reply.
- Controls with unconfigured commands are visibly disabled, and nothing crashes.
- Polling with no configured queries does nothing and doesn't error.
- Closing the window closes the VISA session cleanly.

## 12. Ask the user before building past the MVP

- Do you have the N4962A (or TG1B1A) User's Guide PDF? If so, add it to `docs/` so the command table can be filled in.
- Which functions matter most (for example, PRBS generator only vs. full error-detector BER runs)?
