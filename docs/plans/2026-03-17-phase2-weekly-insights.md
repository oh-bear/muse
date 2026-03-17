# Phase 2 — Weekly Insights Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Layer 2 opportunity extraction (weekly AI analysis of clustered signals), email weekly digest, Notion integration for future idea sync, and a weekly Telegram brief.

**Architecture:** A new `extract_opportunities` job runs weekly (Monday 10:00 UTC). It queries the past week's signals from PostgreSQL, sends them to AI for trend clustering / gap analysis / geo-arbitrage, stores resulting opportunities in a new `muse.opportunities` table, then pushes a weekly brief via Telegram and email. Notion SDK is integrated with a placeholder ready for Phase 3 idea sync.

**Tech Stack:** Existing stack + `aiosmtplib` (async SMTP), `jinja2` (email templates), `notion-client` (Notion SDK). New Alembic migration for `opportunities` table.

**Spec:** `docs/specs/2026-03-16-muse-design.md` — sections 4.2, 6, 3.2, 8

---

## File Map

| File | Responsibility |
|------|---------------|
| `src/muse/db.py` | Add `Opportunity` model |
| `alembic/versions/002_create_opportunities.py` | Migration for opportunities table |
| `src/muse/config.py` | Add email + Notion settings |
| `.env.example` | Add email + Notion env vars |
| `src/muse/analyzer/opportunity.py` | Layer 2: opportunity extraction logic |
| `src/muse/analyzer/prompts/opportunity_extraction_system.txt` | System prompt for Layer 2 |
| `src/muse/analyzer/prompts/opportunity_extraction_user.txt` | User prompt for Layer 2 |
| `src/muse/publisher/email.py` | Email sender with HTML template |
| `src/muse/publisher/notion.py` | Notion client (prep for Phase 3) |
| `src/muse/publisher/telegram.py` | Add `send_weekly_brief()` method |
| `templates/weekly_digest.html` | Jinja2 email template |
| `src/muse/scheduler.py` | Add `extract_opportunities_job()` |
| `src/muse/main.py` | Register new job in scheduler + CLI |
| `tests/conftest.py` | Add email + Notion env defaults |
| `tests/test_opportunity.py` | Opportunity extraction tests |
| `tests/test_email.py` | Email publisher tests |
| `tests/test_notion.py` | Notion client tests |
| `tests/test_telegram.py` | Add weekly brief test |
| `tests/test_scheduler_opportunities.py` | Opportunity job orchestration test |

---

## Chunk 1: Database & Config Extensions

### Task 1: Add Opportunity model and migration

**Files:**
- Modify: `src/muse/db.py`
- Create: `alembic/versions/002_create_opportunities.py` (auto-generated)

- [ ] **Step 1: Add Opportunity model to db.py**

Add after the `State` class in `src/muse/db.py`:

```python
class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = {"schema": "muse"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    trend_category: Mapped[str] = mapped_column(String(64))
    unmet_need: Mapped[str] = mapped_column(Text)
    market_gap: Mapped[str] = mapped_column(Text)
    geo_opportunity: Mapped[str] = mapped_column(Text, default="")
    signal_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    week_of: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
```

Also add `date` to the imports from `datetime` and `Date` to the imports from `sqlalchemy`:

```python
from datetime import date, datetime, timezone
```

```python
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    SmallInteger,
    String,
    Text,
    text,
)
```

- [ ] **Step 2: Generate Alembic migration**

```bash
cd /Users/uraurora/Files/moflow/github/muse
DATABASE_URL=postgresql://muse:muse_dev@localhost:5432/muse poetry run alembic revision --autogenerate -m "add opportunities table"
```

Note: Requires `docker compose up -d postgres` running. Verify the generated migration creates `muse.opportunities` with all columns and does NOT contain any spurious `op.drop_table` calls. If it does, remove them manually (same issue as Phase 1).

- [ ] **Step 3: Run migration**

```bash
DATABASE_URL=postgresql://muse:muse_dev@localhost:5432/muse poetry run alembic upgrade head
```

Expected: Migration applies cleanly, `muse.opportunities` table exists.

- [ ] **Step 4: Verify**

```bash
docker compose exec postgres psql -U muse -d muse -c "\dt muse.*"
```

Expected: `signals`, `state`, `opportunities` all listed.

- [ ] **Step 5: Commit**

```bash
git add src/muse/db.py alembic/versions/
git commit -m "feat: add Opportunity model and migration"
```

---

### Task 2: Extend config for email and Notion

**Files:**
- Modify: `src/muse/config.py`
- Modify: `.env.example`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add email and Notion settings to Settings class**

Add these fields to the `Settings` class in `src/muse/config.py`, after the `schedule_minute` field:

```python
    # Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_recipients: str = ""  # comma-separated

    # Notion
    notion_api_key: str = ""
    notion_ideas_database_id: str = ""

    # Weekly schedule (Monday)
    weekly_schedule_day: str = "mon"
    weekly_schedule_hour: int = 10
    weekly_schedule_minute: int = 0
```

- [ ] **Step 2: Update .env.example**

Add to `.env.example`:

```env

# Email
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
EMAIL_RECIPIENTS=user1@example.com,user2@example.com

# Notion
NOTION_API_KEY=
NOTION_IDEAS_DATABASE_ID=

# Weekly schedule
WEEKLY_SCHEDULE_DAY=mon
WEEKLY_SCHEDULE_HOUR=10
WEEKLY_SCHEDULE_MINUTE=0
```

- [ ] **Step 3: Update tests/conftest.py**

Add env defaults so tests don't require email/Notion config:

```python
os.environ.setdefault("SMTP_HOST", "")
os.environ.setdefault("SMTP_USER", "")
os.environ.setdefault("SMTP_PASSWORD", "")
os.environ.setdefault("EMAIL_RECIPIENTS", "")
os.environ.setdefault("NOTION_API_KEY", "")
os.environ.setdefault("NOTION_IDEAS_DATABASE_ID", "")
```

- [ ] **Step 4: Run existing tests to verify nothing breaks**

```bash
poetry run pytest tests/ --ignore=tests/test_integration.py -v
```

Expected: All 21 unit tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/muse/config.py .env.example tests/conftest.py
git commit -m "feat: add email and Notion config settings"
```

---

### Task 3: Add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add new dependencies**

```bash
cd /Users/uraurora/Files/moflow/github/muse
poetry add aiosmtplib jinja2 notion-client
```

- [ ] **Step 2: Verify install**

```bash
poetry run python -c "import aiosmtplib; import jinja2; import notion_client; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml poetry.lock
git commit -m "deps: add aiosmtplib, jinja2, notion-client"
```

---

## Chunk 2: Opportunity Extraction (Layer 2)

### Task 4: Opportunity extraction prompt templates

**Files:**
- Create: `src/muse/analyzer/prompts/opportunity_extraction_system.txt`
- Create: `src/muse/analyzer/prompts/opportunity_extraction_user.txt`

- [ ] **Step 1: Write system prompt template**

`src/muse/analyzer/prompts/opportunity_extraction_system.txt`:

Uses `string.Template` syntax (`$variable`) to avoid brace conflicts with JSON examples.

```
You are a product strategist analyzing weekly product signals to identify actionable opportunities for indie developers and small teams (max $max_team_size people).

## Your Task

Analyze the signals provided and extract 3-5 concrete opportunities. Each opportunity should synthesize multiple signals into an actionable insight.

## Analysis Framework

1. **Trend Clustering** — Group signals by theme. What patterns emerge?
2. **Complaint Mining** — What are users unhappy about in these products/spaces?
3. **Gap Analysis** — What's missing? What's done poorly that a small team could do better?
4. **Geo/Language Arbitrage** — Is something successful in one market but missing in another (e.g., EN→CN, US→SEA)?

## Focus Areas
$focus_areas

## Output Format

Respond with valid JSON only. No markdown, no explanation outside the JSON.

{
  "opportunities": [
    {
      "title": "<concise opportunity name>",
      "description": "<2-3 sentences: what this opportunity is>",
      "trend_category": "<e.g. ai-automation, creator-economy, developer-tools>",
      "unmet_need": "<what problem is not solved well>",
      "market_gap": "<what's missing in current solutions>",
      "geo_opportunity": "<regional/language arbitrage potential, or empty string if none>",
      "evidence_ids": ["<signal_id string from input>", "..."],
      "confidence": "<high|medium|low>"
    }
  ],
  "weekly_summary": "<2-3 sentence overview of the week's trends>"
}
```

- [ ] **Step 2: Write user prompt template**

`src/muse/analyzer/prompts/opportunity_extraction_user.txt`:

```
Analyze these signals from the past week and extract opportunities:

$signals
```

- [ ] **Step 3: Commit**

```bash
git add src/muse/analyzer/prompts/opportunity_extraction_system.txt src/muse/analyzer/prompts/opportunity_extraction_user.txt
git commit -m "feat: add opportunity extraction prompt templates"
```

---

### Task 5: Opportunity extraction pipeline

**Files:**
- Create: `src/muse/analyzer/opportunity.py`
- Create: `tests/test_opportunity.py`

- [ ] **Step 1: Write tests for opportunity extraction**

`tests/test_opportunity.py`:

```python
import pytest
from unittest.mock import AsyncMock

from muse.analyzer.opportunity import OpportunityExtractor, ExtractionResult


def _signal(sid: int, title: str, score: int = 4, tags: list[str] | None = None) -> dict:
    return {
        "id": f"uuid-{sid}",
        "title": title,
        "ai_summary": f"Summary of {title}",
        "ai_tags": tags or ["ai-tool"],
        "ai_score": score,
        "source": "producthunt",
    }


@pytest.fixture
def extractor(tmp_path):
    sys_prompt = tmp_path / "system.txt"
    sys_prompt.write_text("Analyze signals. Focus: $focus_areas. Team: $max_team_size")
    user_prompt = tmp_path / "user.txt"
    user_prompt.write_text("Signals:\n$signals")

    mock_client = AsyncMock()
    return OpportunityExtractor(
        ai_client=mock_client,
        system_prompt_path=str(sys_prompt),
        user_prompt_path=str(user_prompt),
        focus_areas=["ai-tools", "developer-tools"],
        indie_criteria={"max_team_size": 5},
    )


@pytest.mark.asyncio
async def test_extract_returns_opportunities(extractor):
    ai_response = {
        "opportunities": [
            {
                "title": "AI Code Review Gap",
                "description": "Multiple signals show demand",
                "trend_category": "developer-tools",
                "unmet_need": "Automated logic review",
                "market_gap": "No indie solution exists",
                "geo_opportunity": "",
                "evidence_ids": [1, 2],
                "confidence": "high",
            },
        ],
        "weekly_summary": "AI tools dominated this week.",
    }
    extractor.ai_client.call.return_value = (ai_response, {"input_tokens": 500, "output_tokens": 200})

    signals = [_signal(1, "AI Editor"), _signal(2, "Code Review Bot")]
    result = await extractor.extract(signals)

    assert len(result.opportunities) == 1
    assert result.opportunities[0]["title"] == "AI Code Review Gap"
    assert result.weekly_summary == "AI tools dominated this week."


@pytest.mark.asyncio
async def test_extract_chunks_large_signal_sets(extractor):
    extractor.max_signals_per_call = 2

    extractor.ai_client.call.side_effect = [
        ({"opportunities": [
            {"title": "Opp 1", "description": "d", "trend_category": "ai",
             "unmet_need": "n", "market_gap": "g", "geo_opportunity": "",
             "evidence_ids": [1, 2], "confidence": "high"},
        ], "weekly_summary": "Summary 1."}, {"input_tokens": 100, "output_tokens": 50}),
        ({"opportunities": [
            {"title": "Opp 2", "description": "d", "trend_category": "dev",
             "unmet_need": "n", "market_gap": "g", "geo_opportunity": "",
             "evidence_ids": [3], "confidence": "medium"},
        ], "weekly_summary": "Summary 2."}, {"input_tokens": 100, "output_tokens": 50}),
    ]

    signals = [_signal(i, f"Signal {i}") for i in range(1, 4)]
    result = await extractor.extract(signals)

    assert len(result.opportunities) == 2
    assert extractor.ai_client.call.call_count == 2


@pytest.mark.asyncio
async def test_extract_handles_ai_failure(extractor):
    from muse.analyzer.ai_client import AIRequestError
    extractor.ai_client.call.side_effect = AIRequestError("API down")

    signals = [_signal(1, "Test")]
    result = await extractor.extract(signals)

    assert len(result.opportunities) == 0
    assert result.failed
    assert "API down" in result.error


@pytest.mark.asyncio
async def test_extract_empty_signals(extractor):
    result = await extractor.extract([])

    assert len(result.opportunities) == 0
    assert not result.failed
    extractor.ai_client.call.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_opportunity.py -v
```

Expected: FAIL (module not found)

- [ ] **Step 3: Implement opportunity extractor**

`src/muse/analyzer/opportunity.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import Any

import structlog

from muse.analyzer.ai_client import AIClient, AIRequestError

logger = structlog.get_logger()


@dataclass
class ExtractionResult:
    opportunities: list[dict[str, Any]] = field(default_factory=list)
    weekly_summary: str = ""
    failed: bool = False
    error: str = ""


@dataclass
class OpportunityExtractor:
    ai_client: AIClient
    system_prompt_path: str
    user_prompt_path: str
    focus_areas: list[str]
    indie_criteria: dict[str, Any]
    max_signals_per_call: int = 40

    def _format_signals(self, signals: list[dict[str, Any]]) -> str:
        lines = []
        for s in signals:
            tags = ", ".join(s.get("ai_tags", []))
            lines.append(
                f"- Signal ID: {s['id']}\n"
                f"  Title: {s['title']}\n"
                f"  Summary: {s.get('ai_summary', '')}\n"
                f"  Score: {s.get('ai_score', 0)}/5\n"
                f"  Tags: {tags}\n"
                f"  Source: {s.get('source', 'unknown')}\n"
            )
        return "\n".join(lines)

    def _build_prompts(self, signals: list[dict[str, Any]]) -> tuple[str, str]:
        sys_template = Template(Path(self.system_prompt_path).read_text())
        user_template = Template(Path(self.user_prompt_path).read_text())

        system_prompt = sys_template.safe_substitute(
            focus_areas=", ".join(self.focus_areas),
            max_team_size=self.indie_criteria.get("max_team_size", 5),
        )
        user_prompt = user_template.safe_substitute(
            signals=self._format_signals(signals),
        )
        return system_prompt, user_prompt

    async def extract(self, signals: list[dict[str, Any]]) -> ExtractionResult:
        if not signals:
            return ExtractionResult()

        result = ExtractionResult()

        # Chunk signals if volume is high
        chunks = [signals[i:i + self.max_signals_per_call]
                  for i in range(0, len(signals), self.max_signals_per_call)]

        all_summaries = []

        for chunk_idx, chunk in enumerate(chunks):
            try:
                system_prompt, user_prompt = self._build_prompts(chunk)
                ai_result, usage = await self.ai_client.call(system_prompt, user_prompt)

                for opp in ai_result.get("opportunities", []):
                    result.opportunities.append(opp)

                summary = ai_result.get("weekly_summary", "")
                if summary:
                    all_summaries.append(summary)

                logger.info(
                    "opportunity_chunk_processed",
                    chunk=chunk_idx + 1,
                    total_chunks=len(chunks),
                    opportunities=len(ai_result.get("opportunities", [])),
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                )

            except AIRequestError as e:
                result.failed = True
                result.error = str(e)
                logger.error("opportunity_extraction_failed", chunk=chunk_idx + 1, error=str(e))

        result.weekly_summary = " ".join(all_summaries) if all_summaries else ""

        logger.info("opportunity_extraction_complete",
                    signals=len(signals), opportunities=len(result.opportunities))
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_opportunity.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/muse/analyzer/opportunity.py tests/test_opportunity.py
git commit -m "feat: add opportunity extraction pipeline with chunking"
```

---

## Chunk 3: Publishers (Email + Telegram Weekly + Notion)

### Task 6: Email publisher

**Files:**
- Create: `src/muse/publisher/email.py`
- Create: `templates/weekly_digest.html`
- Create: `tests/test_email.py`

- [ ] **Step 1: Write tests for email publisher**

`tests/test_email.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch

from muse.publisher.email import EmailPublisher


@pytest.fixture
def publisher():
    return EmailPublisher(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="bot@example.com",
        smtp_password="secret",
        recipients=["user1@example.com", "user2@example.com"],
    )


@pytest.mark.asyncio
async def test_send_weekly_digest(publisher):
    opportunities = [
        {
            "title": "AI Code Review Gap",
            "description": "Multiple signals show demand",
            "trend_category": "developer-tools",
            "unmet_need": "Automated logic review",
            "market_gap": "No indie solution",
            "geo_opportunity": "Missing in CN market",
            "confidence": "high",
        },
    ]

    with patch("muse.publisher.email.aiosmtplib") as mock_smtp:
        mock_smtp.send = AsyncMock()
        await publisher.send_weekly_digest(
            opportunities=opportunities,
            weekly_summary="AI tools dominated this week.",
            signal_count=42,
            week_label="2026-W12",
        )

        mock_smtp.send.assert_called_once()
        call_args = mock_smtp.send.call_args
        message = call_args[0][0]  # first positional arg is the message
        assert "AI Code Review Gap" in message.get_body(preferencelist=("html",)).get_content()
        assert len(message["To"].split(", ")) == 2


@pytest.mark.asyncio
async def test_send_skips_when_no_host(publisher):
    publisher.smtp_host = ""

    with patch("muse.publisher.email.aiosmtplib") as mock_smtp:
        mock_smtp.send = AsyncMock()
        await publisher.send_weekly_digest(
            opportunities=[],
            weekly_summary="",
            signal_count=0,
            week_label="2026-W12",
        )

        mock_smtp.send.assert_not_called()
```

- [ ] **Step 2: Create email HTML template**

`templates/weekly_digest.html`:

```html
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 640px; margin: 0 auto; padding: 20px; color: #333; }
  h1 { color: #1a1a2e; border-bottom: 2px solid #e94560; padding-bottom: 8px; }
  h2 { color: #0f3460; margin-top: 24px; }
  .meta { color: #666; font-size: 14px; margin-bottom: 20px; }
  .summary { background: #f8f9fa; padding: 16px; border-radius: 8px; margin-bottom: 24px; border-left: 4px solid #e94560; }
  .opportunity { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
  .opportunity h3 { margin: 0 0 8px 0; color: #1a1a2e; }
  .category { display: inline-block; background: #e94560; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
  .confidence { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
  .confidence-high { background: #d4edda; color: #155724; }
  .confidence-medium { background: #fff3cd; color: #856404; }
  .confidence-low { background: #f8d7da; color: #721c24; }
  .field { margin: 8px 0; }
  .field-label { font-weight: 600; color: #555; }
  .footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid #e0e0e0; color: #999; font-size: 12px; }
</style>
</head>
<body>
  <h1>🎯 Muse Weekly Insights</h1>
  <div class="meta">{{ week_label }} · {{ signal_count }} signals analyzed</div>

  {% if weekly_summary %}
  <div class="summary">
    <strong>This Week:</strong> {{ weekly_summary }}
  </div>
  {% endif %}

  <h2>Opportunities ({{ opportunities|length }})</h2>

  {% for opp in opportunities %}
  <div class="opportunity">
    <h3>{{ loop.index }}. {{ opp.title }}</h3>
    <span class="category">{{ opp.trend_category }}</span>
    <span class="confidence confidence-{{ opp.confidence }}">{{ opp.confidence }}</span>

    <div class="field">{{ opp.description }}</div>

    <div class="field">
      <span class="field-label">Unmet Need:</span> {{ opp.unmet_need }}
    </div>
    <div class="field">
      <span class="field-label">Market Gap:</span> {{ opp.market_gap }}
    </div>
    {% if opp.geo_opportunity %}
    <div class="field">
      <span class="field-label">Geo Opportunity:</span> {{ opp.geo_opportunity }}
    </div>
    {% endif %}
  </div>
  {% endfor %}

  {% if not opportunities %}
  <p>No significant opportunities identified this week.</p>
  {% endif %}

  <div class="footer">
    Generated by Muse · Product Inspiration Workflow
  </div>
</body>
</html>
```

- [ ] **Step 3: Update Dockerfile to copy templates**

Add this line to `Dockerfile` after `COPY config/ ./config/`:

```dockerfile
COPY templates/ ./templates/
```

- [ ] **Step 4: Implement email publisher**

`src/muse/publisher/email.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import aiosmtplib
import structlog
from jinja2 import Template

logger = structlog.get_logger()

TEMPLATE_DIR = Path(__file__).parent.parent.parent.parent / "templates"


@dataclass
class EmailPublisher:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    recipients: list[str]

    async def send_weekly_digest(
        self,
        opportunities: list[dict[str, Any]],
        weekly_summary: str,
        signal_count: int,
        week_label: str,
    ) -> None:
        if not self.smtp_host:
            logger.info("email_skipped", reason="no smtp_host configured")
            return

        template_path = TEMPLATE_DIR / "weekly_digest.html"
        template = Template(template_path.read_text())

        html = template.render(
            opportunities=opportunities,
            weekly_summary=weekly_summary,
            signal_count=signal_count,
            week_label=week_label,
        )

        msg = EmailMessage()
        msg["Subject"] = f"🎯 Muse Weekly Insights — {week_label}"
        msg["From"] = self.smtp_user
        msg["To"] = ", ".join(self.recipients)
        msg.set_content(f"Muse Weekly: {len(opportunities)} opportunities from {signal_count} signals.")
        msg.add_alternative(html, subtype="html")

        await aiosmtplib.send(
            msg,
            hostname=self.smtp_host,
            port=self.smtp_port,
            username=self.smtp_user,
            password=self.smtp_password,
            start_tls=True,
        )

        logger.info("email_weekly_sent", recipients=len(self.recipients), opportunities=len(opportunities))
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
poetry run pytest tests/test_email.py -v
```

Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add src/muse/publisher/email.py templates/weekly_digest.html tests/test_email.py Dockerfile
git commit -m "feat: add email publisher with weekly digest HTML template"
```

---

### Task 7: Telegram weekly brief

**Files:**
- Modify: `src/muse/publisher/telegram.py`
- Modify: `tests/test_telegram.py`

- [ ] **Step 1: Write test for weekly brief**

Add to `tests/test_telegram.py`:

```python
@pytest.mark.asyncio
async def test_send_weekly_brief(publisher, mock_bot):
    opportunities = [
        {
            "title": "AI Code Review Gap",
            "description": "Multiple signals show demand",
            "trend_category": "developer-tools",
            "unmet_need": "Automated logic review",
            "market_gap": "No indie solution",
            "confidence": "high",
        },
        {
            "title": "SEA SaaS Localization",
            "description": "EN tools missing in SEA",
            "trend_category": "saas",
            "unmet_need": "Local payment integration",
            "market_gap": "No localized version",
            "confidence": "medium",
        },
    ]

    await publisher.send_weekly_brief(
        opportunities=opportunities,
        weekly_summary="AI tools and localization dominated this week.",
        signal_count=35,
        week_label="2026-W12",
    )

    mock_bot.send_message.assert_called_once()
    message = mock_bot.send_message.call_args[1]["text"]
    assert "2026-W12" in message
    assert "AI Code Review Gap" in message
    assert "35" in message
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_telegram.py::test_send_weekly_brief -v
```

Expected: FAIL (method not found)

- [ ] **Step 3: Add send_weekly_brief to TelegramPublisher**

Add this method to the `TelegramPublisher` class in `src/muse/publisher/telegram.py`:

```python
    async def send_weekly_brief(
        self,
        opportunities: list[dict[str, Any]],
        weekly_summary: str,
        signal_count: int,
        week_label: str,
    ) -> None:
        lines = [
            "🎯 *Muse Weekly Insights*",
            f"_{week_label} · {signal_count} signals analyzed_",
        ]

        if weekly_summary:
            lines.append("")
            lines.append(weekly_summary)

        if opportunities:
            lines.append("")
            for i, opp in enumerate(opportunities, 1):
                conf = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(
                    opp.get("confidence", ""), "⚪"
                )
                lines.append(f"{i}\\. *{opp['title']}* {conf}")
                lines.append(f"   {opp.get('description', '')}")
                lines.append("")
        else:
            lines.append("")
            lines.append("No significant opportunities this week\\.")

        message = "\n".join(lines)
        await self._send(message)
        logger.info("telegram_weekly_sent", opportunities=len(opportunities))
```

- [ ] **Step 4: Run all telegram tests**

```bash
poetry run pytest tests/test_telegram.py -v
```

Expected: 4 passed (3 existing + 1 new)

- [ ] **Step 5: Commit**

```bash
git add src/muse/publisher/telegram.py tests/test_telegram.py
git commit -m "feat: add Telegram weekly brief message"
```

---

### Task 8: Notion client (Phase 3 prep)

**Files:**
- Create: `src/muse/publisher/notion.py`
- Create: `tests/test_notion.py`

- [ ] **Step 1: Write tests for Notion client**

`tests/test_notion.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from muse.publisher.notion import NotionPublisher


@pytest.fixture
def publisher():
    return NotionPublisher(
        api_key="ntn_test",
        ideas_database_id="db-123",
    )


def test_notion_skips_when_no_api_key():
    pub = NotionPublisher(api_key="", ideas_database_id="db-123")
    assert not pub.is_configured()


def test_notion_is_configured(publisher):
    assert publisher.is_configured()


@pytest.mark.asyncio
async def test_health_check(publisher):
    with patch("muse.publisher.notion.AsyncClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.databases.retrieve = AsyncMock(return_value={"id": "db-123", "title": [{"plain_text": "Ideas"}]})
        mock_cls.return_value = mock_client

        result = await publisher.health_check()
        assert result is True
        mock_client.databases.retrieve.assert_called_once_with(database_id="db-123")
```

- [ ] **Step 2: Implement Notion client**

`src/muse/publisher/notion.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class NotionPublisher:
    api_key: str
    ideas_database_id: str

    def is_configured(self) -> bool:
        return bool(self.api_key and self.ideas_database_id)

    async def health_check(self) -> bool:
        """Verify Notion API connectivity and database access."""
        if not self.is_configured():
            logger.info("notion_skipped", reason="not configured")
            return False

        from notion_client import AsyncClient

        client = AsyncClient(auth=self.api_key)
        try:
            db = await client.databases.retrieve(database_id=self.ideas_database_id)
            logger.info("notion_health_ok", database_id=self.ideas_database_id)
            return True
        except Exception as e:
            logger.error("notion_health_failed", error=str(e))
            return False
```

Note: Full idea sync (`create_idea_page`, `update_idea_page`) will be added in Phase 3. This task only sets up the client skeleton and health check.

- [ ] **Step 3: Run tests**

```bash
poetry run pytest tests/test_notion.py -v
```

Expected: 3 passed

- [ ] **Step 4: Commit**

```bash
git add src/muse/publisher/notion.py tests/test_notion.py
git commit -m "feat: add Notion client with health check (Phase 3 prep)"
```

---

## Chunk 4: Job Orchestration & Scheduler

### Task 9: Opportunity extraction job

**Files:**
- Modify: `src/muse/scheduler.py`
- Create: `tests/test_scheduler_opportunities.py`

- [ ] **Step 1: Write tests for the opportunity job**

`tests/test_scheduler_opportunities.py`:

```python
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from muse.config import FocusConfig, Settings
from muse.db import Signal, Opportunity


@pytest.fixture
def settings():
    return Settings(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        miniflux_url="http://localhost:8080",
        miniflux_api_key="test",
        ai_provider="claude",
        anthropic_api_key="sk-test",
        telegram_bot_token="123:abc",
        telegram_chat_id="-100test",
        smtp_host="smtp.test.com",
        smtp_port=587,
        smtp_user="bot@test.com",
        smtp_password="secret",
        email_recipients="user@test.com",
    )


@pytest.fixture
def focus():
    return FocusConfig(
        focus_areas=["ai-tools"],
        exclude=["crypto"],
        score_threshold=3,
        indie_criteria={"max_team_size": 5},
    )


@pytest.mark.asyncio
async def test_extract_opportunities_job_queries_week_signals(settings, focus):
    """Verify the job fetches signals from the past week and calls AI."""
    from muse.scheduler import extract_opportunities_job

    now = datetime.now(timezone.utc)
    mock_signal = MagicMock()
    mock_signal.id = uuid.uuid4()
    mock_signal.title = "AI Tool"
    mock_signal.ai_summary = "Summary"
    mock_signal.ai_tags = ["ai"]
    mock_signal.ai_score = 4
    mock_signal.source = "producthunt"

    # Mock session
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_signal]
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("muse.scheduler.OpportunityExtractor") as mock_extractor_cls, \
         patch("muse.scheduler.TelegramPublisher") as mock_tg_cls, \
         patch("muse.scheduler.EmailPublisher") as mock_email_cls:

        mock_extractor = AsyncMock()
        mock_extractor.extract.return_value = MagicMock(
            opportunities=[{
                "title": "Test Opp",
                "description": "desc",
                "trend_category": "ai",
                "unmet_need": "need",
                "market_gap": "gap",
                "geo_opportunity": "",
                "evidence_ids": [1],
                "confidence": "high",
            }],
            weekly_summary="Summary",
            failed=False,
        )
        mock_extractor_cls.return_value = mock_extractor

        mock_tg = AsyncMock()
        mock_tg_cls.return_value = mock_tg

        mock_email = AsyncMock()
        mock_email_cls.return_value = mock_email

        await extract_opportunities_job(settings, focus, mock_session_factory)

        # Verify AI was called
        mock_extractor.extract.assert_called_once()

        # Verify opportunity was stored
        mock_session.add.assert_called()

        # Verify push
        mock_tg.send_weekly_brief.assert_called_once()
        mock_email.send_weekly_digest.assert_called_once()
```

- [ ] **Step 2: Implement extract_opportunities_job**

Add these imports to the top of `src/muse/scheduler.py`:

```python
from datetime import timedelta

from muse.analyzer.opportunity import OpportunityExtractor
from muse.db import Opportunity, Signal, State
from muse.publisher.email import EmailPublisher
```

Add this function to `src/muse/scheduler.py` after `collect_signals_job`:

```python
async def extract_opportunities_job(settings: Settings, focus: FocusConfig, session_factory) -> None:
    """Weekly job: query week's signals → AI opportunity extraction → store → push."""
    job_id = str(uuid.uuid4())[:8]
    logger.info("job_started", job="extract_opportunities", job_id=job_id)

    telegram = TelegramPublisher(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )

    # 1. Query signals from the past 7 days
    one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    async with session_factory() as session:
        result = await session.execute(
            select(Signal).where(Signal.created_at >= one_week_ago)
        )
        db_signals = result.scalars().all()

    if not db_signals:
        logger.info("no_signals_for_opportunities", job_id=job_id)
        return

    # Convert to dicts for AI
    signals_data = [
        {
            "id": str(s.id),
            "title": s.title,
            "ai_summary": s.ai_summary,
            "ai_tags": s.ai_tags,
            "ai_score": s.ai_score,
            "source": s.source,
        }
        for s in db_signals
    ]

    # 2. Run opportunity extraction
    api_key = settings.anthropic_api_key if settings.ai_provider == "claude" else settings.openai_api_key
    ai_client = AIClient(provider=settings.ai_provider, api_key=api_key)
    extractor = OpportunityExtractor(
        ai_client=ai_client,
        system_prompt_path=str(PROMPTS_DIR / "opportunity_extraction_system.txt"),
        user_prompt_path=str(PROMPTS_DIR / "opportunity_extraction_user.txt"),
        focus_areas=focus.focus_areas,
        indie_criteria=focus.indie_criteria,
    )
    extraction = await extractor.extract(signals_data)

    if extraction.failed:
        await telegram.send_alert(f"Opportunity extraction failed: {extraction.error}")
        return

    # 3. Store opportunities
    today = datetime.now(timezone.utc).date()
    # Map evidence_ids back to signal UUIDs
    signal_id_map = {str(s.id): s.id for s in db_signals}

    async with session_factory() as session:
        for opp in extraction.opportunities:
            # Try to resolve evidence_ids to actual signal UUIDs
            evidence_uuids = []
            for eid in opp.get("evidence_ids", []):
                sid_str = str(eid)
                if sid_str in signal_id_map:
                    evidence_uuids.append(signal_id_map[sid_str])

            session.add(Opportunity(
                title=opp["title"],
                description=opp.get("description", ""),
                trend_category=opp.get("trend_category", ""),
                unmet_need=opp.get("unmet_need", ""),
                market_gap=opp.get("market_gap", ""),
                geo_opportunity=opp.get("geo_opportunity", ""),
                signal_ids=evidence_uuids,
                week_of=today,
            ))
        await session.commit()

    # 4. Calculate week label
    week_label = datetime.now(timezone.utc).strftime("%G-W%V")

    # 5. Push via Telegram
    try:
        await telegram.send_weekly_brief(
            opportunities=extraction.opportunities,
            weekly_summary=extraction.weekly_summary,
            signal_count=len(db_signals),
            week_label=week_label,
        )
    except Exception as e:
        logger.error("telegram_weekly_failed", error=str(e))

    # 6. Push via Email
    email = EmailPublisher(
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        smtp_user=settings.smtp_user,
        smtp_password=settings.smtp_password,
        recipients=[r.strip() for r in settings.email_recipients.split(",") if r.strip()],
    )
    try:
        await email.send_weekly_digest(
            opportunities=extraction.opportunities,
            weekly_summary=extraction.weekly_summary,
            signal_count=len(db_signals),
            week_label=week_label,
        )
    except Exception as e:
        logger.error("email_weekly_failed", error=str(e))

    logger.info("job_completed", job="extract_opportunities", job_id=job_id,
               signals=len(db_signals), opportunities=len(extraction.opportunities))
```

- [ ] **Step 3: Run tests**

```bash
poetry run pytest tests/test_scheduler_opportunities.py -v
```

Expected: 1 passed

- [ ] **Step 4: Commit**

```bash
git add src/muse/scheduler.py tests/test_scheduler_opportunities.py
git commit -m "feat: add weekly opportunity extraction job"
```

---

### Task 10: Register weekly job in main.py

**Files:**
- Modify: `src/muse/main.py`

- [ ] **Step 1: Update imports in main.py**

Add to the imports in `src/muse/main.py`:

```python
from muse.scheduler import collect_signals_job, extract_opportunities_job
```

- [ ] **Step 2: Add extract_opportunities to jobs dict**

Update the `jobs` dict in `run_job()`:

```python
    jobs = {
        "collect_signals": collect_signals_job,
        "extract_opportunities": extract_opportunities_job,
    }
```

- [ ] **Step 3: Add weekly cron job to scheduler**

Add after the existing `scheduler.add_job` call:

```python
    scheduler.add_job(
        extract_opportunities_job,
        "cron",
        day_of_week=settings.weekly_schedule_day,
        hour=settings.weekly_schedule_hour,
        minute=settings.weekly_schedule_minute,
        args=[settings, focus, session_factory],
        id="extract_opportunities",
        replace_existing=True,
        misfire_grace_time=7200,
    )
```

Update the scheduler log to include the new job:

```python
    logger.info("scheduler_started", timezone=settings.timezone,
               schedule=f"daily={settings.schedule_hour:02d}:{settings.schedule_minute:02d}, "
                       f"weekly={settings.weekly_schedule_day} {settings.weekly_schedule_hour:02d}:{settings.weekly_schedule_minute:02d}",
               jobs=["collect_signals", "extract_opportunities"])
```

- [ ] **Step 4: Run all tests**

```bash
poetry run pytest tests/ --ignore=tests/test_integration.py -v
```

Expected: All tests pass (existing 21 + new tests from this phase)

- [ ] **Step 5: Commit**

```bash
git add src/muse/main.py
git commit -m "feat: register weekly opportunity job in scheduler"
```

---

## Chunk 5: Integration Test & Deploy

### Task 11: Update integration test for opportunities

**Files:**
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Add opportunity job integration test**

Add this test to `tests/test_integration.py` (after the existing `test_full_pipeline`):

```python
@pytest.mark.asyncio
@respx.mock
async def test_opportunity_pipeline(settings, focus, db):
    """Signals → opportunity extraction → store → push."""
    _, _, session_factory = db

    # Seed some signals from the "past week"
    async with session_factory() as session:
        for i in range(1, 4):
            session.add(Signal(
                miniflux_entry_id=100 + i,
                title=f"AI Tool {i}",
                url=f"https://x.com/{i}",
                source="producthunt",
                raw_summary=f"Description {i}",
                ai_summary=f"AI tool summary {i}",
                ai_tags=["ai-tool"],
                ai_score=4,
                ai_reason="Strong signal",
            ))
        await session.commit()

    # Mock Claude API for opportunity extraction
    ai_result = json.dumps({
        "opportunities": [
            {
                "title": "AI Dev Tools Gap",
                "description": "3 signals show unmet need",
                "trend_category": "developer-tools",
                "unmet_need": "Logic review automation",
                "market_gap": "No indie solution",
                "geo_opportunity": "",
                "evidence_ids": [],
                "confidence": "high",
            }
        ],
        "weekly_summary": "AI dominated this week.",
    })
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json={
            "content": [{"type": "text", "text": ai_result}],
            "usage": {"input_tokens": 500, "output_tokens": 200},
        })
    )

    # Mock Telegram + Email
    bot_instance = AsyncMock()
    bot_instance.send_message = AsyncMock()
    bot_instance.__aenter__ = AsyncMock(return_value=bot_instance)
    bot_instance.__aexit__ = AsyncMock(return_value=False)

    from muse.scheduler import extract_opportunities_job

    with patch("muse.publisher.telegram.Bot", return_value=bot_instance), \
         patch("muse.publisher.email.aiosmtplib") as mock_smtp:
        mock_smtp.send = AsyncMock()
        await extract_opportunities_job(settings, focus, session_factory)

    # Verify: opportunity stored
    async with session_factory() as session:
        from muse.db import Opportunity
        opps = (await session.execute(select(Opportunity))).scalars().all()
        assert len(opps) == 1
        assert opps[0].title == "AI Dev Tools Gap"
        assert opps[0].trend_category == "developer-tools"
```

- [ ] **Step 2: Update the settings fixture**

Update the `settings` fixture in `tests/test_integration.py` to include email settings:

```python
@pytest.fixture
def settings(db):
    url, _, _ = db
    return Settings(
        database_url=url,
        miniflux_url="http://miniflux:8080",
        miniflux_api_key="test-key",
        ai_provider="claude",
        anthropic_api_key="sk-test",
        telegram_bot_token="123:abc",
        telegram_chat_id="-100test",
        smtp_host="smtp.test.com",
        smtp_port=587,
        smtp_user="bot@test.com",
        smtp_password="secret",
        email_recipients="user@test.com",
    )
```

- [ ] **Step 3: Run all tests**

```bash
poetry run pytest tests/ -v
```

Expected: All tests pass (including new integration test)

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add opportunity pipeline integration test"
```

---

### Task 12: Docker deployment verification

- [ ] **Step 1: Start services and run migration**

```bash
cd /Users/uraurora/Files/moflow/github/muse
docker compose up -d postgres
DATABASE_URL=postgresql://muse:muse_dev@localhost:5432/muse poetry run alembic upgrade head
```

Expected: Migration applies, `muse.opportunities` table exists.

- [ ] **Step 2: Verify table**

```bash
docker compose exec postgres psql -U muse -d muse -c "\dt muse.*"
```

Expected: `signals`, `state`, `opportunities` listed.

- [ ] **Step 3: Test CLI run**

```bash
DATABASE_URL=postgresql+asyncpg://muse:muse_dev@localhost:5432/muse poetry run python -m muse.main run extract_opportunities
```

Expected: Logs show "no_signals_for_opportunities" (since there are no signals yet), or processes correctly if signals exist.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: adjustments from Phase 2 deployment testing"
```

---

### Task 13: Push to GitHub

- [ ] **Step 1: Push branch**

```bash
git push origin feat/phase2-weekly-insights
```

- [ ] **Step 2: Create PR**

```bash
gh pr create --title "feat: Phase 2 — Weekly opportunity extraction + email digest" --body "$(cat <<'EOF'
## Summary

- Layer 2: AI opportunity extraction from weekly clustered signals
- Email weekly digest with HTML template (Jinja2 + aiosmtplib)
- Telegram weekly brief message
- Notion client skeleton with health check (Phase 3 prep)
- New `muse.opportunities` table + Alembic migration
- Weekly cron job (configurable day/hour/minute)

## Test plan

- [ ] All unit tests pass
- [ ] Integration test with testcontainers passes
- [ ] Alembic migration applies cleanly
- [ ] `python -m muse.main run extract_opportunities` executes without errors

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
