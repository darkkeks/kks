#!/bin/bash

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 CONFIG_FILE"
    exit 1
fi

CONFIG=$(realpath "$1")

IMAGE=${IMAGE:-caos-submissions-bot}

docker stop caos-submissions-bot &>/dev/null
docker rm caos-submissions-bot &>/dev/null

docker run -d --restart always --name caos-submissions-bot -v caos-submissions-data:/data -v $CONFIG:/data/config:ro $IMAGE /data/config
