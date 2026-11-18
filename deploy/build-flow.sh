#!/usr/bin/env bash
# Flow only needs Bash, Git, Docker and tar; no Compose/network-management APIs.
set -euo pipefail
: "${COMMIT_SHA:?Set COMMIT_SHA to the full checked-out source commit}"
[[ "$COMMIT_SHA" =~ ^[a-f0-9]{40}$ ]] || { echo 'A full commit SHA is required'; exit 2; }
test "$(git rev-parse HEAD)" = "$COMMIT_SHA" || { echo 'COMMIT_SHA does not match HEAD'; exit 2; }
test -z "$(git rev-parse --show-prefix)" || { echo 'Run from the repository root'; exit 2; }
git diff --quiet HEAD -- backend frontend deploy || { echo 'Tracked build inputs have changed; use a clean checkout'; exit 2; }
if [[ -e artifacts || -L artifacts ]]; then
    echo 'Use a fresh build workspace without an existing artifacts path'
    exit 2
fi
docker info >/dev/null
command -v tar >/dev/null
export_dir=''
cleanup() {
    result=$?
    trap - EXIT
    case "$export_dir" in "$PWD"/.flow-export.*) rm -rf -- "$export_dir";; esac
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

python_image="${PYTHON_BUILD_IMAGE:-python:3.12-slim-bookworm}"
node_image="${NODE_BUILD_IMAGE:-node:22-bookworm-slim}"
postgres_image="${POSTGRES_TEST_IMAGE:-postgres:16-bookworm}"
package_index="${PYTHON_PACKAGE_INDEX:-https://pypi.org/simple}"
case "$postgres_image" in *alpine*) echo 'Flow checks need postgres:16-bookworm; update POSTGRES_TEST_IMAGE'; exit 2;; esac
artifact_image="vueblog-flow-artifacts:${COMMIT_SHA}"
git archive "$COMMIT_SHA" | docker build --tag "$artifact_image" --file deploy/Dockerfile.flow-build \
    --build-arg "PYTHON_BUILD_IMAGE=$python_image" --build-arg "NODE_BUILD_IMAGE=$node_image" \
    --build-arg "POSTGRES_TEST_IMAGE=$postgres_image" --build-arg "PYTHON_PACKAGE_INDEX=$package_index" \
    --build-arg "COMMIT_SHA=$COMMIT_SHA" -
export_dir=$(mktemp -d "$PWD/.flow-export.XXXXXXXX")
docker run --rm "$artifact_image" | tar -xzf - -C "$export_dir"
for filename in manifest.json "blog-$COMMIT_SHA.tar.gz" "blog-$COMMIT_SHA.tar.gz.sha256" release-native.sh stage_native_artifact.py; do
    [[ -f "$export_dir/$filename" && ! -L "$export_dir/$filename" ]] || { echo 'Incomplete artifact export'; exit 1; }
done
mv "$export_dir" artifacts
export_dir=''
printf 'Native artifact ready for commit %s in artifacts/\n' "$COMMIT_SHA"
