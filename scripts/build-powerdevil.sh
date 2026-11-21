#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
project=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
source_dir=${1:-"$project/out/powerdevil-source"}
source_dir=$(realpath -- "$source_dir")
[[ $(uname -m) == aarch64 ]]
[[ $(dpkg-query -W -f='${Version}' powerdevil) == 4:6.7.4-2* ]]
[[ $(dpkg-query -W -f='${Version}' libqt6core6t64:arm64) == 6.11.2+dfsg-5 ]]
[[ -f "$source_dir/daemon/shengpolicy.cpp" ]]
python3 - "$source_dir" <<'PY'
from pathlib import Path
import sys
source=Path(sys.argv[1]); path=source/'debian/changelog'
text=path.read_text()
if not text.startswith('powerdevil (4:6.7.4-2+sheng5)'):
    header='''powerdevil (4:6.7.4-2+sheng5) unstable; urgency=medium

  * Integrate sheng power policy, lock synchronization and resume handling
    natively into PowerDevil; retain all Debian patches.
  * Blank and lock after one idle minute while preserving the separate
    five-minute low-battery suspend policy and user customizations.
  * Remove the DPMS fade stage and minimize tablet lock-to-display-off delay.
  * Route the protected short power-button action directly through native DPMS.
  * Backport the KDE 6.7 dimming restoration fix (76dc5ace), preserving the
    user's selected brightness; add an isolated backend regression test.

 -- Sheng Kali builders <noreply@localhost>  Sat, 21 Nov 2026 12:00:00 +0800

'''
    path.write_text(header+text)
PY
cd "$source_dir"
# A prior debhelper build stamp can skip compilation after patch changes.
# Clean the generated build/staging state so package contents match the source.
dpkg-buildpackage --build=binary --no-sign -j2
# Run upstream migration tests and the native policy test in an isolated config.
build=$(find "$source_dir" -maxdepth 1 -type d -name 'obj-*' -print -quit)
[[ -n $build ]]
test_config=$(mktemp -d)
trap 'rmdir "$test_config" 2>/dev/null || true' EXIT
env QT_QPA_PLATFORM=offscreen XDG_CONFIG_HOME="$test_config" ctest --test-dir "$build" --output-on-failure
# Debian un-applies quilt patches after packaging; retain the reviewed native
# source tree for inspection without rebuilding the already-tested artifacts.
dpkg-source --before-build "$source_dir"
brightness_build="${source_dir}.brightness-tests"
cmake -S "$project/device/power-management/brightness-tests" -B "$brightness_build" \
    -DPOWERDEVIL_SOURCE_DIR="$source_dir"
cmake --build "$brightness_build" --parallel 2
ctest --test-dir "$brightness_build" --output-on-failure
printf 'Built native PowerDevil packages beside %s; the running service was not changed.\n' "$source_dir"
