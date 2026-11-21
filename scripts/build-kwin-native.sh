#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
project=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
source_dir=${1:-"$project/out/kwin-native-source"}
[[ $(uname -m) == aarch64 ]]
[[ $(dpkg-query -W -f='${Version}' kwin-wayland) == 4:6.7.4-2* ]]
[[ $(dpkg-query -W -f='${Version}' libqt6core6t64:arm64) == 6.11.2+dfsg-5 ]]
python3 - "$source_dir" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1])/'debian/changelog';text=path.read_text()
if not text.startswith('kwin (4:6.7.4-2+sheng1)'):
    path.write_text('''kwin (4:6.7.4-2+sheng1) unstable; urgency=medium

  * Add atomic input-method restart and native three-finger TabBox handling.

 -- Sheng Kali builders <noreply@localhost>  Sat, 21 Nov 2026 14:00:00 +0800

'''+text)
PY
cd "$source_dir"
dpkg-buildpackage --build=binary --no-sign --no-pre-clean -j2
dpkg-source --before-build "$source_dir"
printf 'Built matched native KWin packages; nothing was installed or restarted.\n'
