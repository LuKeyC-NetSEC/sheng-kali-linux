#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Brief offscreen Freedreno/Turnip/Zink readback check; no frequency changes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

PROJECT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--stage', type=Path, help='Root of unpacked complete Mesa package set')
    group.add_argument('--package-dir', type=Path, help='Unpack and validate the complete pinned package set')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    output = (args.output_dir or (args.package_dir / 'smoke-stage' if args.package_dir else PROJECT / 'out/mesa-smoke')).resolve()
    output.mkdir(parents=True, exist_ok=False)
    pin = json.loads((PROJECT / 'device/gpu-driver/provenance.json').read_text())
    package_hashes = {}
    if args.package_dir:
        args.stage = output / 'stage'
        args.stage.mkdir()
        for package in sorted(args.package_dir.resolve().glob('*.deb')):
            def field(name):
                return subprocess.check_output(['dpkg-deb', '-f', str(package), name], text=True).strip()
            name = field('Package')
            if name not in pin['packages']:
                continue
            if name in package_hashes or field('Version') != pin['packageVersion'] or field('Architecture') != 'arm64':
                raise SystemExit('Package identity mismatch: ' + name)
            package_hashes[name] = hashlib.sha256(package.read_bytes()).hexdigest()
            subprocess.run(['dpkg-deb', '-x', str(package), str(args.stage)], check=True)
        if set(package_hashes) != set(pin['packages']):
            raise SystemExit('Incomplete package set')
    for name in ('bench.cpp', 'scene.vert', 'scene.frag', 'build.sh'):
        shutil.copy2(PROJECT / 'device/gpu-bench' / name, output / name)
    subprocess.run(['bash', 'build.sh'], cwd=output, check=True)
    env = os.environ.copy()
    for key in ('MESA_LOADER_DRIVER_OVERRIDE', 'GALLIUM_DRIVER', 'LIBGL_DRIVERS_PATH',
                'VK_DRIVER_FILES', 'VK_ICD_FILENAMES', '__EGL_VENDOR_LIBRARY_FILENAMES',
                'LD_LIBRARY_PATH', 'LIBGL_ALWAYS_SOFTWARE'):
        env.pop(key, None)
    libdir = Path('/usr/lib/aarch64-linux-gnu')
    if args.stage:
        stage = args.stage.resolve()
        libdir = stage / 'usr/lib/aarch64-linux-gnu'
        env['LD_LIBRARY_PATH'] = str(libdir)
        env['LIBGL_DRIVERS_PATH'] = str(libdir / 'dri')
        egl = stage / 'usr/share/glvnd/egl_vendor.d/50_mesa.json'
        if not egl.exists():
            raise SystemExit('Missing staged EGL vendor manifest')
        env['__EGL_VENDOR_LIBRARY_FILENAMES'] = str(egl)
    # Select only Turnip; never fall through silently to Lavapipe or another ICD.
    icds = list((args.stage.resolve() if args.stage else Path('/')).glob('usr/share/vulkan/icd.d/freedreno_icd*.json'))
    if len(icds) != 1:
        raise SystemExit('Expected exactly one Turnip ICD')
    manifest = json.loads(icds[0].read_text())
    library = libdir / Path(manifest['ICD']['library_path']).name
    if not library.is_file():
        raise SystemExit('Missing matching Turnip library')
    manifest['ICD']['library_path'] = str(library)
    icd = output / 'turnip-test.json'
    icd.write_text(json.dumps(manifest))
    env['VK_DRIVER_FILES'] = str(icd)
    # Full diagnostics stay local; publish only the renderer and version lines.
    diagnostics = {}
    for name, command in (
        ('egl', ['eglinfo', '-B', '-p', 'surfaceless']),
        ('vulkan', ['vulkaninfo', '--summary']),
    ):
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)
        (output / (name + '.log')).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise SystemExit(name + ' diagnostics failed; see private log')
        diagnostics[name] = [line.strip() for line in result.stdout.splitlines()
                             if any(key in line for key in ('Mesa ', 'driverName', 'driverInfo', 'deviceName'))]
    if not all(pin['version'] in '\n'.join(lines) for lines in diagnostics.values()):
        raise SystemExit('Renderer version does not match pinned upstream in both APIs')
    runs = {}
    for path, api in (('freedreno', 'gl'), ('turnip', 'vk'), ('zink', 'gl')):
        runenv = env.copy()
        if path == 'zink':
            runenv.update(MESA_LOADER_DRIVER_OVERRIDE='zink', GALLIUM_DRIVER='zink')
        result = subprocess.run([str(output / 'bench'), api, 'fill', '0.1', path],
                                cwd=output, env=runenv, capture_output=True, text=True, timeout=60)
        (output / (path + '.log')).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise SystemExit(path + ' rendering failed; see private log')
        info = json.loads((output / (path + '.json')).read_text())
        if path == 'freedreno' and 'FD740' not in info['renderer']:
            raise SystemExit('Expected native Adreno 740 OpenGL renderer')
        if path == 'zink' and 'zink' not in info['renderer'].lower():
            raise SystemExit('Zink override did not take effect')
        image = output / (path + '.rgba')
        if image.stat().st_size != 3048 * 2032 * 4:
            raise SystemExit('Incomplete image readback')
        runs[path] = {'renderer': info['renderer'], 'sha256': hashlib.sha256(image.read_bytes()).hexdigest()}
    identical = len({run['sha256'] for run in runs.values()}) == 1
    report = {'version': pin['version'], 'stage': bool(args.stage), 'packageHashes': package_hashes, 'diagnostics': diagnostics,
              'runs': runs, 'identicalReadback': identical, 'frequencyChanged': False}
    (output / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))
    if not identical:
        raise SystemExit('GL/Vulkan/Zink image readback differs')


if __name__ == '__main__':
    main()
