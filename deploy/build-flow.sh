#!/usr/bin/env bash
# Flow's AliLinux task only needs Bash, Git, Docker and Compose on the host.
# Source is streamed from the exact commit; no host paths or credentials are mounted.
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
docker compose version

containers=()
cleanup() {
    result=$?
    trap - EXIT
    if ((${#containers[@]})); then
        docker rm --force "${containers[@]}" >/dev/null || echo "Could not remove this build's temporary containers" >&2
    fi
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

start_checked() {
    docker start --attach "$1"
    state=$(docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' "$1")
    if [[ "$state" != 'exited 0' ]]; then
        printf 'Build container did not finish successfully: %s\n' "$state" >&2
        return 1
    fi
}

python_image="${PYTHON_BUILD_IMAGE:-python:3.12-slim-bookworm}"
node_image="${NODE_BUILD_IMAGE:-node:22-bookworm-slim}"
postgres_image="${POSTGRES_TEST_IMAGE:-postgres:16-alpine}"
package_index="${PYTHON_PACKAGE_INDEX:-https://pypi.org/simple}"
tools_image="vueblog-flow-tools:${COMMIT_SHA}"
git archive "${COMMIT_SHA}:deploy" | docker build --tag "$tools_image" --build-arg "PYTHON_BUILD_IMAGE=$python_image" --file Dockerfile.flow-tools -
PYTHON_BUILD_IMAGE="$python_image" POSTGRES_TEST_IMAGE="$postgres_image" PYTHON_PACKAGE_INDEX="$package_index" bash deploy/test-postgres.sh

web=$(docker create --workdir /frontend "$node_image" sh -c 'npm ci && npm run build')
[[ "$web" =~ ^[a-f0-9]{64}$ ]] || { echo 'Docker did not return a container ID'; exit 1; }
containers+=("$web")
git archive "$COMMIT_SHA" frontend | docker cp - "$web:/"
start_checked "$web"

package=$(docker create --env "COMMIT_SHA=$COMMIT_SHA" "$tools_image")
[[ "$package" =~ ^[a-f0-9]{64}$ ]] || { echo 'Docker did not return a container ID'; exit 1; }
containers+=("$package")
git archive "$COMMIT_SHA" \
    backend/app backend/migrations backend/tests backend/alembic.ini backend/requirements.txt \
    deploy/release-native.sh deploy/stage_native_artifact.py | docker cp - "$package:/workspace/"
docker cp "$web:/frontend/dist/." - | docker cp - "$package:/workspace/frontend/dist/"
start_checked "$package"
mkdir artifacts
docker cp "$package:/workspace/artifacts/." artifacts/
printf 'Native artifact ready for commit %s in artifacts/\n' "$COMMIT_SHA"
