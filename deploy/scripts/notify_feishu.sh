#!/usr/bin/env bash
set -euo pipefail
exec "${PYTHON_BIN:-python3}" "$(dirname "${BASH_SOURCE[0]}")/notify_feishu.py" "$@"
