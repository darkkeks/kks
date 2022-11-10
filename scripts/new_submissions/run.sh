if [ "$#" -ne 1 ]; then
    echo "Usage: $0 ENVFILE"
    exit 1
fi

ENVFILE=$1

docker run -d --restart always --name caos-submissions-bot -v caos-submissions-data:/data --env-file $ENVFILE caos-submissions-bot
