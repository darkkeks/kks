FROM python:3.11-alpine

ARG KKS_REVISION
ENV KKS_CUSTOM_DIR=/data/.kks

WORKDIR /tmp
COPY src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && rm requirements.txt

RUN pip install --no-cache-dir https://github.com/darkkeks/kks/archive/$KKS_REVISION.tar.gz

WORKDIR /

COPY src src

STOPSIGNAL SIGINT

CMD ["./src/telegram_bot.py"]
