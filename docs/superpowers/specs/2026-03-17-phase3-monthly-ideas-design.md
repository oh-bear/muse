# Phase 3: Monthly Ideas with BMC Generation + Notion Sync

> Layer 3 of the Muse AI pipeline — transforms monthly accumulated opportunities into actionable product ideas with lean Business Model Canvas, optionally synced to Notion as a pluggable extension.

## 1. Overview

**Goal:** Each month, aggregate all opportunities from the past 30 days, run them through AI to generate 1-2 concrete product ideas per opportunity with lean BMC analysis, store in PostgreSQL, push summaries via Telegram + Email, and optionally sync to Notion for human review.

**Key decisions (from brainstorming):**
- Semi-automatic: scheduled with configurable cron, ideas start as `pending`
- Process ALL monthly opportunities — no filtering
- Notion is a pluggable extension, NOT part of core flow
- Bidirectional Notion sync via separate scheduled job

## 2. Architecture

### 2.1 Core Flow (always runs)

```
Monthly cron
    │
    ▼
generate_ideas_job()
    │
    ├─ Query all opportunities from past 30 days
    ├─ IdeaGenerator.generate(opportunities) → ideas with BMC
    ├─ Store ideas in muse.ideas (status=pending)
    ├─ TelegramPublisher.send_monthly_ideas()
    └─ EmailPublisher.send_monthly_ideas()
```

### 2.2 Notion Sync (optional, separate job)

```
notion_sync_job() — runs only if NOTION_API_KEY + NOTION_IDEAS_DATABASE_ID configured
    │
    ├─ Push: ideas with notion_page_id=NULL → create Notion pages → save notion_page_id
    └─ Pull: read Notion pages with updated status → update muse.ideas.status + updated_at
```

Notion sync is a separate scheduled job (every 6 hours by default). It can be disabled entirely by not setting Notion env vars. Removing Notion = delete `notion.py` + remove sync job registration in `main.py`. Core flow is completely unaffected.

## 3. Data Model

### 3.1 `muse.ideas` Table

```sql
CREATE TABLE muse.ideas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    one_liner       TEXT NOT NULL,
    target_users    TEXT NOT NULL,
    pain_point      TEXT NOT NULL,
    differentiation TEXT NOT NULL,
    channels        TEXT[] DEFAULT '{}',
    revenue_model   VARCHAR(32) NOT NULL,
    key_resources   TEXT NOT NULL,
    cost_estimate   TEXT NOT NULL,
    validation_method TEXT NOT NULL,
    difficulty      SMALLINT NOT NULL,     -- 1-5
    opportunity_id  UUID REFERENCES muse.opportunities(id),
    notion_page_id  VARCHAR(64),           -- NULL when Notion not used
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Status lifecycle:** `pending` → `promising` / `validated` / `abandoned`
- Ideas are created as `pending` by the AI pipeline
- Human updates status via Notion (pulled by sync job) or direct DB update

### 3.2 SQLAlchemy Model

```python
class Idea(Base):
    __tablename__ = "ideas"
    __table_args__ = {"schema": "muse"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(Text)
    one_liner: Mapped[str] = mapped_column(Text)
    target_users: Mapped[str] = mapped_column(Text)
    pain_point: Mapped[str] = mapped_column(Text)
    differentiation: Mapped[str] = mapped_column(Text)
    channels: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    revenue_model: Mapped[str] = mapped_column(String(32))
    key_resources: Mapped[str] = mapped_column(Text)
    cost_estimate: Mapped[str] = mapped_column(Text)
    validation_method: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(SmallInteger)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("muse.opportunities.id"), nullable=True
    )
    notion_page_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
```

### 3.3 Indexes

```sql
CREATE INDEX idx_ideas_notion_page_id_null ON muse.ideas (id) WHERE notion_page_id IS NULL;
CREATE INDEX idx_ideas_opportunity_id ON muse.ideas (opportunity_id);
```

The partial index on `notion_page_id IS NULL` optimizes the push query (finding un-synced ideas). The `opportunity_id` index supports FK lookups and monthly queries.

### 3.4 Status Validation

Valid statuses: `pending`, `promising`, `validated`, `abandoned`.

Python-side validation via a constant set:

```python
VALID_IDEA_STATUSES = {"pending", "promising", "validated", "abandoned"}
```

The `pull_status_updates` method must reject unknown statuses from Notion and log a warning instead of writing invalid values to the DB.

### 3.5 Alembic Migration

New migration: `add_ideas_table`. Same approach as previous migrations — manually clean up any spurious Miniflux table operations from autogenerate. Include indexes from Section 3.3.

### 3.6 Prerequisite: Add `confidence` to Opportunity Model

The `Opportunity` model currently does not persist the `confidence` field from AI output. This Phase 3 spec requires it for idea generation context. Add to the same migration (or a separate one):

```python
# In Opportunity model (db.py):
confidence: Mapped[str] = mapped_column(String(16), default="medium")
```

Also update `extract_opportunities_job` in `scheduler.py` to persist `confidence` when storing opportunities:
```python
session.add(Opportunity(
    ...
    confidence=opp.get("confidence", "medium"),
))
```

## 4. AI Processing — Layer 3: Idea Generation

### 4.1 IdeaGenerator

Follows the same pattern as `OpportunityExtractor`:
- Dataclass with `AIClient`, prompt paths, config
- `generate(opportunities) → IdeaGenerationResult`
- Chunks opportunities if > `max_opportunities_per_call` (default 20)
- Uses `string.Template` with `$` variable syntax for prompts

```python
@dataclass
class IdeaGenerationResult:
    ideas: list[dict[str, Any]] = field(default_factory=list)
    monthly_summary: str = ""
    failed: bool = False
    error: str = ""

@dataclass
class IdeaGenerator:
    ai_client: AIClient
    system_prompt_path: str
    user_prompt_path: str
    focus_areas: list[str]
    indie_criteria: dict[str, Any]
    max_opportunities_per_call: int = 20

    async def generate(self, opportunities: list[dict[str, Any]]) -> IdeaGenerationResult:
        # Same chunking pattern as OpportunityExtractor
        ...
```

### 4.2 Prompt Templates

**System prompt** (`idea_generation_system.txt`):
- Role: product ideation expert for indie developers
- Input: monthly opportunities with evidence
- Task: generate 1-2 concrete, buildable product ideas per opportunity
- Each idea must include lean BMC fields
- Output: structured JSON

**User prompt** (`idea_generation_user.txt`):
- Template with `$opportunities` placeholder
- Formatted opportunities list with title, description, unmet_need, market_gap, geo_opportunity, confidence

**AI response format:**
```json
{
  "ideas": [
    {
      "title": "CodeReview.ai",
      "one_liner": "AI-powered logic review for pull requests, catching bugs that linters miss",
      "target_users": "Small dev teams (2-10) shipping fast without dedicated QA",
      "pain_point": "Linters catch style, not logic. Code review is slow and inconsistent.",
      "differentiation": "Focuses on logic errors and business rule violations, not formatting",
      "channels": ["Developer communities", "GitHub Marketplace", "Dev Twitter"],
      "revenue_model": "freemium",
      "key_resources": "AI/ML expertise, GitHub API integration, cloud compute",
      "cost_estimate": "Low — API costs + hosting, <$500/month to start",
      "validation_method": "Build GitHub Action MVP, post on HN Show, measure installs in 2 weeks",
      "difficulty": 3,
      "source_opportunity_id": "<opportunity ID from input>"
    }
  ],
  "monthly_summary": "AI developer tools and SEA localization dominated this month's opportunities."
}
```

### 4.3 Opportunity Formatting for AI

```python
def _format_opportunities(self, opportunities: list[dict[str, Any]]) -> str:
    lines = []
    for opp in opportunities:
        lines.append(
            f"- Opportunity ID: {opp['id']}\n"
            f"  Title: {opp['title']}\n"
            f"  Description: {opp.get('description', '')}\n"
            f"  Category: {opp.get('trend_category', '')}\n"
            f"  Unmet Need: {opp.get('unmet_need', '')}\n"
            f"  Market Gap: {opp.get('market_gap', '')}\n"
            f"  Geo Opportunity: {opp.get('geo_opportunity', '')}\n"
            f"  Confidence: {opp.get('confidence', 'unknown')}\n"
        )
    return "\n".join(lines)
```

The AI prompt instructs the model to return `source_opportunity_id` matching the Opportunity ID from input, enabling reliable DB-level linking without fragile title matching.

## 5. Scheduler Jobs

### 5.1 `generate_ideas_job()` — Monthly

```python
async def generate_ideas_job(settings: Settings, focus: FocusConfig, session_factory) -> None:
    """Monthly job: query month's opportunities → AI idea generation → store → push."""
    job_id = str(uuid.uuid4())[:8]
    logger.info("job_started", job="generate_ideas", job_id=job_id)

    telegram = TelegramPublisher(bot_token=settings.telegram_bot_token, chat_id=settings.telegram_chat_id)

    # 1. Query opportunities from the past 30 days
    one_month_ago = datetime.now(timezone.utc) - timedelta(days=30)
    async with session_factory() as session:
        result = await session.execute(
            select(Opportunity).where(Opportunity.created_at >= one_month_ago)
        )
        db_opps = result.scalars().all()

    if not db_opps:
        logger.info("no_opportunities_for_ideas", job_id=job_id)
        return

    # 2. Convert to dicts for AI
    opps_data = [
        {
            "id": str(o.id),
            "title": o.title,
            "description": o.description,
            "trend_category": o.trend_category,
            "unmet_need": o.unmet_need,
            "market_gap": o.market_gap,
            "geo_opportunity": o.geo_opportunity,
            "confidence": o.confidence,
        }
        for o in db_opps
    ]

    # 3. Run IdeaGenerator
    api_key = settings.anthropic_api_key if settings.ai_provider == "claude" else settings.openai_api_key
    ai_client = AIClient(provider=settings.ai_provider, api_key=api_key)
    generator = IdeaGenerator(
        ai_client=ai_client,
        system_prompt_path=str(PROMPTS_DIR / "idea_generation_system.txt"),
        user_prompt_path=str(PROMPTS_DIR / "idea_generation_user.txt"),
        focus_areas=focus.focus_areas,
        indie_criteria=focus.indie_criteria,
    )
    generation = await generator.generate(opps_data)

    if generation.failed and not generation.ideas:
        await telegram.send_alert(f"Idea generation failed: {generation.error}")
        return

    # 4. Store ideas
    opp_id_map = {str(o.id): o.id for o in db_opps}
    async with session_factory() as session:
        for idea in generation.ideas:
            opp_id = opp_id_map.get(idea.get("source_opportunity_id"))
            session.add(Idea(
                title=idea["title"],
                one_liner=idea.get("one_liner", ""),
                target_users=idea.get("target_users", ""),
                pain_point=idea.get("pain_point", ""),
                differentiation=idea.get("differentiation", ""),
                channels=idea.get("channels", []),
                revenue_model=idea.get("revenue_model", ""),
                key_resources=idea.get("key_resources", ""),
                cost_estimate=idea.get("cost_estimate", ""),
                validation_method=idea.get("validation_method", ""),
                difficulty=idea.get("difficulty", 3),
                opportunity_id=opp_id,
            ))
        await session.commit()

    # 5. Calculate month label
    month_label = datetime.now(timezone.utc).strftime("%Y-%m")

    # 6. Push via Telegram
    try:
        await telegram.send_monthly_ideas(
            ideas=generation.ideas,
            monthly_summary=generation.monthly_summary,
            opportunity_count=len(db_opps),
            month_label=month_label,
        )
    except Exception as e:
        logger.error("telegram_monthly_failed", error=str(e))

    # 7. Push via Email
    email = EmailPublisher(
        smtp_host=settings.smtp_host, smtp_port=settings.smtp_port,
        smtp_user=settings.smtp_user, smtp_password=settings.smtp_password,
        recipients=[r.strip() for r in settings.email_recipients.split(",") if r.strip()],
    )
    try:
        await email.send_monthly_ideas(
            ideas=generation.ideas,
            monthly_summary=generation.monthly_summary,
            opportunity_count=len(db_opps),
            month_label=month_label,
        )
    except Exception as e:
        logger.error("email_monthly_failed", error=str(e))

    logger.info("job_completed", job="generate_ideas", job_id=job_id,
               opportunities=len(db_opps), ideas=len(generation.ideas))
```

**Chunk failure semantics:** Same as `OpportunityExtractor` — if a single chunk fails, `result.failed` is set but successfully generated ideas from other chunks are still collected. The job-level `if generation.failed` check only triggers if ALL chunks fail (no ideas generated). Partial results are stored and pushed.

### 5.2 `notion_sync_job()` — Every 6 hours (optional)

Note: `notion_sync_job` does NOT take `focus` — it only needs `settings` and `session_factory`. This is intentional: Notion sync is a data transport concern, not an analysis concern.

```python
async def notion_sync_job(settings: Settings, session_factory) -> None:
    """Sync ideas with Notion — push new, pull status updates."""
    notion = NotionPublisher(api_key=settings.notion_api_key,
                             ideas_database_id=settings.notion_ideas_database_id)
    if not notion.is_configured():
        return  # Silently skip — Notion is optional

    # Push: query ideas WHERE notion_page_id IS NULL → create Notion pages → update notion_page_id
    async with session_factory() as session:
        result = await session.execute(
            select(Idea).where(Idea.notion_page_id.is_(None))
        )
        new_ideas = result.scalars().all()

    if new_ideas:
        pushed = await notion.push_ideas(new_ideas)
        async with session_factory() as session:
            for idea_id, page_id in pushed:
                await session.execute(
                    update(Idea).where(Idea.id == idea_id).values(notion_page_id=page_id)
                )
            await session.commit()

    # Pull: read Notion statuses → update DB where changed
    updates = await notion.pull_status_updates()
    if updates:
        async with session_factory() as session:
            for page_id, new_status, edited_time in updates:
                if new_status not in VALID_IDEA_STATUSES:
                    logger.warning("notion_invalid_status", page_id=page_id, status=new_status)
                    continue
                await session.execute(
                    update(Idea)
                    .where(Idea.notion_page_id == page_id, Idea.updated_at < edited_time)
                    .values(status=new_status, updated_at=edited_time)
                )
            await session.commit()
```

### 5.3 Config

New settings in `Settings`:
```python
# Monthly schedule (1st of month)
monthly_schedule_day: int = 1
monthly_schedule_hour: int = 10
monthly_schedule_minute: int = 0

# Notion sync interval (hours, 0 = disabled)
notion_sync_interval_hours: int = 6
```

### 5.4 Job Registration in `main.py`

```python
# Monthly idea generation
scheduler.add_job(
    generate_ideas_job, "cron",
    day=settings.monthly_schedule_day,
    hour=settings.monthly_schedule_hour,
    minute=settings.monthly_schedule_minute,
    args=[settings, focus, session_factory],
    id="generate_ideas", replace_existing=True,
    misfire_grace_time=7200,
)

# Notion sync (only if configured)
if settings.notion_api_key and settings.notion_ideas_database_id:
    scheduler.add_job(
        notion_sync_job, "interval",
        hours=settings.notion_sync_interval_hours,
        args=[settings, session_factory],
        id="notion_sync", replace_existing=True,
    )
```

## 6. Notion Publisher — Pluggable Extension

### 6.1 Design Principles

- All Notion logic lives in `src/muse/publisher/notion.py` — single file
- Never imported by core flow (`generate_ideas_job` does NOT import NotionPublisher)
- `notion_sync_job` is the only consumer, registered conditionally in `main.py`
- Removing Notion = delete `notion.py` + remove job registration + drop `notion_page_id` column

### 6.2 NotionPublisher Methods

```python
@dataclass
class NotionPublisher:
    api_key: str
    ideas_database_id: str

    def is_configured(self) -> bool:
        return bool(self.api_key and self.ideas_database_id)

    async def health_check(self) -> bool:
        # Already implemented

    async def push_ideas(self, ideas: list[Idea]) -> list[tuple[uuid.UUID, str]]:
        """Create Notion pages for ideas without notion_page_id.
        Returns list of (idea_id, notion_page_id) for DB update."""

    async def pull_status_updates(self) -> list[tuple[str, str, datetime]]:
        """Query Notion pages, return (notion_page_id, new_status, last_edited_time)
        for pages whose status differs from what we last synced."""
```

### 6.3 Notion Page Structure

Each idea → one Notion page in the configured database:

| Notion Property | Type | Source |
|----------------|------|--------|
| Title | title | idea.title |
| One-liner | rich_text | idea.one_liner |
| Target Users | rich_text | idea.target_users |
| Pain Point | rich_text | idea.pain_point |
| Differentiation | rich_text | idea.differentiation |
| Channels | multi_select | idea.channels |
| Revenue Model | select | idea.revenue_model |
| Key Resources | rich_text | idea.key_resources |
| Cost Estimate | rich_text | idea.cost_estimate |
| Validation | rich_text | idea.validation_method |
| Difficulty | select | "1"-"5" |
| Status | select | idea.status |
| Generated | date | idea.created_at |

### 6.4 Bidirectional Sync Logic

**Push (DB → Notion):**
1. Query ideas where `notion_page_id IS NULL`
2. Create Notion page with all properties
3. Update `idea.notion_page_id` in DB

**Pull (Notion → DB):**
1. Query Notion database pages
2. For each page with a matching `notion_page_id` in DB:
   - Compare `status` — if different AND Notion's `last_edited_time` > idea's `updated_at`, update DB
3. Last-write-wins conflict resolution using timestamps

**Edge cases:**
- Notion page deleted manually → leave idea in DB, clear `notion_page_id` (re-push on next cycle)
- Notion property missing → skip that field, log warning
- Rate limit hit → backoff and retry, process remaining on next cycle

## 7. Push Channels

### 7.1 Telegram — `send_monthly_ideas()`

New method on `TelegramPublisher`:

```
💡 *Muse Monthly Ideas*
_2026-03 · 12 opportunities → 8 ideas_

*1. CodeReview.ai* ⭐⭐⭐
AI-powered logic review for PRs
Revenue: freemium | Difficulty: 3/5

*2. LocalPay SEA* ⭐⭐⭐⭐
Payment integration for SEA SaaS
Revenue: marketplace | Difficulty: 4/5

...
```

### 7.2 Email — `send_monthly_ideas()`

New Jinja2 template `templates/monthly_ideas.html` with full BMC cards. Same styling as `weekly_digest.html`.

New method on `EmailPublisher`:
```python
async def send_monthly_ideas(
    self,
    ideas: list[dict[str, Any]],
    monthly_summary: str,
    opportunity_count: int,
    month_label: str,
) -> None:
```

## 8. Testing Strategy

### 8.1 Unit Tests

| Test file | Tests |
|-----------|-------|
| `test_idea_generator.py` | generate returns ideas, chunks large sets, handles AI failure, handles empty input |
| `test_telegram.py` | add `test_send_monthly_ideas` |
| `test_email.py` | add `test_send_monthly_ideas` |
| `test_notion.py` | push_ideas, pull_status_updates, handles unconfigured, handles API errors |
| `test_scheduler_ideas.py` | full generate_ideas_job flow with mocks |
| `test_notion_sync.py` | full notion_sync_job flow: push new ideas, pull status changes, skip when unconfigured |

### 8.2 Integration Test

Add `test_idea_pipeline` to `test_integration.py`:
- Seed opportunities → mock Claude API → run `generate_ideas_job` → verify ideas stored → verify push called

## 9. Files to Create/Modify

### New Files
- `src/muse/analyzer/idea.py` — IdeaGenerator
- `src/muse/analyzer/prompts/idea_generation_system.txt` — system prompt
- `src/muse/analyzer/prompts/idea_generation_user.txt` — user prompt
- `templates/monthly_ideas.html` — email template
- `alembic/versions/xxx_add_ideas_table.py` — migration
- `tests/test_idea_generator.py`
- `tests/test_scheduler_ideas.py`
- `tests/test_notion_sync.py`

### Modified Files
- `src/muse/db.py` — add `Idea` model, add `ForeignKey` import
- `src/muse/config.py` — add monthly schedule + notion sync settings
- `src/muse/scheduler.py` — add `generate_ideas_job`, `notion_sync_job`
- `src/muse/main.py` — register monthly + notion sync jobs, add `generate_ideas` and `notion_sync` to `run_job` CLI dispatch dict
- `src/muse/publisher/telegram.py` — add `send_monthly_ideas()`
- `src/muse/publisher/email.py` — add `send_monthly_ideas()`
- `src/muse/publisher/notion.py` — add `push_ideas()`, `pull_status_updates()`
- `tests/test_telegram.py` — add monthly test
- `tests/test_email.py` — add monthly test
- `tests/test_notion.py` — add push/pull tests
- `tests/test_integration.py` — add idea pipeline test
- `tests/conftest.py` — add monthly schedule env defaults
- `Dockerfile` — already copies templates/

## 10. Error Handling

- AI chunk failure → log, continue processing remaining chunks. `IdeaGenerationResult.failed=True` only if zero ideas were generated across all chunks. Job-level: if `generation.failed and not generation.ideas`, send alert and return. Partial success stores whatever was generated.
- Notion API failure → log, skip affected ideas, retry on next sync cycle
- Email failure → log, don't block core flow
- Telegram failure → log, don't block core flow
- Empty opportunities → skip AI call, log, return early
