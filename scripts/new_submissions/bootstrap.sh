#!/bin/bash

# TODO remove this script, use config with creds

docker volume create caos-submissions-data 2>/dev/null
docker run -it --rm -v caos-submissions-data:/data caos-submissions-bot kks auth --judge
