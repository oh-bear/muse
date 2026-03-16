# Muse — Product Inspiration Workflow

> Automated pipeline that collects product signals from RSS feeds, extracts insights through AI, and delivers actionable product ideas to a small team.

## 1. System Architecture

```
┌──────────────────────────────────────────────────────┐
│                   Docker Compose                      │
│                                                       │
│  ┌──────────┐    ┌───────────────┐    ┌───────────┐  │
│  │ Miniflux │───→│  PostgreSQL   │←───│  Worker   │  │
│  │ (RSS)    │    │  (shared DB)  │    │  (Python) │  │
│  └──────────┘    └───────────────┘    └─────┬─────┘  │
│                                             │        │
└─────────────────────────────────────────────┼────────┘
                                              │
                               ┌──────────────┼──────────────┐
                               ↓              ↓              ↓
                           Notion        Telegram         Email
                         (idea DB)      (daily push)   (weekly digest)
```

### Services

| Service | Image | Role | Memory |
|---------|-------|------|--------|
| postgres | postgres:16-alpine | Shared storage for Miniflux + Worker | ~100-150MB |
| miniflux | miniflux/miniflux:latest | RSS collection, dedup, scheduling | ~30-50MB |
| worker | Custom Python 3.12 | AI processing, storage, push | ~80-120MB |

**Total: ~250-350MB.** Runs comfortably on a 1C1G VPS.

### Key Design Decisions

- **Miniflux owns RSS complexity** — parsing, scheduling, dedup, error retry are all handled. Worker only consumes via Miniflux REST API.
- **Single PostgreSQL instance** — Miniflux uses its own schema (`miniflux`). Worker uses `muse` schema. No cross-schema queries.
- **No message queue** — volume is low (hundreds of entries/day). APScheduler in-process is sufficient.
- **No AI framework** — direct API calls to Claude/OpenAI via `httpx`. Prompts are plain text templates. No LangChain/CrewAI overhead.
- **Alembic for migrations** — schema evolves across phases (signals → opportunities → ideas). Alembic tracks all changes.
- **Miniflux manages its own schema** — Worker runs `CREATE SCHEMA IF NOT EXISTS muse` on init. No cross-schema interference.

## 2. Data Flow

```
Miniflux fetches RSS (auto-scheduled)
       │
       ▼
Worker pulls new entries via Miniflux API (after_entry_id watermark, daily cron)
       │
       ▼
┌─── Layer 1: Signal Detection (per entry) ───┐
│  AI filters noise, scores & tags entries     │
│  Output: signals table (valuable ones only)  │
└──────────────────────────────────────────────┘
       │
       ▼
┌─── Layer 2: Opportunity Extraction (weekly) ─┐
│  AI clusters signals, finds unmet needs      │
│  Output: opportunities table + weekly brief  │
└──────────────────────────────────────────────┘
       │
       ▼
┌─── Layer 3: Idea Generation (monthly/adhoc) ─┐
│  AI produces actionable ideas with BMC        │
│  Output: ideas table → Notion + push         │
└──────────────────────────────────────────────┘
```

## 3. Data Model

### 3.1 `muse.signals`

Valuable entries that pass Layer 1 filtering.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| miniflux_entry_id | BIGINT UNIQUE | Reference to Miniflux entry |
| title | TEXT | Original title |
| url | TEXT | Original URL |
| source | VARCHAR(32) | `producthunt`, `hackernews`, `indie`, etc. |
| raw_summary | TEXT | Original content/summary from RSS |
| ai_summary | TEXT | AI-generated one-line summary |
| ai_tags | TEXT[] | AI-assigned tags (e.g. `ai-tool`, `saas`, `devtool`) |
| ai_score | SMALLINT | 1-5, signal strength |
| ai_reason | TEXT | Why this signal matters |
| created_at | TIMESTAMPTZ | |

Only entries scored >= 3 are stored. The rest are discarded.

### 3.2 `muse.opportunities`

Weekly aggregated insights from clustered signals.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| title | TEXT | Opportunity title |
| description | TEXT | What unmet need was identified |
| trend_category | VARCHAR(64) | e.g. `ai-automation`, `creator-economy` |
| unmet_need | TEXT | Core problem not yet solved well |
| market_gap | TEXT | What's missing in current solutions |
| geo_opportunity | TEXT | Regional/language arbitrage potential |
| signal_ids | UUID[] | Evidence: linked signal IDs |
| week_of | DATE | Monday of the analysis week |
| created_at | TIMESTAMPTZ | |

### 3.3 `muse.ideas`

Actionable product ideas with lean Business Model Canvas.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | |
| title | TEXT | Idea name |
| one_liner | TEXT | What it does, for whom |
| target_users | TEXT | Customer Segments |
| pain_point | TEXT | Value Propositions — what pain it solves |
| differentiation | TEXT | Why this wins vs. existing solutions |
| channels | TEXT[] | Customer acquisition channels |
| revenue_model | VARCHAR(32) | `subscription`, `one-time`, `freemium`, `ads`, `marketplace` |
| key_resources | TEXT | What's needed to build & run |
| cost_estimate | TEXT | Rough cost structure |
| validation_method | TEXT | Minimum viable validation approach |
| difficulty | SMALLINT | 1-5 |
| opportunity_id | UUID FK | Source opportunity |
| notion_page_id | VARCHAR(64) | Synced Notion page ID, nullable |
| status | VARCHAR(16) | `pending`, `promising`, `validated`, `abandoned` |
| created_at | TIMESTAMPTZ | |

### 3.4 Notion Database (final output only)

Fields mirror `muse.ideas` table. Notion is the team-facing view — PostgreSQL is the source of truth.

| Field | Type | Maps to |
|-------|------|---------|
| Title | Title | title |
| One-liner | Rich Text | one_liner |
| Target Users | Rich Text | target_users |
| Pain Point | Rich Text | pain_point |
| Differentiation | Rich Text | differentiation |
| Channels | Multi-select | channels |
| Revenue Model | Select | revenue_model |
| Key Resources & Cost | Rich Text | key_resources + cost_estimate |
| Validation Method | Rich Text | validation_method |
| Difficulty | Select | 1-5 |
| Evidence | URL | linked signal/opportunity URLs |
| Status | Select | status |
| Generated | Date | created_at |

## 4. AI Processing — The Core

### 4.1 Layer 1: Signal Detection (Daily)

**Input:** New Miniflux entries since last run.

**Prompt strategy:** Batch entries (10-20 per call) with a system prompt defining:
- What counts as a valuable product signal
- Scoring rubric (1-5)
- Configurable focus areas loaded from `config/focus.yaml`

**Focus config example (`config/focus.yaml`):**

```yaml
focus_areas:
  - ai-tools
  - developer-tools
  - productivity
  - creator-economy

exclude:
  - crypto
  - web3
  - gambling

score_threshold: 3

languages:
  - en
  - zh
```

**Evaluation dimensions:**
- Problem authenticity — real pain or manufactured need?
- Market timing — why now? What's the catalyst?
- Indie feasibility — can a small team build and ship this?

**Output per entry:** score (1-5), tags, one-line summary, reason. Only score >= threshold stored.

**Cost control:** Filter by keyword blacklist/whitelist BEFORE calling AI. Expect ~70% entries filtered out pre-AI.

**AI response format:** All AI calls return structured JSON. Example for Layer 1:

```json
{
  "entries": [
    {
      "entry_id": 12345,
      "score": 4,
      "tags": ["ai-tool", "developer-tools"],
      "summary": "AI-powered code review tool that catches logic errors, not just style",
      "reason": "Addresses real developer pain; timing aligns with AI coding tool adoption wave"
    }
  ]
}
```

Response parsing: `json.loads()` with a try/except fallback that retries once with a "respond in valid JSON" nudge. If both attempts fail, log the raw response and skip the batch.

**Error handling & retry:** AI API calls use exponential backoff (3 retries, 2s/4s/8s delay). On persistent failure, the batch is skipped and logged — next run picks up unprocessed entries via the `last_processed_entry_id` watermark. A Telegram alert is sent if >50% of batches fail in a single run.

**Source mapping:** The `source` column is derived from a Miniflux feed → source mapping in `config/focus.yaml`:

```yaml
source_mapping:
  "Product Hunt - Today": producthunt
  "Hacker News - Best": hackernews
  "Indie Hackers - Feed": indiehackers
```

### 4.2 Layer 2: Opportunity Extraction (Weekly)

**Input:** All signals from the past week (score >= 3). Expected volume: 20-50 signals/week. If a week exceeds 80 signals, chunk into groups of 40 by trend_category and run multiple calls.

**Prompt strategy:** Single call with all week's signals (or chunked if high volume). AI performs:
- **Trend clustering** — group signals by theme, identify what's hot
- **Complaint mining** — what are users unhappy about in these products?
- **Gap analysis** — what's missing? What's done poorly?
- **Geo/language arbitrage** — successful in EN market, missing in CN/SEA?

**Output:** 3-5 opportunities per week, each with evidence (signal IDs).

**Push:** Weekly brief → Email (HTML template) + Telegram.

### 4.3 Layer 3: Idea Generation (Monthly / On-demand)

**Input:** Accumulated opportunities from the past month.

**Prompt strategy:** Two-step:
1. Select top opportunities with strongest evidence
2. For each, generate 1-2 concrete product ideas using lean BMC template

**BMC-aligned output per idea:**
- One-liner (what + who)
- Customer Segments (target users)
- Value Propositions (pain point + differentiation)
- Channels (acquisition strategy guess)
- Revenue Streams (monetization model)
- Key Resources + Cost Structure (what it takes)
- Minimum validation method (cheapest way to test)
- Difficulty rating (1-5)

**Output:** Ideas → PostgreSQL → Notion + Telegram + Email.

## 5. RSS Sources (Phase 1)

| Source | RSS/API | Notes |
|--------|---------|-------|
| Product Hunt | RSS feed (daily top) | High signal for new product launches |
| Hacker News | `hn.algolia.com` API + RSS | Show HN, top stories, comments |
| Indie Hackers | RSS feed | Founder stories, milestones, revenue |
| Indie dev blogs | Curated RSS list | Manually maintained in config |

**Phase 2 (future):**
| Source | Method | Notes |
|--------|--------|-------|
| Reddit | `praw` (official API) | Subreddits: r/SideProject, r/indiehackers, r/startups, r/EntrepreneurRideAlong |
| App Store | iTunes Search API + `google-play-scraper` | Trending apps, new releases |

RSS sources are configured in Miniflux UI. No code change needed to add/remove feeds.

## 6. Push & Output

### Telegram
- Daily: signal count summary + top 3 signals of the day
- Weekly: opportunity brief (3-5 opportunities, key evidence)
- Monthly: new ideas with BMC summary

### Email
- Weekly digest: HTML template combining signals + opportunities
- Monthly: full idea cards with BMC details

### Notion
- Only ideas (Layer 3 output) are synced
- Worker creates/updates Notion pages via official SDK
- `notion_page_id` stored in PostgreSQL to enable updates

## 7. Project Structure

```
muse/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── .env.example
├── config/
│   └── focus.yaml           # AI focus areas, exclusions, thresholds
├── alembic/                 # Database migrations
│   ├── alembic.ini
│   └── versions/
├── src/
│   └── muse/
│       ├── __init__.py
│       ├── main.py           # Entry point, scheduler setup
│       ├── config.py         # Settings (pydantic-settings)
│       ├── db.py             # SQLAlchemy models + connection
│       ├── collector/
│       │   ├── __init__.py
│       │   └── miniflux.py   # Pull entries from Miniflux API
│       ├── analyzer/
│       │   ├── __init__.py
│       │   ├── prompts/      # Prompt templates (plain text files)
│       │   │   ├── signal_detection.txt
│       │   │   ├── opportunity_extraction.txt
│       │   │   └── idea_generation.txt
│       │   ├── signal.py     # Layer 1: signal detection
│       │   ├── opportunity.py # Layer 2: opportunity extraction
│       │   └── idea.py       # Layer 3: idea generation
│       ├── publisher/
│       │   ├── __init__.py
│       │   ├── notion.py     # Notion sync
│       │   ├── telegram.py   # Telegram bot push
│       │   └── email.py      # Email sender
│       └── scheduler.py      # APScheduler job definitions
├── templates/
│   ├── weekly_digest.html    # Email template
│   └── monthly_ideas.html
├── tests/
├── docs/
│   └── specs/
└── data/                     # gitignored, for local dev
```

## 8. Scheduling

| Job | Frequency | What it does |
|-----|-----------|-------------|
| `collect_signals` | Daily 08:00 UTC | Pull Miniflux → Layer 1 AI → store signals |
| `daily_push` | Chained after `collect_signals` | Telegram summary of today's signals |
| `extract_opportunities` | Weekly Monday 10:00 UTC | Aggregate week's signals → Layer 2 AI → store + push weekly brief |
| `generate_ideas` | Monthly 1st, 10:00 UTC | Aggregate month's opportunities → Layer 3 AI → store + Notion + push |

`daily_push` is triggered by `collect_signals` completion (event-driven, not clock-driven) to avoid race conditions.

All times configurable via `.env`.

### Scheduler Persistence

APScheduler uses PostgreSQL job store (`apscheduler.jobstores.sqlalchemy`) to survive container restarts. On startup, the worker checks for missed jobs and executes them immediately if the last run was missed. The `last_processed_entry_id` watermark in the database ensures idempotent re-runs — processing the same entries twice produces no duplicates.

## 9. Configuration

### `.env.example`

```env
# Database
DATABASE_URL=postgresql+asyncpg://muse:password@postgres:5432/muse

# Miniflux
MINIFLUX_URL=http://miniflux:8080
MINIFLUX_API_KEY=

# AI
AI_PROVIDER=claude          # claude | openai
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

# Notion
NOTION_API_KEY=
NOTION_IDEAS_DATABASE_ID=

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Email
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
EMAIL_RECIPIENTS=user1@example.com,user2@example.com

# Scheduler
TIMEZONE=Asia/Singapore
```

### `config/focus.yaml`

Team-editable file defining what the AI should pay attention to. No code change needed to shift focus.

```yaml
focus_areas:
  - ai-tools
  - developer-tools
  - productivity
  - saas
  - creator-economy

exclude:
  - crypto
  - web3
  - gambling
  - adult

score_threshold: 3

indie_criteria:
  max_team_size: 5
  prefer_low_infra: true
  prefer_digital_product: true
```

## 10. Observability

**Logging:** Structured JSON to stdout (Docker captures it). Each log entry includes:
- `layer`: which processing layer (collect / signal / opportunity / idea / push)
- `job_id`: scheduler run identifier
- `entry_count`: how many entries processed
- `ai_tokens_used`: token consumption per AI call
- `duration_ms`: processing time

Use `structlog` for structured logging.

**Alerts:** Critical failures push to Telegram:
- AI API down (>50% batch failures in a run)
- Miniflux unreachable
- Scheduler missed a job by >2 hours

**Cost tracking:** Each AI call logs model, input/output tokens, and estimated cost. A weekly summary of AI spend is included in the team digest.

**Manual trigger:** All jobs can be triggered via CLI: `python -m muse.main run <job_name>`. This covers the "on-demand" use case for Layer 3.

## 11. Tech Stack

| Component | Choice | Reason |
|-----------|--------|--------|
| Language | Python 3.12 | Team standard |
| Package manager | Poetry | Consistent with existing projects |
| Web framework | None | No HTTP server needed, pure worker |
| ORM | SQLAlchemy 2.0 (async) | Team standard |
| DB | PostgreSQL 16 | Shared with Miniflux |
| Scheduler | APScheduler 3.x | In-process, PostgreSQL job store for persistence |
| Migrations | Alembic | Schema evolution across phases |
| Logging | structlog | Structured JSON logging |
| AI client | `httpx` | Direct API calls, no framework |
| Notion | `notion-client` | Official SDK |
| Telegram | `python-telegram-bot` | Mature, async support |
| Email | `smtplib` (stdlib) | No dependency needed |
| Config | `pydantic-settings` | Type-safe env loading |
| Container | Docker + Compose | Single-command deployment |

## 12. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| AI filtering quality is poor | Garbage in → garbage out for all layers | Invest in prompt iteration. Log AI decisions for review. Make focus.yaml easily tunable. |
| Miniflux RSS feeds break | No new data | Miniflux has built-in error tracking. Add a health check alert to Telegram. |
| AI API costs grow | Budget pressure | Pre-filter with keywords before AI. Batch entries. Use cheaper models for Layer 1. |
| Notion API rate limits | Sync failures | Only sync Layer 3 (low volume). Retry with backoff. |
| Signal dedup across sources | Same product from PH + HN counted twice | URL dedup in signals table. Title similarity check (simple fuzzy match) before AI call. |

## 13. Phased Rollout

### Phase 1 — MVP (Week 1-2)
- Docker Compose with Miniflux + PostgreSQL + Worker
- RSS sources: Product Hunt, Hacker News (3-5 feeds)
- Layer 1 only: signal detection + daily Telegram push
- `focus.yaml` config

### Phase 2 — Weekly Insights (Week 3-4)
- Layer 2: opportunity extraction
- Email weekly digest (HTML template)
- Notion integration for ideas

### Phase 3 — Idea Generation (Week 5-6)
- Layer 3: BMC-aligned idea generation
- Monthly idea push
- Notion database fully synced

### Phase 4 — Expand Sources (Future)
- Reddit integration via `praw`
- App Store data
- Custom scrapers as needed
