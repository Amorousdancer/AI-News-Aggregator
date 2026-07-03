# AI 新闻聚合器

AI 驱动的新闻聚合系统 — 自动抓取、智能分析、每日报告。

[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 功能特性

- **多源抓取** — 支持 RSS 订阅源，定时自动拉取最新文章
- **AI 智能分析** — 使用 Claude/OpenAI 对文章进行多维度评分（相关性、可信度、新鲜度、深度等）
- **自动去重** — 基于内容哈希和 SimHash 算法识别重复新闻
- **每日报告** — 自动生成新闻摘要报告，支持 Markdown/HTML 格式
- **成本控制** — 内置 AI 调用费用追踪和预算限制
- **可观测性** — 结构化日志、健康检查、调度器状态监控

---

## 快速开始

### 前置要求

- Python 3.12+
- PostgreSQL 16+（或 Docker）
- Anthropic API Key（[获取地址](https://console.anthropic.com/)）

### 1. 克隆项目

```bash
git clone https://github.com/your-username/ai-news-aggregator.git
cd ai-news-aggregator
```

### 2. 启动数据库

**方式 A：Docker（推荐）**

```bash
docker compose up -d postgres
```

**方式 B：本地 PostgreSQL**

确保 PostgreSQL 已运行，创建数据库：

```sql
CREATE DATABASE news_aggregator;
CREATE USER aggregator WITH PASSWORD 'aggregator';
GRANT ALL PRIVILEGES ON DATABASE news_aggregator TO aggregator;
```

### 3. 配置环境

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env，填入你的 API Key
# ANTHROPIC_API_KEY=sk-ant-你的密钥
```

### 4. 安装依赖

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# Mac/Linux:
# source .venv/bin/activate

# 安装依赖
pip install -e ".[dev]"
```

### 5. 初始化数据库

```bash
alembic upgrade head
```

### 6. 启动应用

```bash
# 开发模式（热重载）
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# 或使用项目脚本
python -m src.main
```

访问 http://localhost:8000/docs 查看 API 文档。

---

## Docker 一键部署

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 ANTHROPIC_API_KEY

# 2. 启动所有服务
docker compose up -d
```

---

## 项目结构

```
ai-news-aggregator/
├── src/
│   ├── api/              # FastAPI 路由和端点
│   │   ├── articles.py   # 文章 API
│   │   ├── sources.py    # 新闻源 API
│   │   ├── reports.py    # 报告 API
│   │   └── health.py     # 健康检查
│   ├── analyzer/         # AI 分析模块
│   │   ├── llm_client.py # LLM 客户端（Claude/OpenAI）
│   │   ├── scorer.py     # 文章评分器
│   │   └── prompts.py    # 提示词模板
│   ├── dedup/            # 去重算法
│   │   ├── content_hash.py  # 内容哈希
│   │   └── simhash.py    # SimHash 相似度
│   ├── fetchers/         # 新闻抓取器
│   │   └── rss_fetcher.py
│   ├── models/           # SQLAlchemy 数据模型
│   ├── reports/          # 报告生成
│   ├── scheduler/        # 定时任务调度
│   └── config.py         # 配置管理
├── alembic/              # 数据库迁移
├── tests/                # 测试用例
├── docker-compose.yml    # Docker 编排
└── pyproject.toml        # 项目配置
```

---

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `GET` | `/api/sources` | 获取所有新闻源 |
| `POST` | `/api/sources` | 添加新闻源 |
| `GET` | `/api/articles` | 文章列表（支持分页、筛选） |
| `GET` | `/api/articles/{id}` | 文章详情 |
| `GET` | `/api/reports` | 每日报告列表 |
| `GET` | `/api/reports/{date}` | 指定日期报告 |
| `GET` | `/api/reports/{date}/html` | HTML 格式报告 |

完整文档：http://localhost:8000/docs

---

## 定时任务

| 任务 | 频率 | 说明 |
|------|------|------|
| 抓取新闻 | 每 30 分钟 | 从所有启用的源拉取文章 |
| AI 分析 | 每 1 小时 | 分析未评分的文章 |
| 生成日报 | 每天 16:00 (UTC+8) | 生成前一日新闻报告 |
| 清理旧文 | 每天 03:00 (UTC) | 删除 90 天前的文章 |

---

## 配置项

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `postgresql+asyncpg://aggregator:aggregator@localhost:5432/news_aggregator` | 数据库连接 |
| `ANTHROPIC_API_KEY` | — | Anthropic API 密钥（必填） |
| `OPENAI_API_KEY` | — | OpenAI API 密钥（可选） |
| `DAILY_COST_LIMIT_USD` | `20.00` | 每日 AI 调用费用上限 |
| `MAX_CONCURRENT_FETCHES` | `5` | 最大并发抓取数 |
| `ARTICLE_RETENTION_DAYS` | `90` | 文章保留天数 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

---

## 开发

```bash
# 运行测试
pytest

# 代码检查
ruff check .

# 代码格式化
ruff format .
```

---

## 技术栈

- **Web 框架**: FastAPI
- **数据库**: PostgreSQL + SQLAlchemy (async)
- **AI**: Anthropic Claude / OpenAI
- **调度**: APScheduler
- **去重**: 内容哈希 + SimHash
- **容器化**: Docker + Docker Compose

---

## License

MIT License - 详见 [LICENSE](LICENSE) 文件
