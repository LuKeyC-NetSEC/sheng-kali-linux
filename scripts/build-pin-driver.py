#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build the PIN module on its exact running ARM64 kernel; never load or flash it."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import urllib.request

PROJECT = Path(__file__).resolve().parents[1]
LOCAL = PROJECT / 'device/keyboard-driver'


def run(args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, help='Optional pristine tree of the pinned commit')
    parser.add_argument('--build-dir', type=Path, default=PROJECT/'out/pin-driver')
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    pin = json.loads((LOCAL/'provenance.json').read_text())
    if platform.system() != 'Linux' or platform.machine() != 'aarch64' or os.geteuid() != 0:
        raise SystemExit('Run with sudo on the target ARM64 Linux tablet')
    if platform.release() != pin['kernel_abi'] or run(['clang-21', '--version']).splitlines()[0] != pin['compiler']:
        raise SystemExit('Running kernel/compiler differs from the reviewed ABI')
    build = args.build_dir.resolve()
    build.mkdir(parents=True, exist_ok=True)
    source = args.source_dir.resolve() if args.source_dir else build/'source'
    if args.source_dir:
        if run(['git','-C',str(source),'rev-parse','HEAD']) != pin['kernel_commit']:
            raise SystemExit('Optional source checkout is not the pinned commit')
        subprocess.run(['git','-C',str(source),'diff','--exit-code','HEAD','--'], check=True)
    if not args.source_dir:
        archive = build/'kernel.tar.gz'
        if not archive.exists():
            with urllib.request.urlopen(pin['archive_url'], timeout=60) as response, archive.open('wb') as output:
                shutil.copyfileobj(response, output)
        if sha(archive) != pin['archive_sha256']:
            raise SystemExit('Kernel archive hash mismatch')
        source.mkdir(exist_ok=True)
        subprocess.run(['tar', '-xf', str(archive), '--strip-components=1', '-C', str(source)], check=True)
    driver = source/'drivers/hid/hid-nanosic-wn8030.c'
    if sha(driver) != pin['driver_baseline_sha256']:
        raise SystemExit('Expected a pristine pinned driver; use a separate module build directory')
    config = gzip.decompress(Path('/proc/config.gz').read_bytes()).decode()
    if 'CONFIG_MODVERSIONS=y' in config:
        raise SystemExit('MODVERSIONS requires the original CRC symbol table; refusing to reconstruct one')
    (source/'.config').write_text(config)
    make = ['make', '-C', str(source), 'LLVM=-21', 'LOCALVERSION=-00104-g87ac0f2347eb']
    subprocess.run(make + ['olddefconfig', 'prepare', 'modules_prepare'], check=True)
    def entries(text):
        return {s.split('=', 1)[0]: s for s in text.splitlines() if s.startswith('CONFIG_')}
    before, after = entries(config), entries((source/'.config').read_text())
    changes = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    allowed = {'CONFIG_PAHOLE_VERSION', 'CONFIG_PAHOLE_HAS_BTF_TAG', 'CONFIG_PAHOLE_HAS_LANG_EXCLUDE'}
    if set(changes) - allowed or 'CONFIG_DEBUG_INFO_BTF=y' in config:
        raise SystemExit('Unreviewed configuration differences: ' + ', '.join(changes))
    if run(make + ['-s', '--no-print-directory', 'kernelrelease']) != platform.release():
        raise SystemExit('Prepared kernel release differs from the running kernel')
    # No CRCs exist with MODVERSIONS=n. Reconstruct exported names/owners only;
    # imports must also remain a subset of the existing matching working module.
    exports = {}
    for line in Path('/proc/kallsyms').read_text().splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[2].startswith('__ksymtab_'):
            exports[parts[2][10:]] = parts[3].strip('[]') if len(parts) > 3 else 'vmlinux'
    if not exports:
        raise SystemExit('Running kernel exports unavailable')
    (source/'Module.symvers').write_text(''.join('0x00000000\t%s\t%s\tEXPORT_SYMBOL_GPL\t\n' % (name, owner) for name, owner in sorted(exports.items())))
    stage = build/'patch/drivers/hid'
    stage.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(driver, stage/driver.name)
    for name in ('0001-fix-auth-and-resume.patch', '0002-fix-hotplug-input-restore.patch'):
        patch = (LOCAL/name).read_bytes().replace(b'\r\n', b'\n')
        subprocess.run(['git', 'apply', '--check', '-'], cwd=build/'patch', input=patch, check=True)
        subprocess.run(['git', 'apply', '-'], cwd=build/'patch', input=patch, check=True)
    module = build/'module'
    module.mkdir(exist_ok=True)
    shutil.copyfile(stage/driver.name, module/driver.name)
    (module/'Makefile').write_text('obj-m += hid-nanosic-wn8030.o\n')
    installed = Path(run(['modinfo', '-n', 'hid_nanosic_wn8030']))
    old = build/'previous-module.ko'
    if installed.suffix == '.zst':
        try:
            from compression import zstd
            previous = zstd.decompress(installed.read_bytes())
        except ImportError:
            previous = run_bytes(['zstd', '-dc', str(installed)])
    else:
        previous = installed.read_bytes()
    old.write_bytes(previous)
    subprocess.run(make + ['-j'+str(max(1,args.jobs)), 'M='+str(module), 'modules'], check=True)
    result = module/'hid-nanosic-wn8030.ko'
    def imports(file): return {s.split()[-1] for s in run(['nm', '-u', str(file)]).splitlines()}
    missing = imports(result) - imports(old)
    if missing or imports(result) - exports.keys():
        raise SystemExit('Unreviewed imports: ' + ', '.join(sorted(missing | (imports(result) - exports.keys()))))
    if run(['modinfo', '-F', 'vermagic', str(result)]).split()[0] != platform.release():
        raise SystemExit('Built module vermagic mismatch')
    report = {'kernel': platform.release(), 'compiler': pin['compiler'], 'moduleSha256': sha(result),
              'version': run(['modinfo','-F','version',str(result)]), 'verifiedImports':len(imports(result)),
              'configDifferences':changes, 'kernelCommit':pin['kernel_commit'], 'loaded':False}
    (build/'build-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


def run_bytes(args):
    return subprocess.check_output(args)


if __name__ == '__main__':
    main()
