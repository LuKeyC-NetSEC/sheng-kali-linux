#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
project=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
source_dir=${1:-"$project/out/plasma-native-source"}
[[ $(uname -m) == aarch64 ]]
[[ $(dpkg-query -W -f='${Version}' plasma-workspace) == 4:6.7.4-2* ]]
[[ $(dpkg-query -W -f='${Version}' libqt6core6t64:arm64) == 6.11.2+dfsg-5 ]]
[[ -f "$source_dir/shell/shengdesktoppolicy.cpp" ]]
python3 - "$source_dir" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1])/'debian/changelog';text=path.read_text()
if not text.startswith('plasma-workspace (4:6.7.4-2+sheng1)'):
    path.write_text('''plasma-workspace (4:6.7.4-2+sheng1) unstable; urgency=medium

  * Move sheng panel and input-presence policy into the native shell.
  * Handle empty touch cancellations before accessing event points.

 -- Sheng Kali builders <noreply@localhost>  Sat, 21 Nov 2026 17:00:00 +0800

'''+text)
PY
cd "$source_dir"
dpkg-buildpackage --build=binary --no-sign --no-pre-clean -j2
dpkg-source --before-build "$source_dir"
printf 'Built matched Plasma packages; nothing was installed or restarted.\n'
