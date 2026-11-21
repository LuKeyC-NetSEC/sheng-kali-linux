#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare a pinned, reviewed MiPPS source tree; never install or run it."""
import argparse
import ast
import hashlib
import io
import json
import pathlib
import shutil
import subprocess
import tarfile
import urllib.request

PROJECT = pathlib.Path(__file__).resolve().parents[1]
LOCAL = PROJECT / 'device/charging'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=pathlib.Path, help='Optional cached archive; its fixed hash is still required')
    parser.add_argument('--output-dir', type=pathlib.Path, default=PROJECT / 'out/mipps-source')
    args = parser.parse_args()
    pin = json.loads((LOCAL / 'provenance.json').read_text(encoding='utf-8'))
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit('Choose a fresh, empty output directory')
    patch = (LOCAL / 'mipps-hardening.patch').read_bytes().replace(b'\r\n', b'\n')
    if sha(patch) != pin['patch_sha256']:
        raise SystemExit('Patch SHA-256 mismatch; review provenance first')
    if args.archive:
        archive_data = args.archive.read_bytes()
    else:
        url = pin['upstream'].replace('https://github.com/', 'https://codeload.github.com/') + '/tar.gz/' + pin['commit']
        with urllib.request.urlopen(url, timeout=60) as response:
            archive_data = response.read()
    if sha(archive_data) != pin['archive_sha256']:
        raise SystemExit('Upstream archive SHA-256 mismatch')
    entries = {}
    with tarfile.open(fileobj=io.BytesIO(archive_data), mode='r:gz') as archive:
        for item in archive.getmembers():
            parts = pathlib.PurePosixPath(item.name).parts[1:]
            if not parts or item.isdir():
                continue
            if not item.isfile() or '..' in parts or any('\\' in part or ':' in part for part in parts):
                raise SystemExit('Unsupported archive member')
            relative = pathlib.PurePosixPath(*parts).as_posix()
            entries[relative] = (archive.extractfile(item).read(), item.mode)
    for name, expected in pin['base_files'].items():
        if name not in entries or sha(entries[name][0]) != expected:
            raise SystemExit('Unexpected base source: ' + name)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, (data, mode) in entries.items():
        target = args.output_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o755 if mode & 0o111 else 0o644)
    subprocess.run(['git', 'apply', '--check', '-'], input=patch, cwd=args.output_dir, check=True)
    subprocess.run(['git', 'apply', '-'], input=patch, cwd=args.output_dir, check=True)
    control = args.output_dir / 'DEBIAN/control'
    text = control.read_text(encoding='utf-8').replace('Version: 0.21\n', 'Version: 0.21+sheng1\n')
    control.write_bytes(text.encode('utf-8'))
    ast.parse((args.output_dir / 'xiaomi-mipps-auth').read_text(encoding='utf-8'))
    for name in ('provenance.json', 'mipps-hardening.patch', 'README.md'):
        shutil.copyfile(LOCAL / name, args.output_dir / ('Sheng-' + name))
    (args.output_dir / 'NOTICE.sheng').write_text(
        'Modified upstream source for Xiaomi Pad 6S Pro (sheng), GPL-2.0-only.\n'
        'Source: ' + pin['upstream'] + '@' + pin['commit'] + '\n'
        'Offline hardening: attachment checks, bounded retry service, verdict checks,\n'
        'sanitized authentication logs and accurate capability notifications.\n'
        'Protocol reference: Xiaomi official sheng-u-oss; no property-ID replacement.\n'
        'No device installation, key extraction, thermal bypass or power-limit change.\n', encoding='utf-8')
    print(json.dumps({'upstream_commit': pin['commit'], 'patch_sha256': pin['patch_sha256'],
                      'status': 'source prepared only; device unmodified'}, indent=2))


if __name__ == '__main__':
    main()
