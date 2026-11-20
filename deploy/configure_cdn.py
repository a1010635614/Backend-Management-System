"""Verify CDN and optionally enable downloads. Keys stay in a masked dialog/SSH stdin."""
import argparse
import json
import shlex
import subprocess
import sys
from remote import ROOT, ssh_arguments


def ask_key(apply):
    import tkinter as tk
    from tkinter import simpledialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    action = 'Verify and enable CDN downloads' if apply else 'Verify CDN only (no configuration changes)'
    message = ('https://cdn.kongqi.xyz\nType D / decimal / sign / t / 300 seconds\n'
               + action + '\nTests download one published image and PDF; CDN usage may be billed.\n'
               'Enter the CDN authentication key (not the COS SecretKey):')
    try:
        return simpledialog.askstring('Blog CDN configuration', message, show='*', parent=root)
    finally:
        root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Enable CDN only after all live preflight checks pass.')
    args = parser.parse_args()
    subprocess.run([sys.executable, str(ROOT / 'deploy/setup_ssh.py'), '--check'], check=True)
    key = ask_key(args.apply)
    if key is None:
        raise SystemExit('Cancelled; no CDN configuration was sent.')
    # Import only the pure signing module, not app.main or local environment settings.
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.cdn import validate_cdn_settings
    validate_cdn_settings('https://cdn.kongqi.xyz', key)
    helper = (ROOT / 'deploy/configure_mail_remote.py').read_text(encoding='utf-8')
    program = (ROOT / 'deploy/configure_cdn_remote.py').read_text(encoding='utf-8')
    bootstrap = ("_helpers={'__name__':'cdn_config_helpers'}\nexec(" + repr(helper) + ",_helpers)\n"
                 "serialize_environment=_helpers['serialize_environment']\n"
                 "replace_file=_helpers['replace_file']\n" + program)
    command = '/opt/vueblog/current/.venv/bin/python -c ' + shlex.quote(bootstrap)
    payload = json.dumps({'base_url': 'https://cdn.kongqi.xyz', 'secret': key, 'apply': args.apply}).encode()
    print('Checking CDN; credentials and signed download URLs are not logged.', flush=True)
    result = subprocess.run(ssh_arguments() + [command], input=payload,
                            capture_output=True, timeout=240)
    print(result.stdout.decode('utf-8', errors='replace'), end='', flush=True)
    if result.returncode:
        # Only our sanitised remote failures are shown; arbitrary traceback output stays private.
        for line in result.stderr.decode('utf-8', errors='replace').splitlines():
            if line.startswith(('CDN setup stopped:', 'CDN setup stopped (', 'Deploy the CDN-capable backend')):
                print(line, flush=True)
        raise SystemExit('CDN setup did not complete; inspect server status before retrying.')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit('SSH verification failed; the CDN key was not transmitted.') from None
    except subprocess.TimeoutExpired:
        raise SystemExit('CDN setup timed out; inspect the server before retrying. Do not start another setup yet.') from None
    except ValueError:
        raise SystemExit('The CDN key must contain 6–40 ASCII letters or digits.') from None
    except OSError:
        raise SystemExit('The CDN setup tool could not run.') from None
