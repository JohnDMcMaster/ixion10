# TG1B1A / N4962A BERT control

Python control GUI for the Centellax TG1B1A (Keysight N4962A) serial BERT. It
uses the documented GPIB commands from N4962-91021, edition 6.0, and includes a
simulator for development without hardware.

The application does **not** enable the PRBS output at connection time. The
instrument's `OFF` data path is its safe mode. Selecting `NORM` or `THRU`
requires an explicit Apply action and confirmation. Observe the manual's RF,
50-ohm termination, ESD, and maximum-input requirements.

## Install

Install [uv](https://docs.astral.sh/uv/), then create/update the locked
Python 3.11+ environment:

```console
uv sync
```

Before using real hardware, close Keysight Interactive IO and N4980A, then
confirm that Keysight Connection Expert can communicate with
`GPIB0::18::INSTR`. The default backend is the installed VISA implementation.
If discovery fails, enter `C:\Windows\System32\visa64.dll` on the Settings tab.

Linux uses an entirely open-source host stack: Linux-GPIB's
`agilent_82357a` driver, `gpib-ctypes`, PyVISA-py, and PyVISA. The Python
components are installed by `uv sync`, and the app selects PyVISA-py (`@py`)
automatically on Linux. USB enumeration alone does not provide a GPIB device;
Linux-GPIB must first provide `/dev/gpib0`.

For the current Ubuntu 24.04 / Linux 6.8 host, install Linux-GPIB 4.3.7 from
its [official release](https://sourceforge.net/projects/linux-gpib/files/linux-gpib%20for%203.x.x%20and%202.6.x%20kernels/4.3.7/).
The included setup script downloads the checksum-pinned release, builds both
components, configures board zero, and synchronizes the uv environment:

```console
./setup.sh
```

To perform the same setup manually, build and install both included components:

```console
sudo apt install build-essential linux-headers-$(uname -r) \
  autoconf automake libtool pkg-config flex bison libusb-1.0-0-dev fxload
make -C linux-gpib-kernel-4.3.7
sudo make -C linux-gpib-kernel-4.3.7 install
cd linux-gpib-user-4.3.7
./configure --sysconfdir=/etc
make
sudo make install
sudo ldconfig
```

Configure `/etc/gpib.conf` with `board_type = "agilent_82357a"`, load the
module, and configure board zero:

```console
sudo modprobe agilent_82357a
sudo gpib_config --minor 0
ls -l /dev/gpib0
uv run pyvisa-info
```

PyVISA should then report a working `GPIB INTFC` backend without a
`GPIB library not found` warning.

Genuine 82357B adapters need firmware uploaded after every power-up. They
enumerate as `0957:0518` until Linux-GPIB's udev rule runs `fxload`, then
re-enumerate as `0957:0718`. `setup.sh` installs the firmware from
[linux_gpib_firmware](https://github.com/fmhess/linux_gpib_firmware) into
`/usr/local/share/usb/agilent_82357a/`; to do it manually, copy
`agilent_82357a/measat_releaseX1.8.hex` there and replug the adapter. Some
clones carry their own firmware and appear as `0957:0718` immediately; the
included kernel patch supports them.

## Run

Simulator:

```console
uv run python -m gui.main --sim
```

Real instrument:

```console
uv run python -m gui.main
```

Connect verifies `*IDN?` but permits an unexpected identity with a warning.
The raw console is intentionally unrestricted for trying commands from the
manual. Sending `*RST` requires confirmation.

## Controls and measurements

All instrument-specific strings are centralized in `bert/commands.py`, with
manual page references. Unsupported features remain disabled rather than
guessing a command. In particular, the manual documents no command dedicated
to reset-on-standby, reset counters, or front-panel local/remote switching.

Start polling explicitly starts a BER acquisition, samples it at the selected
interval, and reads clock presence, error count, bit count, and BER in a worker
thread. Stop polling aborts acquisition. Choose a CSV path to append UTC
timestamps and measurements.

The bundled simulator is defined in `bert/sim.yaml`. When adding a command to
`bert/commands.py`, add a matching dialogue and fake response to that file.

## Test

```console
uv run pytest
```

## Troubleshooting

- **VISA library not found:** select `visa64.dll` explicitly on Windows.
- **Timeout:** check LF terminations, GPIB address 18, and that no other
  application owns the session.
- **No resource despite USB detection:** the 82357B being visible to the OS
  does not prove the VISA/GPIB driver has claimed it.
- **No `/dev/gpib0`:** if `lsusb` shows `0957:0518`, the adapter firmware
  has not been loaded (see Install).
- **Unanswered documented queries:** TG1B1A firmware 1.38 does not answer
  `:SENSe:APTime?`, `:SYSTem:STATus?` or `SYST:ERR?`, so autophase readback
  and the RX-clock indicator are disabled.
- **No RX clock:** the supplied TX CKO-to-TX CKI loop clocks the generator, not
  the receiver. BER measurement also requires RX clock and data connections.

PyMeasure could provide a higher-level instrument/experiment framework in a
future version, but is not required for this GUI.
