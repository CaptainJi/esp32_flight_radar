#!/usr/bin/env bash
# 在家用服务器上加载镜像并启动 Voice ATC
set -euo pipefail
DIR="${1:-/opt/voice_atc}"
cd "$DIR"
if [[ ! -f voice-atc-18650.tar.gz ]]; then
  echo "缺少 voice-atc-18650.tar.gz" >&2
  exit 1
fi
if [[ ! -f .env ]]; then
  echo "缺少 .env（请先填 ARK_* / VOICE_API_KEY）" >&2
  exit 1
fi
COMPOSE=docker-compose.server.yml
if [[ ! -f "$COMPOSE" ]]; then
  COMPOSE=docker-compose.yml
fi
if [[ ! -f "$COMPOSE" ]]; then
  echo "缺少 docker-compose 文件" >&2
  exit 1
fi
echo "==> docker load"
gunzip -c voice-atc-18650.tar.gz | docker load
echo "==> compose up ($COMPOSE)"
docker compose -f "$COMPOSE" up -d
echo "==> health"
sleep 2
curl -sS "http://127.0.0.1:18650/health" || true
echo
echo "完成。对外: http://<公网或内网IP>:18650/"
echo "Tab5 Voice ATC URL 填该地址（勿用 127.0.0.1）"
