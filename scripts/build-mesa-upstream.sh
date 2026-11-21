#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
project=$(cd -- "$(dirname -- "$0")/.." && pwd)
source_dir=${1:-"$project/out/mesa-upstream-source"}
[[ $(uname -s) == Linux && $(dpkg --print-architecture) == arm64 ]] || {
    echo 'Use an ARM64 Linux build host.' >&2; exit 1;
}
[[ -f "$source_dir/sheng-provenance.json" ]] || {
    echo 'Run scripts/prepare-mesa-upstream.py first.' >&2; exit 1;
}
cd -- "$source_dir"
dpkg-checkbuilddeps
# Tests remain enabled. No GPU frequency changes or installation.
export DEB_BUILD_OPTIONS="parallel=${JOBS:-4}"
extra=()
[[ ${RESUME:-0} != 1 ]] || extra+=(-nc)
dpkg-buildpackage -b -us -uc "${extra[@]}"
