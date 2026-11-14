#!/bin/sh
# 生产启动脚本：Render / Railway / 任意容器都用它
# PORT 由平台注入（Render 默认 10000）；WORKERS 按内存调整
set -e

exec gunicorn web_app:app \
  --bind "0.0.0.0:${PORT:-5000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --threads 2 \
  --timeout 300 \
  --access-logfile - \
  --error-logfile -
