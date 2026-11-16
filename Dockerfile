# GlobalShop 生产镜像（ModelScope 创空间 / Docker Compose 通用）
FROM python:3.12-slim

# 魔搭创空间要求容器监听 7860；本地 compose 通过 environment 覆盖为 5000
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai \
    PORT=7860

WORKDIR /app

# 魔搭构建机在香港：官方 PyPI 更快；失败自动回退阿里云镜像。
# 本地 compose 通过 build-arg 指定清华源。
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

COPY requirements.txt ./
RUN pip install --no-cache-dir --retries 5 --timeout 60 -r requirements.txt gunicorn \
    || pip install --no-cache-dir --retries 5 --timeout 60 \
         -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt gunicorn

COPY . .
RUN chmod +x /app/start.sh && sed -i 's/\r$//' /app/start.sh

EXPOSE 7860

CMD ["/app/start.sh"]
