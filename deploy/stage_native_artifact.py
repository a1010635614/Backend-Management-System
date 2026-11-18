"""Validate a trusted Flow artifact directory, stage it, and invoke its native release script."""
import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


@dataclass(frozen=True)
class Artifact:
    commit:str
    archive:Path
    checksum:Path
    release_script:Path


def regular_file(directory,name):
    path=directory/name
    if path.parent!=directory or path.is_symlink() or not path.is_file():
        raise ValueError('Artifact file is missing or is not a regular file')
    return path


def verify(directory,expected_commit=None):
    directory=Path(directory).resolve(strict=True)
    manifest=regular_file(directory,'manifest.json')
    if manifest.stat().st_size>4096: raise ValueError('Manifest is too large')
    data=json.loads(manifest.read_text(encoding='utf-8'))
    if not isinstance(data,dict): raise ValueError('Manifest must be an object')
    commit=data.get('commit');digest=data.get('sha256')
    if not isinstance(commit,str) or not re.fullmatch(r'[a-f0-9]{40}',commit): raise ValueError('Manifest commit must be a full SHA')
    if expected_commit is not None and commit!=expected_commit: raise ValueError('Artifact commit differs from this pipeline run')
    filename='blog-'+commit+'.tar.gz'
    if data.get('archive')!=filename: raise ValueError('Unexpected artifact filename')
    if not isinstance(digest,str) or not re.fullmatch(r'[a-f0-9]{64}',digest): raise ValueError('Manifest digest must be SHA-256')
    archive=regular_file(directory,filename)
    checksum=regular_file(directory,filename+'.sha256')
    script=regular_file(directory,'release-native.sh')
    if checksum.stat().st_size>4096 or checksum.read_text(encoding='utf-8')!=digest+'  '+filename+'\n':
        raise ValueError('Checksum file does not match the manifest')
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=digest: raise ValueError('Artifact SHA-256 mismatch')
    return Artifact(commit,archive,checksum,script)


def stage(artifact,incoming=Path('/opt/vueblog/incoming')):
    incoming=Path(incoming).resolve()
    incoming.mkdir(parents=True,exist_ok=True,mode=0o700)
    for source in (artifact.archive,artifact.checksum):
        destination=incoming/source.name
        if destination.parent.resolve()!=incoming: raise ValueError('Invalid staging destination')
        fd,name=tempfile.mkstemp(prefix='.flow-stage-',dir=incoming)
        temporary=Path(name)
        try:
            with os.fdopen(fd,'wb') as stream,source.open('rb') as reader:
                shutil.copyfileobj(reader,stream)
            temporary.chmod(0o600)
            os.replace(temporary,destination)
        finally:
            temporary.unlink(missing_ok=True)


def deploy(directory,incoming=Path('/opt/vueblog/incoming'),expected_commit=None):
    artifact=verify(directory,expected_commit)
    stage(artifact,incoming)
    subprocess.run(['bash',str(artifact.release_script)],env={**os.environ,'COMMIT_SHA':artifact.commit},check=True)
    return artifact.commit


def main():
    parser=argparse.ArgumentParser(description='Deploy the verified artifacts directory from this trusted Flow build.')
    parser.add_argument('artifact_directory')
    parser.add_argument('--verify-only',action='store_true',help='Validate metadata/checksum without copying or deploying.')
    args=parser.parse_args()
    expected=os.environ.get('COMMIT_SHA') or None
    if args.verify_only:
        print('Artifact verified:',verify(args.artifact_directory,expected).commit)
    else:
        print('Native release finished:',deploy(args.artifact_directory,expected_commit=expected))


if __name__=='__main__':
    try: main()
    except (OSError,ValueError,subprocess.CalledProcessError) as error:
        raise SystemExit('Native artifact deployment stopped: '+str(error)) from None
