"""Install a reviewed AliDNS hook after a read-only credential preflight."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile

CODE = Path('/usr/local/lib/blog-acme/alidns_hook.py')
CONFIG = Path('/etc/letsencrypt/alidns-hook.json')
STATE = Path('/var/lib/blog-acme')
RELOAD = CODE.with_name('reload-nginx.sh')
RELOAD_SOURCE = b'#!/bin/sh\nset -eu\n/usr/sbin/nginx -t\n/usr/bin/systemctl reload nginx\n'


class InstallError(RuntimeError):
    pass


def plan():
    return {'hook':CODE.as_posix(),'credentials':CONFIG.as_posix(),'credentials_mode':'0600',
            'state':STATE.as_posix(),'state_mode':'0700','reload_hook':RELOAD.as_posix(),
            'credential_check':'read only; fixed AliDNS HTTPS API',
            'zone':'kongqi.xyz','dns_records_changed':False,'renewal_configuration_changed':False}


def directory(path, mode):
    if path.resolve()!=path or path.is_symlink(): raise InstallError('Installation directory must not be linked')
    path.mkdir(parents=True,exist_ok=True,mode=mode)
    info=path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
        raise InstallError('Installation directory must be root-owned and not writable by others')
    if mode==0o700 and info.st_mode&0o077:
        raise InstallError('Private state directory must have mode 0700')


def write_new_or_identical(path, content, mode):
    if path.is_symlink() or path.resolve()!=path: raise InstallError('Installation file must not be linked')
    if path.exists():
        info=path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o777!=mode or info.st_size>131072:
            raise InstallError('Existing installation file has unsafe ownership or permissions')
        if path.read_bytes()!=content: raise InstallError('Existing installation differs; inspect it before replacing')
        return
    fd, temporary=tempfile.mkstemp(prefix='.acme-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(content);stream.flush();os.fsync(stream.fileno())
        os.chmod(temporary,mode)
        # A hard link publishes only if the final name still does not exist.
        os.link(temporary,path)
        parent=os.open(path.parent,os.O_DIRECTORY)
        try: os.fsync(parent)
        finally: os.close(parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def install(hook_source, credentials):
    if not hasattr(os,'geteuid') or os.geteuid()!=0: raise InstallError('Root is required')
    if len(hook_source)>65536: raise InstallError('Hook source exceeded the installation limit')
    compile(hook_source,str(CODE),'exec')
    with tempfile.TemporaryDirectory(prefix='blog-acme-check-') as temporary:
        module_file=Path(temporary)/'alidns_hook.py';module_file.write_bytes(hook_source)
        spec=importlib.util.spec_from_file_location('reviewed_alidns_hook',module_file)
        hook=importlib.util.module_from_spec(spec);spec.loader.exec_module(hook)
        try:
            client=hook.client_from_credentials(credentials)
            client.challenge_records(); authorities=hook.nameservers()
        except hook.HookError as error:
            raise InstallError(str(error)) from None
    # No installation or credential file has been written before this preflight.
    for path,mode in ((CODE.parent,0o755),(CONFIG.parent,0o755),(STATE,0o700)):
        directory(path,mode)
    config=(json.dumps(credentials,sort_keys=True)+'\n').encode()
    # Preflight existing files together so an incompatible earlier config blocks all publication.
    files=((CONFIG,config,0o600),(CODE,hook_source,0o755),(RELOAD,RELOAD_SOURCE,0o755))
    for path,content,mode in files:
        if path.exists() or path.is_symlink():
            if path.is_symlink() or not path.is_file() or path.resolve()!=path or path.stat().st_uid!=0 or path.stat().st_mode&0o777!=mode:
                raise InstallError('Existing installation file is unsafe')
            if path.stat().st_size>131072 or path.read_bytes()!=content:
                raise InstallError('Existing installation differs; no credentials were replaced')
    for path,content,mode in files: write_new_or_identical(path,content,mode)
    return {**plan(),'installed':True,'hook_sha256':hashlib.sha256(hook_source).hexdigest(),
            'authoritative_nameservers':authorities,'read_permission':'passed'}
