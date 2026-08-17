# 企业级 RAG 知识库问答系统 (Enterprise RAG System)

一个面向企业场景的**检索增强生成（RAG）**知识库问答系统。上传 PDF / Markdown 文档，系统会自动解析、向量化入库，之后即可基于文档内容进行多轮流式问答，并附可点击的引用来源。

## ✨ 核心特性

| 特性 | 说明 | 解决什么问题 |
| :--- | :--- | :--- |
| 🧩 **复杂文档结构化解析** | PyMuPDF 提取标题层级，表格转 Markdown | 传统按页提取丢失结构，大模型看不懂层级 |
| 🌲 **父子文档策略 (Parent-Child)** | 大块(上下文)切小块(检索)，命中小块还原大块 | 兼顾召回精准度与上下文完整度 |
| 🔀 **混合检索 (Hybrid Search)** | FAISS 向量 + BM25 关键词双路召回融合 | 专有名词（工号/型号）向量检索失效 |
| 🎯 **重置排序 (Reranker)** | Cross-Encoder 二次精排，Top-50 → Top-5 | 降低幻觉，解决 RAG 最后一公里 |
| ⚡ **异步工程化** | Celery + Redis，状态机 PENDING→PROCESSING→COMPLETED | 上传百页 PDF 不再接口超时 |
| 📖 **流式问答 + 引用溯源** | SSE 逐 token 输出，引用来源可点击定位 | 真实产品体验，答案可验证 |
| 🔍 **全链路可观测** | LangSmith Trace（可选） | 排查 Bad Case：检索失效 or 模型理解错误 |
| 🐳 **容器化部署** | Docker Compose 一键拉起 API/Worker/MySQL/Redis/Web | 一套命令从零到可用 |

---

## 🏗 系统架构

```
┌──────────┐   REST/SSE   ┌──────────────┐
│ 前端 Streamlit │ ─────────▶ │  FastAPI 网关  │
└──────────┘              └──────┬───────┘
                                 │ 鉴权 JWT
                ┌────────────────┼─────────────────┐
                ▼                ▼                 ▼
          文档管理服务        对话服务(RAG)      用户/会话
                │                │                 │
                ▼                ▼                 ▼
        ┌───────────────┐   ┌──────────────┐   ┌──────────┐
        │  Celery Worker │   │  混合检索     │   │   MySQL   │
        │ 解析→切分→向量化 │   │ FAISS + BM25 │   │ 用户/文档/ │
        └───────┬───────┘   │      +       │   │ 会话/历史  │
                │            │   Reranker    │   └──────────┘
                ▼            └──────┬───────┘
        ┌───────────────┐           ▼
        │  FAISS 向量库  │       Qwen LLM (流式)
        └───────────────┘           │
        Redis (Broker)  ◀───────────┘
```

### 数据流转

1. **上传**：`POST /api/documents/upload` 立即返回文档记录（状态 `PENDING`），异步派发 Celery 任务。
2. **处理**：Worker 解析 PDF → 语义切分（父子文档）→ 向量化 → 写入 FAISS，状态流转至 `COMPLETED`。
3. **问答**：`POST /api/chat/stream` 混合检索 → 重排 → 拼装 Prompt → Qwen 流式生成 → 返回引用来源。

---

## 🚀 快速开始（Docker）

### 前置要求
- 安装 **Docker Desktop**（勾选 WSL2 引擎），内存建议 ≥ 4GB
- 申请 **通义千问 API Key**（[阿里云百炼](https://bailian.console.aliyun.com/)），开通：
  - `qwen-plus`（对话生成）
  - `text-embedding-v3`（向量化）
  - `gte-rerank`（重排序）

### 启动步骤

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY

# 2. 一条命令启动整套集群
docker compose up -d --build

# 3. 打开前端
# 浏览器访问 http://localhost:8501
```

### 服务与端口

| 服务 | 地址 | 说明 |
| :--- | :--- | :--- |
| Web 前端 | http://localhost:8501 | Streamlit 交互界面 |
| API 文档 | http://localhost:8000/docs | Swagger 在线调试 |
| API 健康检查 | http://localhost:8000/health | 存活探针 |
| MySQL | localhost:3306 | 业务数据 |
| Redis | localhost:6379 | Celery Broker |

---

## 🧪 本地开发与测试

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 运行单元测试（离线，使用 mock 嵌入与 LLM）
pytest -q
```

### 本地运行（不依赖 Docker）

```bash
# 终端 1：启动 API
uvicorn app.main:app --reload --port 8000

# 终端 2：启动 Worker（需本地 Redis）
celery -A app.tasks.celery_app:celery_app worker --loglevel=info

# 终端 3：启动前端
cd ../frontend && streamlit run app.py
```

---

## 📁 项目结构

```
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 入口
│   │   ├── config.py          # 配置（pydantic-settings）
│   │   ├── database.py        # 异步数据库引擎
│   │   ├── models/            # users / documents / chat_sessions / chat_history
│   │   ├── api/               # auth / documents / chat 路由
│   │   ├── core/              # JWT、统一响应、全局异常
│   │   ├── services/
│   │   │   ├── rag/           # parser / splitter / vectorstore / retriever / reranker / llm / pipeline
│   │   │   ├── chat_service.py
│   │   │   └── document_service.py
│   │   └── tasks/             # Celery 任务
│   └── tests/                 # pytest 测试
├── frontend/                  # Streamlit 界面
├── docker-compose.yml         # 一键部署
└── .env.example               # 环境变量模板
```

---

## 🗄 数据库设计

| 表 | 说明 |
| :--- | :--- |
| `users` | 用户（id, username, password_hash, role） |
| `documents` | 文档元数据（含状态机 `PENDING/PROCESSING/COMPLETED/FAILED`、chunk_count） |
| `chat_sessions` | 对话会话（支持左侧历史列表） |
| `chat_history` | 对话明细（role, content, sources 存 JSON 引用） |

---
## 🛠 可观测性（可选）

在 `.env` 中配置后自动启用 LangSmith：

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_...
LANGCHAIN_PROJECT=enterprise-rag
```

无 Key 时系统自动跳过，不影响主流程。

---

## 📄 许可

MIT License

---

## 演进方向（Roadmap）

- 向量库升级为 **Milvus / Qdrant**（支持分布式、多副本、标量过滤）
- 数据库迁移改用 **Alembic**（当前为启动建表）
- 接入 **用户反馈 + 在线评测**（RAGAS 指标），形成迭代闭环
- 前端改为 **Vue3**，支持流式打字机与引用点击高亮
