#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare pinned Mesa and reviewed Kali packaging for Adreno 740; no install."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import urllib.request

PROJECT = Path(__file__).resolve().parents[1]
COMPONENT = PROJECT / 'device/gpu-driver'
BUILD_DEPENDS = '''debhelper-compat (= 13), bison, flex, glslang-tools, libgtest-dev,
 libdrm-dev (>= 2.4.134), libelf-dev, libexpat1-dev, libglvnd-core-dev,
 libwayland-dev, libwayland-egl-backend-dev, libx11-dev, libx11-xcb-dev,
 libxcb-dri2-0-dev, libxcb-dri3-dev, libxcb-glx0-dev, libxcb-present-dev,
 libxcb-randr0-dev, libxcb-shm0-dev, libxcb-sync-dev, libxext-dev,
 libxrandr-dev, libxshmfence-dev, libxxf86vm-dev, libzstd-dev,
 libdisplay-info-dev, libpng-dev, libsensors-dev, libvulkan-dev,
 llvm-21-dev, meson (>= 1.7.0), pkgconf, python3, python3-mako,
 python3-ply, python3-pycparser, python3-setuptools, python3-yaml,
 wayland-protocols (>= 1.41), x11proto-dev, zlib1g-dev'''


def fetch(url, destination, expected):
    if not destination.exists():
        partial = destination.with_suffix(destination.suffix + '.part')
        with urllib.request.urlopen(url, timeout=120) as source, partial.open('wb') as target:
            shutil.copyfileobj(source, target)
        partial.replace(destination)
    if hashlib.sha256(destination.read_bytes()).hexdigest() != expected:
        raise SystemExit('Archive hash mismatch: ' + destination.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=PROJECT / 'out/mesa-upstream-source')
    parser.add_argument('--cache-dir', type=Path, default=PROJECT / 'out/mesa-upstream-downloads')
    args = parser.parse_args()
    if not shutil.which('gpgv'):
        raise SystemExit('Use Linux with gpgv, debian-keyring, patch and dpkg-dev')
    if args.output_dir.exists():
        raise SystemExit('Choose a fresh output directory')
    pin = json.loads((COMPONENT / 'provenance.json').read_text())
    for name, expected in pin['local_files'].items():
        actual = hashlib.sha256((COMPONENT / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        if actual != expected:
            raise SystemExit('Reviewed local source hash mismatch: ' + name)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    upstream = args.cache_dir / ('mesa-' + pin['version'] + '.tar.xz')
    fetch(pin['upstream']['url'], upstream, pin['upstream']['sha256'])
    packaging = pin['packaging']
    for name, expected in packaging['archives'].items():
        fetch(packaging['baseUrl'] + name, args.cache_dir / name, expected)
    dsc = args.cache_dir / ('mesa_' + packaging['version'] + '.dsc')
    subprocess.run(['gpgv', '--keyring', '/usr/share/keyrings/debian-keyring.pgp', str(dsc)], check=True)
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(upstream) as archive:
        archive.extractall(args.output_dir.parent, filter='data')
    extracted = args.output_dir.parent / ('mesa-' + pin['version'])
    extracted.rename(args.output_dir)
    with tarfile.open(args.cache_dir / ('mesa_' + packaging['version'] + '.debian.tar.xz')) as archive:
        archive.extractall(args.output_dir, filter='data')
    debian = args.output_dir / 'debian'
    # driDestroyConfigs moved out of the GLX header upstream. Rebase only the
    # distribution patch context; preserve its original typedef and guard.
    shutil.copyfile(COMPONENT / 'src_glx_dri_common.h.diff',
                    debian / 'patches/src_glx_dri_common.h.diff')
    runtime_patch = '0001-gallivm-linux-arm64-runtime-features.patch'
    shutil.copyfile(COMPONENT / runtime_patch, debian / 'patches' / runtime_patch)
    with (debian / 'patches/series').open('a') as series:
        series.write('\n' + runtime_patch + '\n')
    # Both distribution patches plus the runtime fix must apply with zero fuzz.
    for entry in (debian / 'patches/series').read_text().splitlines():
        if entry.strip() and not entry.startswith('#'):
            patch = debian / 'patches' / entry.strip()
            subprocess.run(['patch', '--dry-run', '--batch', '--fuzz=0', '-p1', '-i', str(patch.resolve())],
                           cwd=args.output_dir, check=True)
    subprocess.run(['dpkg-source', '--before-build', str(args.output_dir)], check=True)
    control = (debian / 'control').read_text()
    sections = control.strip().split('\n\n')
    sections[0] = re.sub(r'Build-Depends:.*?(?=\n\S)', 'Build-Depends: ' + BUILD_DEPENDS,
                         sections[0], flags=re.S)
    selected = [sections[0]]
    for section in sections[1:]:
        match = re.search(r'^Package: (.+)$', section, re.M)
        if match and match[1] in pin['packages']:
            selected.append(section)
    if len(selected) != len(pin['packages']) + 1:
        raise SystemExit('Distribution package layout changed')
    (debian / 'control').write_text('\n\n'.join(selected) + '\n')
    shutil.copy2(debian / 'rules', debian / 'rules.distribution')
    shutil.copyfile(COMPONENT / 'rules', debian / 'rules')
    (debian / 'rules').chmod(0o755)
    # No RADV is built in this device-specific profile.
    install = debian / 'mesa-vulkan-drivers.install'
    install.write_text(install.read_text().replace('usr/share/drirc.d/00-radv-defaults.conf\n', '')
                       + 'usr/share/drirc.d/00-turnip-defaults.conf\n'
                       + 'usr/share/drirc.d/00-lavapipe-defaults.conf\n')
    with (debian / 'mesa-libgallium.install').open('a') as install:
        install.write('usr/share/drirc.d/00-msm-defaults.conf\nusr/share/drirc.d/00-zink-defaults.conf\n')
    with (debian / 'mesa-common-dev.install').open('a') as install:
        install.write('usr/include/EGL/eglext_angle.h\nusr/include/EGL/eglmesaext.h\n')
    changelog = debian / 'changelog'
    changelog.write_text(
        f"mesa ({pin['packageVersion']}) unstable; urgency=medium\n\n"
        '  * Sync upstream stable for sheng: Freedreno, Turnip, Zink and software fallback.\n'
        '  * Retain distribution patches, ABI metadata and package dependencies.\n'
        '  * Device profile excludes other GPUs, VA/VDPAU, OpenCL and Teflon.\n'
        '  * Respect absent SVE/RNG in LLVM 21 ARM64 JIT, following LLVM 22.\n\n'
        ' -- Sheng Linux contributors <noreply@example.invalid>  Sat, 21 Nov 2026 10:00:00 +0000\n\n'
        + changelog.read_text())
    shutil.copy2(COMPONENT / 'provenance.json', args.output_dir / 'sheng-provenance.json')
    print(json.dumps({'source': str(args.output_dir), 'version': pin['packageVersion'],
                      'packages': pin['packages']}))


if __name__ == '__main__':
    main()
