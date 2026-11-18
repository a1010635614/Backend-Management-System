"""Package reviewed application inputs and matching deploy scripts for native releases."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tarfile

INPUTS=('backend/app','backend/migrations','backend/tests','backend/alembic.ini','backend/requirements.txt','frontend/dist')
SCRIPTS=('release-native.sh','stage_native_artifact.py')


def create_package(root,commit):
    root=Path(root).resolve()
    if not isinstance(commit,str) or not re.fullmatch(r'[a-f0-9]{40}',commit): raise ValueError('A full commit SHA is required')
    files=[]
    for name in INPUTS:
        path=root/name
        if path.is_symlink() or not path.exists(): raise ValueError('Missing or linked application input: '+name)
        for item in (path.rglob('*') if path.is_dir() else (path,)):
            relative=item.relative_to(root)
            if '__pycache__' in relative.parts: continue
            if item.is_symlink(): raise ValueError('Linked artifact input is not allowed')
            if item.is_file():
                if item.name=='.env' or item.name.startswith('.env.') or item.suffix.lower() in ('.pem','.key'):
                    raise ValueError('Credential-like file found in artifact inputs')
                files.append((item,relative.as_posix()))
    for name in SCRIPTS:
        path=root/'deploy'/name
        if path.is_symlink() or not path.is_file(): raise ValueError('Matching deployment script is missing')
    output=root/'artifacts';output.mkdir(exist_ok=True)
    archive=output/('blog-'+commit+'.tar.gz')
    with tarfile.open(archive,'w:gz') as tar:
        for path,name in sorted(files,key=lambda row:row[1]): tar.add(path,arcname=name)
    with archive.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
    archive.with_suffix('.gz.sha256').write_text(digest+'  '+archive.name+'\n',encoding='utf-8')
    (output/'manifest.json').write_text(json.dumps({'commit':commit,'archive':archive.name,'sha256':digest}),encoding='utf-8')
    for name in SCRIPTS: shutil.copyfile(root/'deploy'/name,output/name)
    return output


if __name__=='__main__':
    create_package(Path.cwd(),os.environ['COMMIT_SHA'])
