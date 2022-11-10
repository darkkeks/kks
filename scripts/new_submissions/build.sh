KKS_REVISION=${1:-judge}

docker build . -t caos-submissions-bot --build-arg KKS_REVISION=$KKS_REVISION
