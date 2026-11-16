#!/bin/sh
# 生产启动脚本：魔搭创空间 / Docker Compose / 任意容器
# 魔搭 Docker 创空间要求监听 7860；本地 compose 通过 PORT=5000 覆盖
set -e

exec gunicorn web_app:app \
  --bind "0.0.0.0:${PORT:-7860}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --threads 2 \
  --timeout 300 \
  --access-logfile - \
  --error-logfile -
