#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
project=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
source_dir=${1:-"$project/out/kwin-native-source"}
build_dir="$source_dir/obj-aarch64-linux-gnu"
[[ -f "$build_dir/CMakeCache.txt" ]]
cmake -S "$source_dir" -B "$build_dir" -DBUILD_TESTING=ON
cmake --build "$build_dir" --target testVirtualKeyboardDBus --parallel 2
test_binary="$build_dir/bin/testVirtualKeyboardDBus"
[[ -x $test_binary ]]
# A private bus/runtime/config prevents the harness from contacting the real
# compositor or changing the user's InputMethod, windows, or lockscreen.
test_root=$(mktemp -d)
mkdir -m 700 "$test_root/runtime" "$test_root/config" "$test_root/data" "$test_root/cache"
trap 'find "$test_root" -type f -delete; find "$test_root" -type s -delete; find "$test_root" -depth -type d -empty -delete' EXIT
env -u DISPLAY -u WAYLAND_DISPLAY -u WAYLAND_SOCKET -u DBUS_SESSION_BUS_ADDRESS \
    XDG_RUNTIME_DIR="$test_root/runtime" XDG_CONFIG_HOME="$test_root/config" \
    XDG_DATA_HOME="$test_root/data" XDG_CACHE_HOME="$test_root/cache" \
    dbus-run-session -- "$test_binary"
