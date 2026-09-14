# Voice ATC 旁路中继 — 局域网 HTTP 服务
FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VOICE_ATC_HOST=0.0.0.0 \
    VOICE_ATC_PORT=18650

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py volc_client.py prompt.py radio_fx.py ./
COPY static ./static

RUN mkdir -p /app/data/audio

EXPOSE 18650

# 音频落盘目录可挂载；密钥用 -e / --env-file 注入，勿打进镜像
VOLUME ["/app/data"]

CMD ["python", "main.py"]
