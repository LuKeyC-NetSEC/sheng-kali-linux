#!/bin/bash
# SPDX-License-Identifier: MIT
set -euo pipefail
project=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
source_dir=${1:-"$project/out/osk-source"}
[[ $(uname -m) == aarch64 ]]
[[ -f "$source_dir/fcitx5-osk-kwin-launcher/src/native_policy.rs" ]]
cd "$source_dir"
# Cargo.lock fixes registry/git revisions and crate checksums. Only the launcher
# is rebuilt: do not replace a working FUTO UI or import a user's IME data.
cargo test --locked --jobs 2 --package fcitx5-osk-kwin-launcher
cargo build --locked --jobs 2 --release --package fcitx5-osk-kwin-launcher
printf 'Built %s; nothing was installed or restarted.\n' "$source_dir/target/release/fcitx5-osk-kwin-launcher"
