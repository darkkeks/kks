FROM python:3.11-alpine

ENV KKS_CUSTOM_DIR=/data/.kks

WORKDIR /tmp
COPY ./scripts/new_submissions/src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && rm requirements.txt

COPY ./setup.py ./MANIFEST.in ./README.md ./kks /tmp/kks/
COPY ./kks /tmp/kks/kks
RUN pip install --no-cache-dir /tmp/kks && rm -r /tmp/kks

WORKDIR /

COPY ./scripts/new_submissions/src ./src

STOPSIGNAL SIGINT

VOLUME "/data"

ENTRYPOINT ["./src/telegram_bot.py"]
