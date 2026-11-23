"""Verify a downloaded Flow artifact without deploying or reading production settings."""
import argparse
import json
import os
import subprocess
import tarfile

from artifact import ArtifactError
from flow_host import context
from receive import receive


def run(environment, *, inspect=False):
    values=context(environment)
    if inspect: return values
    return {**values,**receive(values['archive'],values['commit'],verify_only=True)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect',action='store_true')
    args=parser.parse_args()
    try: print(json.dumps(run(os.environ,inspect=args.inspect),sort_keys=True))
    except (ArtifactError,OSError,ValueError,tarfile.TarError,subprocess.SubprocessError):
        raise SystemExit('Flow artifact verification stopped; no application was deployed.') from None
