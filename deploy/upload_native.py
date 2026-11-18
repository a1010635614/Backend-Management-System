"""Upload only reviewed source files and built static assets; excludes local secrets."""
from pathlib import Path
import subprocess
import tarfile
from remote import ROOT,ssh_arguments

archive=ROOT/".local"/"native-release.tar.gz"
archive.parent.mkdir(exist_ok=True)
with tarfile.open(archive,"w:gz") as bundle:
    for relative in ("backend/app","backend/migrations","backend/tests","backend/alembic.ini","backend/requirements.txt","frontend/dist"):
        path=ROOT/relative
        if path.is_dir():
            for item in path.rglob("*"):
                if item.is_file() and "__pycache__" not in item.parts:
                    bundle.add(item,arcname=item.relative_to(ROOT).as_posix())
        else: bundle.add(path,arcname=relative)
with archive.open("rb") as data:
    subprocess.run(ssh_arguments()+["umask 077; cat > /opt/vueblog/release.tar.gz"],stdin=data,check=True)
print("Uploaded source and static assets.")
