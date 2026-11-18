#!/usr/bin/python3
"""Receive a trusted Flow download and invoke its matching native release entry point."""
import argparse
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile


def run_archive(archive, *, verify_only=False, work_parent=None):
    archive = Path(archive).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='vueblog-flow-', dir=work_parent) as work:
        with tarfile.open(archive, 'r:*') as package:
            if any(not (member.isfile() or member.isdir()) for member in package.getmembers()):
                raise ValueError('The Flow download must contain only regular files and directories')
            package.extractall(work, filter='data')
        artifacts = Path(work) / 'artifacts'
        entry = artifacts / 'stage_native_artifact.py'
        if not artifacts.is_dir() or artifacts.is_symlink() or not entry.is_file() or entry.is_symlink():
            raise ValueError('Expected artifacts/stage_native_artifact.py; include the packaging path when uploading')
        command = [sys.executable, str(entry), str(artifacts)]
        if verify_only:
            command.append('--verify-only')
        subprocess.run(command, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', help='Archive downloaded by this trusted Flow deployment task')
    parser.add_argument('--verify-only', action='store_true', help='Unpack and validate without publishing')
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        raise SystemExit('Python 3.12+ is required')
    run_archive(args.archive, verify_only=args.verify_only, work_parent='/opt/vueblog')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, tarfile.TarError, subprocess.CalledProcessError) as error:
        raise SystemExit('Flow artifact processing stopped: ' + str(error)) from None
