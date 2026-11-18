#!/usr/bin/env bash
# 在服务器部署目录运行；.env 与 compose.production.yml 预先放在此目录。
set -euo pipefail
: "${IMAGE_PREFIX:?}"
: "${COMMIT_SHA:?}"
[[ "$COMMIT_SHA" =~ ^[a-f0-9]{7,40}$ ]] || exit 2
exec 9>.release.lock
flock -n 9 || { echo '已有部署正在运行'; exit 1; }
previous=''
if [[ -f .current-release ]]; then previous=$(cat .current-release); fi
export IMAGE_TAG="$COMMIT_SHA"
docker compose -f compose.production.yml pull
if docker compose -f compose.production.yml up -d --wait --wait-timeout 180 && curl --fail --silent http://127.0.0.1:8080/api/health >/dev/null; then
  printf '%s' "$COMMIT_SHA" > .current-release
else
  if [[ "$previous" =~ ^[a-f0-9]{7,40}$ ]]; then
    export IMAGE_TAG="$previous"
    docker compose -f compose.production.yml up -d --wait --wait-timeout 180
  fi
  exit 1
fi
