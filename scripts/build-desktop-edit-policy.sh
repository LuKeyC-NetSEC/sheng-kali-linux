#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
project=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
build_dir=${1:-"$project/out/build-desktop-edit-policy"}
[[ $(uname -m) == aarch64 ]]
[[ $(dpkg-query -W -f='${Version}' libqt6core6t64:arm64) == 6.11.2+dfsg-5 ]]
cmake -S "$project/device/desktop-edit-policy" -B "$build_dir" -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr -DKDE_INSTALL_PLUGINDIR="$(qmake6 -query QT_INSTALL_PLUGINS)"
cmake --build "$build_dir" --parallel 2
cat "$build_dir/policy-id.txt"
