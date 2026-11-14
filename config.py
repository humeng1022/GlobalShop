"""
配置文件
包含系统运行所需的各种配置参数

所有配置都来自环境变量（.env），方便本地与云端使用同一套代码：
- 本地：DATABASE_URL 指向 SQLite
- 云端：DATABASE_URL 指向 Neon/Postgres
"""

import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# OpenAI兼容API配置（聊天模型）
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "Qwen/Qwen3-8B")

# 向量模型（默认与聊天模型共用硅基流动 Key）
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", OPENAI_BASE_URL).rstrip("/")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "16"))

# 运行形态：server = 调用独立 LangGraph 服务；embedded = 图内嵌在 Flask 进程
APP_MODE = os.getenv("APP_MODE", "server").strip().lower()

# 数据库：sqlite:///./data/app.db 或 postgresql://...
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")

# 服务端口 / 管理后台
PORT = int(os.getenv("PORT", "5000"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in ("1", "true", "yes")

# HTTP请求配置
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "180"))
HTTP_MAX_RETRIES = int(os.getenv("HTTP_MAX_RETRIES", "3"))
HTTP_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "GlobalShopCustomerService/1.0.0"
}

# 系统配置
SYSTEM_NAME = "GlobalShop AI 客服中心"
VERSION = "1.0.0"

# 日志配置
LOG_CONFIG = {
    "level": os.getenv("LOG_LEVEL", "INFO"),
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
}
