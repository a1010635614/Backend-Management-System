#!/usr/bin/env bash
# Compatibility entrypoint for the existing Flow command.
set -euo pipefail
exec bash "$(dirname "${BASH_SOURCE[0]}")/cicd/build.sh" "$@"
