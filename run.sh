#!/usr/bin/env bash
#
# Launch the BERT control GUI. Extra arguments are passed through,
# e.g. ./run.sh --sim

set -Eeuo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [[ " $* " != *" --sim "* ]] && command -v lsusb >/dev/null; then
    if lsusb -d 0957:0518 | grep -q .; then
        echo "WARNING: 82357B firmware is not loaded (0957:0518); replug the adapter." >&2
    elif ! lsusb -d 0957:0718 | grep -q .; then
        echo "WARNING: no 82357B adapter found on USB." >&2
    elif [[ ! -e /dev/gpib0 ]]; then
        echo "WARNING: /dev/gpib0 is missing; run: sudo gpib_config --minor 0" >&2
    fi
fi

exec uv run python -m gui.main "$@"
