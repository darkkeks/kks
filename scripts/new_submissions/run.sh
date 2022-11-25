#!/bin/bash
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 ENVFILE"
    exit 1
fi

ENVFILE=$1

docker stop caos-submissions-bot &>/dev/null
docker rm caos-submissions-bot &>/dev/null
docker run -d --restart always --name caos-submissions-bot -v caos-submissions-data:/data --env-file $ENVFILE caos-submissions-bot