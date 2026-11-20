#!/usr/bin/env bash
# No Compose/network-management APIs are used on the Flow build daemon.
set -euo pipefail
: "${COMMIT_SHA:?Set COMMIT_SHA to the full checked-out source commit}"
[[ "$COMMIT_SHA" =~ ^[a-f0-9]{40}$ ]] || { echo 'A full commit SHA is required'; exit 2; }
test "$(git rev-parse HEAD)" = "$COMMIT_SHA" || { echo 'COMMIT_SHA does not match HEAD'; exit 2; }
test -z "$(git rev-parse --show-prefix)" || { echo 'Run from the repository root'; exit 2; }
git diff --quiet HEAD -- backend frontend-web frontend-admin deploy .env.example docker-compose.yml .dockerignore || {
  echo 'Tracked build inputs have changed; use a clean checkout'; exit 2;
}
if [[ -e artifacts || -L artifacts ]]; then echo 'Use a fresh build workspace without artifacts/'; exit 2; fi
docker info >/dev/null
command -v tar >/dev/null
export_dir=''
cleanup() {
  result=$?; trap - EXIT
  case "$export_dir" in "$PWD"/.flow-export.*) rm -rf -- "$export_dir";; esac
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
artifact_image="blog-compose-artifacts:$COMMIT_SHA"
git archive "$COMMIT_SHA" | docker build --tag "$artifact_image" --file deploy/docker/ci.Dockerfile \
  --build-arg "PYTHON_BUILD_IMAGE=${PYTHON_BUILD_IMAGE:-public.ecr.aws/docker/library/python:3.12-slim-bookworm}" \
  --build-arg "NODE_BUILD_IMAGE=${NODE_BUILD_IMAGE:-public.ecr.aws/docker/library/node:22-bookworm-slim}" \
  --build-arg "POSTGRES_TEST_IMAGE=${POSTGRES_TEST_IMAGE:-public.ecr.aws/docker/library/postgres:16.15-bookworm}" \
  --build-arg "PYTHON_PACKAGE_INDEX=${PYTHON_PACKAGE_INDEX:-https://pypi.org/simple}" \
  --build-arg "COMMIT_SHA=$COMMIT_SHA" -
export_dir=$(mktemp -d "$PWD/.flow-export.XXXXXXXX")
# Keep to Flow's verified build/run API subset; this image only emits the tar.
docker run --rm "$artifact_image" | tar -xzf - -C "$export_dir"
for filename in manifest.json "blog-$COMMIT_SHA.tar.gz" "blog-$COMMIT_SHA.tar.gz.sha256"; do
  [[ -f "$export_dir/$filename" && ! -L "$export_dir/$filename" ]] || { echo 'Incomplete artifact export'; exit 1; }
done
mv "$export_dir" artifacts
export_dir=''
printf 'Compose artifact ready for commit %s in artifacts/\n' "$COMMIT_SHA"
