"""Bind a Flow host deployment to its full source SHA and versioned v2 receiver."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


def context(environment):
    first = environment.get('CI_COMMIT_SHA_1', '')
    single = environment.get('CI_COMMIT_SHA', '')
    if first and single and first != single:
        raise ValueError('Code source SHA variables disagree')
    commit = first or single
    if not re.fullmatch('[a-f0-9]{40}', commit):
        raise ValueError('Flow must supply the full source SHA; use unencoded host variables')
    pipeline, number = environment.get('PIPELINE_ID', ''), environment.get('BUILD_NUMBER', '')
    if not re.fullmatch('[A-Za-z0-9_-]{1,64}', pipeline) or not re.fullmatch('[1-9][0-9]{0,12}', number):
        raise ValueError('Flow pipeline/run identifiers are missing or invalid')
    return {'commit': commit, 'pipeline': pipeline, 'build_number': number,
            'archive': str(PurePosixPath('/opt/vueblog/flow') / pipeline / number / 'blog-native.tgz')}


def run(environment, *, inspect=False):
    values = context(environment)
    if inspect: return values
    # Resolve the current release once. The old /usr/local/sbin native receiver
    # is deliberately not used; receive.py enforces the completed traffic gate.
    receiver = Path(__file__).resolve().with_name('receive.py')
    subprocess.run([sys.executable, str(receiver), values['archive'], '--commit', values['commit']],
                   check=True, timeout=3600)
    return {**values, 'result': 'deployed'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect', action='store_true', help='Print public run/source metadata without unpacking or deploying')
    args = parser.parse_args()
    try: print(json.dumps(run(os.environ, inspect=args.inspect), sort_keys=True))
    except (OSError, ValueError, subprocess.SubprocessError):
        raise SystemExit('Flow host deployment stopped. Check full source SHA, unencoded variables, download path and completed first cutover') from None
