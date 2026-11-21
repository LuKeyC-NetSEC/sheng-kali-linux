#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
project=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
source_dir=${1:-"$project/out/powerdevil-source"}
[[ $(uname -m) == aarch64 ]]
[[ $(dpkg-query -W -f='${Version}' powerdevil) == 4:6.7.4-2* ]]
[[ $(dpkg-query -W -f='${Version}' libqt6core6t64:arm64) == 6.11.2+dfsg-5 ]]
[[ -f "$source_dir/daemon/shengpolicy.cpp" ]]
python3 - "$source_dir" <<'PY'
from pathlib import Path
import sys
source=Path(sys.argv[1]); path=source/'debian/changelog'
text=path.read_text()
if not text.startswith('powerdevil (4:6.7.4-2+sheng2)'):
    header='''powerdevil (4:6.7.4-2+sheng2) unstable; urgency=medium

  * Integrate sheng power policy, lock synchronization and resume handling
    natively into PowerDevil; retain all Debian patches.
  * Blank and lock after one idle minute while preserving the separate
    five-minute low-battery suspend policy and user customizations.

 -- Sheng Kali builders <noreply@localhost>  Sat, 21 Nov 2026 12:00:00 +0800

'''
    path.write_text(header+text)
PY
cd "$source_dir"
dpkg-buildpackage --build=binary --no-sign --no-pre-clean -j2
# Run upstream migration tests and the native policy test in an isolated config.
build=$(find "$source_dir" -maxdepth 1 -type d -name 'obj-*' -print -quit)
[[ -n $build ]]
test_config=$(mktemp -d)
trap 'rmdir "$test_config" 2>/dev/null || true' EXIT
env QT_QPA_PLATFORM=offscreen XDG_CONFIG_HOME="$test_config" ctest --test-dir "$build" --output-on-failure
# Debian un-applies quilt patches after packaging; retain the reviewed native
# source tree for inspection without rebuilding the already-tested artifacts.
dpkg-source --before-build "$source_dir"
printf 'Built native PowerDevil packages beside %s; the running service was not changed.\n' "$source_dir"
