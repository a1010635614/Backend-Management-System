"""Generate new independent local configuration without overwriting any file."""
import argparse
import os
from pathlib import Path
import secrets


def initialize(root):
    root = Path(root).resolve()
    names = ('.env', 'backend/.env', 'frontend-web/.env', 'frontend-admin/.env')
    for name in names:
        path = root / name
        if path.exists() or path.is_symlink():
            raise ValueError('Existing configuration was preserved: ' + name)
    database, cache, jwt = (secrets.token_hex(32) for _ in range(3))
    common = (root / '.env.example').read_text(encoding='utf-8')
    common = common.replace('ReplaceThisDatabasePassword1234567890', database)
    common = common.replace('ReplaceThisRedisPassword1234567890123', cache)
    common = common.replace('development-only-change-this-secret-key', jwt)
    values = {'.env': common, 'backend/.env': common.replace('@postgres:5432/', '@127.0.0.1:15432/')
              .replace('@redis:6379/', '@127.0.0.1:16379/')}
    for name in names[2:]:
        values[name] = (root / (name + '.example')).read_text(encoding='utf-8')
    created = []
    try:
        for name, value in values.items():
            path = root / name
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                stream.write(value)
    except OSError:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return names


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()
    try:
        for name in initialize(args.root):
            print('Created local configuration: ' + name)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
