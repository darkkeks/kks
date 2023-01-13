#!/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR"

IMAGE=${IMAGE:-caos-submissions-bot}

# currently used only for image tag
KKS_VERSION=$(cd ../.. && python3 -c "from kks import __version__; print(__version__.replace('+', '-'))")

COMMIT_ID=snapshot  # Use real commit id only if files are clean
git diff --exit-code >/dev/null && \
    git diff --staged --exit-code >/dev/null && \
    COMMIT_ID=$(git rev-parse --short HEAD)

docker build -f ./Dockerfile -t $IMAGE:$KKS_VERSION.$COMMIT_ID -t $IMAGE:latest ../..
