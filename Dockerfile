# GlobalShop 生产镜像（ModelScope 创空间 / Docker Compose 通用）
FROM python:3.12-slim

# 魔搭创空间要求容器监听 7860；本地 compose 通过 environment 覆盖为 5000
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai \
    PORT=7860

WORKDIR /app

# 魔搭创空间的构建机在国内，默认走清华源；海外平台可用 build-arg 覆盖
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .
RUN chmod +x /app/start.sh && sed -i 's/\r$//' /app/start.sh

# 魔搭 Docker 创空间默认端口 7860；本地 compose 通过 PORT 覆盖
EXPOSE 7860

CMD ["/app/start.sh"]
