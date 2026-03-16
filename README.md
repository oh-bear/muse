# Muse

独立产品灵感发现与想法生产工作流。

从 RSS 数据源中自动采集、筛选、分析产品信息，通过 AI 提炼产品机会并生成可执行的产品想法。

## 架构

```
Miniflux (RSS) → Python Worker → PostgreSQL → Notion + Email/Telegram
```

## 流程

1. **信号识别** — 每日从 RSS 条目中筛选有价值的产品信号
2. **机会提炼** — 每周聚合信号，发现未被满足的需求和市场空白
3. **想法生成** — 基于机会库，生成带商业模式画布的可执行产品想法

## 部署

```bash
cp .env.example .env
# 编辑 .env 填入 API keys
docker compose up -d
```

## 技术栈

- Python 3.12
- PostgreSQL 16 (共享 Miniflux)
- Miniflux (RSS 采集)
- APScheduler (定时任务)
- Claude/OpenAI API (AI 分析)
- Notion API (想法存储)
- Telegram Bot + Email (推送)
