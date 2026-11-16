---
title: GlobalShop AI 客服中心
sdk: docker
app_port: 7860
license: Apache License 2.0

# ModelScope 创空间元数据（可选）
domain:
  - nlp
tags:
  - customer-service
  - rag
  - e-commerce
datasets:
models:
---

# GlobalShop AI 客服中心

> 面向跨境电商场景的多智能体智能客服 · 基于开源项目二次开发

一个可以直接本地运行的跨境电商客服 Demo：用户可以用中文或英文咨询商品、物流、退换货、关税和售后问题，系统会自动识别意图和语言，路由到对应的专家智能体，并用同一语言回复。

---

## 项目来源与致谢

本项目基于开源项目 **「多智能体客服系统」（customer-service-ai-agent）** 二次开发，保留其 Apache-2.0 许可证（见 [LICENSE](LICENSE)）与 LangGraph 多智能体架构，在此之上做了跨境电商方向的业务改造。

与原项目相比的主要变化：

| 维度 | 原项目 | 本项目 |
|---|---|---|
| 业务语境 | 国内电商（人民币、发票、门店） | 跨境电商（USD、国际物流、关税、VAT） |
| 智能体 | 产品/技术/账单/投诉/综合 | 新增 **物流追踪**，其余五个按跨境场景重写 |
| 知识来源 | 每个智能体硬编码字典 | 统一 `knowledge/` 知识库 + bge-m3 向量检索 |
| 语言 | 仅中文 | **中英自动识别**，按用户语言回复 |
| 前端 | 通用客服 UI | GlobalShop 品牌与跨境场景快捷问题 |

---

## ✨ 核心功能

### 1. 跨境电商客服人设
所有智能体共享同一段人设（[persona.py](persona.py)）：专业、热情、懂国际物流与海关政策，不臆造轨迹/价格/法律建议，遇到不确定会给出下一步动作。

### 2. 🚚 物流追踪（本项目新增）
- 识别 `物流 / 快递 / 单号 / 包裹 / tracking / parcel / customs` 等中英关键词
- 从自然语言里提取运单号（支持 `YT123456789CN` 这类 UPU S10、专线号、纯数字单号）
- **规则命中后不调用大模型**，直接返回稳定话术：*"您的包裹已到达目的国海关，正在清关中"*，并附清关说明与时效
- 实现见 [tools/logistics.py](tools/logistics.py)，替换 `track_package()` 即可接入真实承运商 API

### 3. 🌐 多语言支持（本项目新增）
- [i18n.py](i18n.py) 判断提问语言：含中文 → 中文回复；纯英文/其他 → 英文回复
- 语言规则会被写进每次系统提示；即使同一会话中用户切换语言，下一轮也会跟着切换
- 兜底文案、护栏话术同样双语

### 4. 📚 知识库（向量检索）

知识源在 [knowledge/](knowledge/) 目录：

| 文件 | 内容 | 切分方式 |
|---|---|---|
| `products.csv` | 商品 SKU（标题/价格/库存/变体/保修地区/描述） | 一行一个 SKU |
| `policies.md` | 退换货、物流时效、关税、支付、保修、追踪、联系方式、投诉 | 每个 `##` 章节 |
| `faq.json` | 中英双语问答对 | 一问一答 |

处理链路：切分 → `BAAI/bge-m3` 向量化（1024 维）→ 存入数据库（SQLite / Postgres）→ 按余弦相似度召回 Top3 注入系统提示；向量索引不可用时自动回退关键词检索。

```powershell
# 修改 knowledge/ 后重建索引（本地）
.\.venv\Scripts\python.exe scripts\ingest_kb.py --force
# 或在后台「概览 → 重建索引」点一下
```

后台新增的知识条目也存在数据库里（`source=admin`），重建索引不会覆盖。

### 5. 🔀 多智能体路由
```
classify_query ──┬─ 物流关键词 ───────────────► logistics_agent
                 ├─ product_info ─────────────► product_agent
                 ├─ technical_support ────────► tech_agent
                 ├─ billing ──────────────────► billing_agent
                 ├─ complaint ────────────────► complaint_agent
                 ├─ general_inquiry ──────────► general_agent
                 └─ out_of_scope ─────────────► 固定护栏话术（双语）
                                            ↓
                                     final_response
```

---

## 🗂 目录结构

```
customer-service-ai-agent/
├── web_app.py                     # Flask 入口：页面 + /api/chat + 后台注册
├── start.sh                       # 生产启动脚本（gunicorn，读取 PORT / WEB_CONCURRENCY）
├── chat_service_embedded.py       # ⭐ 单进程模式：图内嵌执行、会话读写
├── chat_web_service.py            # 双服务模式：HTTP 调 LangGraph（需许可证）
├── graph_runtime.py               # ⭐ 图实例 + 持久化 checkpointer + 并发锁
├── multi_agent_customer_service.py# LangGraph 图：分类、路由、智能体节点
├── persona.py                     # ⭐ 跨境电商人设（系统提示）
├── i18n.py                        # ⭐ 语言识别 + 回复语言指令
├── knowledge/                     # ⭐ 知识源（csv / md / json）
│   ├── products.csv
│   ├── policies.md
│   └── faq.json
├── knowledge_loader.py            # 切分知识源为 chunk
├── knowledge_base.py              # 关键词兜底检索
├── vector_store.py                # ⭐ 向量化、入库、余弦检索
├── embedding_client.py            # bge-m3 调用
├── db.py                          # SQLite / Postgres 双引擎 + 所有表
├── admin/                         # ⭐ 后台蓝图（登录/会话/知识库/运单）
├── scripts/
│   ├── ingest_kb.py               # 知识库入库 / 重建索引
│   └── clear_sessions.py          # 清空会话（演示用）
├── multi_agents/                  # 6 个智能体
├── tools/                         # 意图分类 + 物流模拟
├── templates/                     # index.html / admin.html / admin_login.html
├── Dockerfile                     # ⭐ 生产镜像（创空间/Compose 通用，根目录）
├── start.sh                       # 生产启动脚本（PORT / WEB_CONCURRENCY）
├── docker-compose.yml             # 本地：db + web
├── requirements.txt
└── .env.example                   # 环境变量模板（复制为 .env）
```

---

## 🚀 快速开始

### 1. 环境要求
- Python 3.11+（本项目在 3.12.4 验证）
- 一个 OpenAI 兼容的 API Key（默认使用[硅基流动](https://cloud.siliconflow.cn/account/ak)）

### 2. 安装依赖

```bash
cd customer-service-ai-agent
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
pip install -U "langgraph-cli[inmem]"
pip install colorama              # Windows 下 langgraph dev 彩日志必需
```

### 3. 配置 `.env`

复制 `.env.example` 为 `.env`，最少只需要改一项：

```env
OPENAI_API_KEY=sk-your-key-here
OPENAI_BASE_URL=https://api.siliconflow.cn/v1
OPENAI_MODEL=Qwen/Qwen3-8B
HTTP_TIMEOUT=180
LANGGRAPH_API_URL=http://127.0.0.1:2024
LANGGRAPH_GRAPH_NAME=customer_service
FLASK_SECRET_KEY=随便一串随机字符
```

> `HTTP_TIMEOUT` 建议 ≥120 秒：Qwen3 等思考型模型在长提示下容易超过 30 秒。

### 4. 启动

**方式 A：单进程（推荐，无需 Docker）**

`APP_MODE=embedded` 时，图直接跑在 Flask 进程里，会话历史写入 SQLite（`data/app.db`），重启不丢：

```powershell
.\.venv\Scripts\python.exe web_app.py
# http://localhost:5000
```

**方式 B：Docker（Postgres 持久化，更接近线上）**

见下一节。

> 如果你的 key 额度有限，注意每条消息会触发 2 次模型调用（分类 + 回答）。

### 5. 自检

```powershell
# 页面 / 健康检查
curl http://127.0.0.1:5000/api/health
# 数据库 + 图自检
curl http://127.0.0.1:5000/api/test
# 后台（密码为 .env 的 ADMIN_PASSWORD）
# http://localhost:5000/admin
```

---

## 🐳 本地 Docker 运行（Postgres + Web）

默认两容器：`db`（Postgres 16）+ `web`（Flask + gunicorn，`APP_MODE=embedded`）。
会话 checkpoint、知识库原文与向量都存在 Postgres，`docker compose down` 不会丢数据（`down -v` 才会）。

```powershell
# 1. 启动（首次会构建 web 镜像）
docker compose up -d --build

# 2. 首次把知识库写入 Postgres（之后改 knowledge/ 再跑一次）
docker compose run --rm web python scripts/ingest_kb.py --force

# 3. 打开页面
# http://localhost:5000
```

> 启动前先停掉本机直接运行的 `python web_app.py`，否则 5000 端口冲突。

**关于「双服务」**：LangGraph 官方 Agent Server 接 Postgres 属于授权模式，需要 LangGraph Cloud 许可证，免费版只提供内存态 `langgraph dev`。因此本项目默认用 embedded + 开源 checkpointer；仓库里保留了 `agent-server` profile，拿到许可证后可用：

```powershell
docker compose --profile agent-server up -d
```

**国内网络拉不到 Docker Hub 时**，先用镜像源拉取再打回标准标签：

```powershell
docker pull docker.m.daocloud.io/library/postgres:16-alpine
docker tag  docker.m.daocloud.io/library/postgres:16-alpine postgres:16-alpine
docker pull docker.m.daocloud.io/library/python:3.12-slim
docker tag  docker.m.daocloud.io/library/python:3.12-slim python:3.12-slim
docker compose up -d --build
```

## 🛠 管理后台

地址：<http://localhost:5000/admin>，密码为 `.env` 中的 `ADMIN_PASSWORD`（默认 `globalshop-admin-2026`，**上线前务必修改**）。

| 标签页 | 能力 |
|---|---|
| 概览 | 会话数、知识片段数、已向量化数、运单数；一键重建索引 |
| 会话 | 查看所有会话及完整对话记录 |
| 知识库 | 新增/删除后台条目（保存即向量化）；查看文件来源统计（只读） |
| 模拟运单 | 录入运单号 + 中英状态 + 位置 + 时效，前台查该单号即返回录入内容 |

**两套知识来源**：
- `knowledge/` 下的 CSV / Markdown / JSON：文件即事实源，页面只读，改完点「重建索引」
- 后台新增的条目：存在数据库（`source=admin`），重建索引不会丢

**模拟运单**：录入后，用户在聊天里发「我的包裹到哪了？单号 xxx」即可命中；未录入的单号仍返回默认的「已到达目的国海关，正在清关中」话术。

## 💬 可以这样试

| 输入 | 预期路由 | 说明 |
|---|---|---|
| `我的包裹到哪了？单号 YT123456789CN` | 物流追踪 | 直接返回清关话术，不走大模型 |
| `Where is my parcel? YT123456789CN` | Logistics | 英文回复 |
| `退换货政策是怎样的` / `What is your return policy?` | 综合客服 / 账单 | 命中知识库 `refund` 章节 |
| `关税由谁承担？` | 账单与支付 | 命中 `customs` 章节 |
| `耳机连不上手机` | 技术支持 | 结合保修政策排查 |
| `写一首关于夏天的诗` | 护栏 | 双语礼貌拒答 |

---

## 🔧 扩展指南

### 加知识
- **临时/运营条目**：后台「知识库」页新增，保存即向量化
- **长期内容**：改 `knowledge/products.csv`、`policies.md`、`faq.json`，然后执行 `python scripts/ingest_kb.py --force`（或后台点「重建索引」）

FAQ 条目格式：

```json
{ "id": "faq-gift", "category": "products",
  "question_en": "Do you offer gift wrapping?",
  "question_zh": "支持礼品包装吗？",
  "answer_en": "Free gift wrap for orders over USD 50.",
  "answer_zh": "订单满 50 美元免费礼盒包装。" }
```

### 接入真实物流 API
编辑 `tools/logistics.py` 的 `track_package()`，把模拟返回值换成承运商（4PX / YunExpress / DHL）的查询结果，保持返回字段（`tracking_number / stage / events / eta_*`）不变即可。

### 新增智能体
1. 在 `multi_agents/` 新建 `xxx_agent.py`，继承 `BaseAgent`，实现 `process()`
2. 在 `multi_agents/__init__.py` 导出
3. 在 `multi_agent_customer_service.py` 的 `make_graph()` 里 `add_node` + 条件边
4. 在 `tools/query_tools.py` 的分类标签里加入新类别

### 换模型 / 换服务商
改 `.env` 的 `OPENAI_BASE_URL` 和 `OPENAI_MODEL` 即可，任何 OpenAI 兼容接口都能用。

---

## 🚀 部署到公网（魔搭 ModelScope 创空间 + Neon）

目标架构：**一个 Docker 创空间（embedded 模式）+ Neon Postgres**，国内直连、手机号注册、无需信用卡。

> 创空间的磁盘是临时的（重启/重建会清空），所以数据库必须用 Neon，不能落 SQLite。
> 双服务（独立 Agent Server + Postgres）属于 LangGraph 商业授权功能，本项目默认不用。

### 0. 为什么选 Docker 类型

| 类型 | 是否适合 |
|---|---|
| Gradio | ❌ 会接管页面，我们的 Flask + 自定义前端用不上 |
| Streamlit | ❌ 同上 |
| **Docker / 自定义镜像** | ✅ 直接使用仓库根目录的 `Dockerfile`，监听 7860 |

### 1. 前置检查

- **重置 Neon 密码**（连接串曾出现在聊天/截图里）
- `ADMIN_PASSWORD` 用强密码
- 推送前 `git status` 确认 `.env`、`data/` 没被提交

### 2. 注册并创建创空间（网页端，约 3 分钟）

1. 打开 <https://www.modelscope.cn>，用手机号注册/登录
2. 进入「创空间」→「创建创空间」
3. 填写：

   | 字段 | 值 |
   |---|---|
   | 创空间名称 | `GlobalShop`（会进 URL） |
   | 许可证 | Apache-2.0 |
   | **空间类型 / SDK** | **Docker**（自定义镜像），不要选 Gradio |
   | 可见性 | 公开 |

4. 创建完成后，页面会给一个 git 地址，形如：
   `https://www.modelscope.cn/studios/<用户名>/GlobalShop.git`

> 如果创建页没有 Docker 选项，先随便建一个空间，进「设置」里改 SDK 类型，或把页面截图发我。

### 3. 推送代码（复用现有仓库）

创空间本质是 git 仓库，加一个 remote 推上去：

```powershell
cd D:\DeepSeek\A4_AI_customer_service\customer-service-ai-agent

# 用户名 + 访问令牌 作为密码
git remote add ms https://www.modelscope.cn/studios/<用户名>/GlobalShop.git

# 第一次覆盖创空间的初始 commit
git push -f ms HEAD:main
```

如果提示 `src refspec main does not match`，改成 `git push -f ms HEAD:master`。

令牌位置：个人中心 → **访问令牌**（没有就新建一个）。

> 之后更新：`git add -A && git commit -m "..." && git push ms HEAD:main`
> GitHub 仓库继续作为源码仓库，创空间只作为部署目标。

### 4. 配置环境变量（关键）

创空间页面 → **设置** → **环境变量**（不同版本可能叫「变量 / 密钥」），逐个添加：

| Name | Value | 说明 |
|---|---|---|
| `DATABASE_URL` | `postgresql://neondb_owner:...@....neon.tech/neondb?sslmode=require` | Neon 连接串（**不要**加 hostaddr） |
| `OPENAI_API_KEY` | `sk-...` | 硅基流动 Key |
| `ADMIN_PASSWORD` | 强密码 | 后台登录 |
| `FLASK_SECRET_KEY` | 32 位随机十六进制 | 会话签名 |

可选（不填走代码默认值）：`OPENAI_MODEL`、`EMBEDDING_MODEL`、`WEB_CONCURRENCY=2`。

> 环境变量只在运行时注入，不会出现在代码里；保存后创空间会自动重启。

### 5. 首次初始化与验收

- 打开 `https://www.modelscope.cn/studios/<用户名>/GlobalShop`
- 若 Neon 里没有知识库：`/admin` → 概览 → **重建索引**（本项目通常已灌好 17 条）
- 后台密码 = `ADMIN_PASSWORD`
- 手机 4G 打开验证；重启创空间后确认历史仍在

### 6. 注意事项

| 项 | 说明 |
|---|---|
| 端口 | 容器监听 `0.0.0.0:7860`（`start.sh` 默认）；若平台注入 `PORT` 会跟随 |
| 502 / 无法访问 | 先看创空间「日志」：确认 gunicorn 实际监听端口，再把端口填到创空间设置里 |
| 磁盘 | 临时存储，重启丢本地文件；会话/知识库/运单都在 Neon ✅ |
| 休眠 | 免费空间长时间无访问会休眠，唤醒需几十秒 |
| 延迟 | 创空间在国内、Neon 在 us-east-2，跨区约 200–300ms；想更快可在 Neon 新建新加坡项目 |
| 安全 | 公开空间前台公开，后台有密码；Key 只放环境变量，绝不写进代码 |

## 🩺 常见问题

**Q：`langgraph dev` 启动即崩，报 `colorama`？**
装 `pip install colorama`（Windows 彩色日志依赖）。

**Q：报 `IndexError` / `MongoDBChatMessageHistory` 导入失败？**
`langchain-community` 0.4.x 移除了该后端，本项目的 `session_manager.py` 已做容错导入；默认内存后端不受影响。

**Q：对话报 429？**
模型服务商限流。每条用户消息会触发 2 次模型调用（分类 + 回答），免费额度较低时连续提问容易触发；代码已对 429 做 20s/40s 退避，仍失败请稍等 1–2 分钟或充值。

**Q：改了 Prompt / 智能体代码不生效？**
Docker 部署时执行 `docker compose restart web`；本地 direct run 则重启 `web_app.py`。

**Q：`docker compose up` 后 web 起不来？**
看 `docker compose logs web`。数据库未就绪时先 `docker compose ps` 确认 db healthy；第一次可等 10–20 秒再访问。

**Q：部署后报 `ENETUNREACH` / 连不上 Neon？**
平台出站只有 IPv4，而 Neon 某些端点只解析 IPv6。改用 Neon 的 **pooler** 连接串，或在 Neon 控制台确认项目有 IPv4 地址。

---

## 📄 许可证

本项目沿用原项目的 [Apache-2.0](LICENSE) 许可证。二次开发部分同样以 Apache-2.0 发布。
