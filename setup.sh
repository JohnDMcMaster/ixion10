#!/usr/bin/env bash
#
# Install the all-FOSS Linux host stack for an Agilent/Keysight 82357B.
# This installs Linux-GPIB 4.3.7, configures board 0, and syncs the uv project.
#
# Run as your normal desktop user: ./setup.sh

set -Eeuo pipefail

readonly VERSION="4.3.7"
readonly ARCHIVE="linux-gpib-${VERSION}.tar.gz"
readonly URL="https://downloads.sourceforge.net/project/linux-gpib/linux-gpib%20for%203.x.x%20and%202.6.x%20kernels/${VERSION}/${ARCHIVE}"
readonly SHA256="b3ff812606865c85b58b012a4218a6fe3b82d177c8c0abc795cb22db41f3ad68"
readonly FIRMWARE_REPO="https://github.com/fmhess/linux_gpib_firmware"
readonly FIRMWARE_COMMIT="8a5c6c2c1a2adac4c770763a7236452a871a0113"
readonly FIRMWARE_DIR="/usr/local/share/usb/agilent_82357a"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly CLONE_PATCH="${SCRIPT_DIR}/patches/linux-gpib-4.3.7-82357b-clone.patch"
readonly BUILD_ROOT="${XDG_CACHE_HOME:-${HOME}/.cache}/centellax-linux-gpib"
readonly SOURCE_ROOT="${BUILD_ROOT}/linux-gpib-${VERSION}"

log() {
    printf '\n==> %s\n' "$*"
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

on_error() {
    printf '\nSetup failed at line %s. Fix the error above and rerun this script.\n' "$1" >&2
}
trap 'on_error "$LINENO"' ERR

[[ "$(uname -s)" == "Linux" ]] || die "this setup is Linux-only"
[[ "${EUID}" -ne 0 ]] || die "run this as your normal user, not as root"
command -v apt-get >/dev/null || die "this script currently supports Debian/Ubuntu (apt)"
command -v sudo >/dev/null || die "sudo is required to install the kernel driver"

log "Requesting administrator access"
sudo -v

log "Installing build prerequisites"
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    "linux-headers-$(uname -r)" \
    autoconf \
    automake \
    libtool \
    pkg-config \
    flex \
    bison \
    libusb-1.0-0-dev \
    libusb-dev \
    fxload \
    curl \
    ca-certificates \
    git

mkdir -p "${BUILD_ROOT}"
cd "${BUILD_ROOT}"

if [[ ! -f "${ARCHIVE}" ]]; then
    log "Downloading Linux-GPIB ${VERSION}"
    curl --fail --location --retry 3 --output "${ARCHIVE}.part" "${URL}"
    mv "${ARCHIVE}.part" "${ARCHIVE}"
fi

log "Verifying source archive"
printf '%s  %s\n' "${SHA256}" "${ARCHIVE}" | sha256sum --check -

if [[ ! -d "${SOURCE_ROOT}" ]]; then
    tar xzf "${ARCHIVE}"
fi
cd "${SOURCE_ROOT}"

# This is a script-owned build cache. Re-extracting makes reruns reproducible
# and removes stale or experimental patches from earlier builds.
rm -rf "linux-gpib-kernel-${VERSION}"
tar xzf "linux-gpib-kernel-${VERSION}.tar.gz"
if [[ ! -d "linux-gpib-user-${VERSION}" ]]; then
    tar xzf "linux-gpib-user-${VERSION}.tar.gz"
fi

log "Applying 82357B firmware-bearing clone support"
[[ -f "${CLONE_PATCH}" ]] || die "missing driver patch: ${CLONE_PATCH}"
if ! grep -q "is_clone_82357b" \
    "linux-gpib-kernel-${VERSION}/drivers/gpib/agilent_82357a/agilent_82357a.c"; then
    patch -d "linux-gpib-kernel-${VERSION}" -p1 < "${CLONE_PATCH}"
fi

log "Building Linux-GPIB kernel modules for $(uname -r)"
make -C "linux-gpib-kernel-${VERSION}" clean
make -C "linux-gpib-kernel-${VERSION}" -j"$(nproc)"
if grep -q '^agilent_82357a ' /proc/modules; then
    sudo modprobe --remove agilent_82357a
fi
sudo make -C "linux-gpib-kernel-${VERSION}" install
sudo depmod -a
sudo modprobe agilent_82357a

log "Building Linux-GPIB userspace library and tools"
cd "${SOURCE_ROOT}/linux-gpib-user-${VERSION}"
if [[ -f Makefile ]]; then
    make distclean >/dev/null 2>&1 || true
fi
./configure --sysconfdir=/etc
make -j"$(nproc)"
sudo make install
sudo ldconfig

log "Installing 82357A/B firmware for genuine adapters"
# Genuine 82357B adapters enumerate as 0957:0518 until the udev rule
# installed above uploads this firmware; they then become 0957:0718.
firmware_src="${BUILD_ROOT}/linux_gpib_firmware"
if [[ ! -d "${firmware_src}/.git" ]]; then
    git clone --quiet "${FIRMWARE_REPO}" "${firmware_src}"
fi
git -C "${firmware_src}" fetch --quiet origin
git -C "${firmware_src}" -c advice.detachedHead=false checkout --quiet "${FIRMWARE_COMMIT}"
sudo install -d "${FIRMWARE_DIR}"
sudo install -m 0644 \
    "${firmware_src}/agilent_82357a/measat_releaseX1.8.hex" \
    "${firmware_src}/agilent_82357a/82357a_fw.hex" \
    "${FIRMWARE_DIR}/"

log "Configuring the 82357B as GPIB board 0"
if [[ -f /etc/gpib.conf ]] && ! grep -q 'board_type[[:space:]]*=[[:space:]]*"agilent_82357a"' /etc/gpib.conf; then
    backup="/etc/gpib.conf.backup.$(date +%Y%m%d-%H%M%S)"
    sudo cp /etc/gpib.conf "${backup}"
    printf 'Existing /etc/gpib.conf backed up to %s\n' "${backup}"
fi
sudo tee /etc/gpib.conf >/dev/null <<'EOF'
interface {
    minor = 0
    board_type = "agilent_82357a"
    name = "82357b"
    pad = 0
    master = yes
}
EOF

log "Configuring non-root access through the plugdev group"
getent group plugdev >/dev/null || sudo groupadd --system plugdev
sudo usermod -aG plugdev "${USER}"
sudo tee /etc/udev/rules.d/98-gpib-local.rules >/dev/null <<'EOF'
KERNEL=="gpib[0-9]*", MODE="0660", GROUP="plugdev"
EOF
sudo udevadm control --reload-rules

gpib_config=""
for candidate in \
    "$(command -v gpib_config 2>/dev/null || true)" \
    /usr/local/sbin/gpib_config \
    /usr/sbin/gpib_config; do
    if [[ -n "${candidate}" && -x "${candidate}" ]]; then
        gpib_config="${candidate}"
        break
    fi
done
[[ -n "${gpib_config}" ]] || die "gpib_config was not installed"

log "Initializing GPIB board 0"
if command -v lsusb >/dev/null && lsusb -d 0957:0518 | grep -q .; then
    # Plugged in before the firmware existed: load it now instead of replugging.
    busdev="$(lsusb -d 0957:0518 | awk 'NR == 1 { sub(":", "", $4); print $2 "/" $4 }')"
    sudo fxload -t fx2 -D "/dev/bus/usb/${busdev}" -I "${FIRMWARE_DIR}/measat_releaseX1.8.hex"
    for _ in $(seq 20); do
        lsusb -d 0957:0718 | grep -q . && break
        sleep 0.5
    done
fi
if command -v lsusb >/dev/null && lsusb -d 0957:0718 | grep -q .; then
    sudo "${gpib_config}" --minor 0
    if [[ -e /dev/gpib0 ]]; then
        sudo chgrp plugdev /dev/gpib0
        sudo chmod 0660 /dev/gpib0
    else
        printf 'WARNING: /dev/gpib0 was not created.\n' >&2
    fi
else
    printf '82357B is unplugged; skipping board initialization.\n'
    printf 'Plug it in after setup, then run: sudo %s --minor 0\n' "${gpib_config}"
fi

log "Synchronizing the Python environment"
command -v uv >/dev/null || die "uv is not installed"
cd "${SCRIPT_DIR}"
uv sync

log "Checking the open-source VISA backend"
uv run pyvisa-info

cat <<'EOF'

Setup complete.

Log out and back in before using /dev/gpib0 so the plugdev membership applies.
Then verify the instrument with:

uv run python - <<'PY'
import pyvisa
rm = pyvisa.ResourceManager("@py")
instrument = rm.open_resource(
    "GPIB0::18::INSTR",
    read_termination="\n",
    write_termination="\n",
)
instrument.timeout = 3000
print(instrument.query("*IDN?"))
instrument.close()
rm.close()
PY

If lsusb still reports 0957:0518 rather than 0957:0718, the firmware did not
load; unplug and replug the adapter so udev retries it.

Rerun this setup after installing a new Linux kernel.
EOF
