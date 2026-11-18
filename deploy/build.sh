#!/usr/bin/env bash
set -euo pipefail
: "${IMAGE_PREFIX:?设置 ACR 仓库前缀，例如 registry.cn-shanghai.aliyuncs.com/team/blog}"
: "${COMMIT_SHA:?由云效代码源变量映射提交 SHA}"
[[ "$COMMIT_SHA" =~ ^[a-f0-9]{7,40}$ ]] || exit 2
bash deploy/test-postgres.sh
docker build -t "$IMAGE_PREFIX-api:$COMMIT_SHA" backend
docker build -t "$IMAGE_PREFIX-web:$COMMIT_SHA" frontend
docker push "$IMAGE_PREFIX-api:$COMMIT_SHA"
docker push "$IMAGE_PREFIX-web:$COMMIT_SHA"
