# Phase 3: Monthly Ideas with BMC Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Layer 3 to the Muse AI pipeline — monthly idea generation with lean BMC from accumulated opportunities, with optional bidirectional Notion sync.

**Architecture:** Monthly cron queries 30 days of opportunities → IdeaGenerator (same pattern as OpportunityExtractor) produces BMC ideas → stored in `muse.ideas` → pushed via Telegram + Email. Separate optional `notion_sync_job` runs every 6h to push new ideas to Notion and pull status updates back.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, APScheduler, structlog, httpx (AI calls), string.Template (prompts), jinja2 (email), notion-client (optional), aiosmtplib, python-telegram-bot

**Spec:** `docs/superpowers/specs/2026-03-17-phase3-monthly-ideas-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `src/muse/analyzer/idea.py` | IdeaGenerator + IdeaGenerationResult dataclasses |
| `src/muse/analyzer/prompts/idea_generation_system.txt` | System prompt for Layer 3 |
| `src/muse/analyzer/prompts/idea_generation_user.txt` | User prompt template with $opportunities |
| `templates/monthly_ideas.html` | Jinja2 email template for monthly ideas |
| `tests/test_idea_generator.py` | Unit tests for IdeaGenerator |
| `tests/test_scheduler_ideas.py` | Unit tests for generate_ideas_job |
| `tests/test_notion_sync.py` | Unit tests for notion_sync_job + push/pull |

### Modified Files
| File | Changes |
|------|---------|
| `src/muse/db.py` | Add `Idea` model, `ForeignKey` import, `VALID_IDEA_STATUSES` constant, `confidence` on Opportunity |
| `src/muse/config.py` | Add monthly schedule + notion sync settings |
| `src/muse/scheduler.py` | Add `generate_ideas_job`, `notion_sync_job`, imports for Idea/IdeaGenerator |
| `src/muse/main.py` | Register monthly + notion sync jobs, add to CLI dispatch |
| `src/muse/publisher/telegram.py` | Add `send_monthly_ideas()` method |
| `src/muse/publisher/email.py` | Add `send_monthly_ideas()` method |
| `src/muse/publisher/notion.py` | Add `push_ideas()`, `pull_status_updates()` methods |
| `tests/test_telegram.py` | Add `test_send_monthly_ideas` |
| `tests/test_email.py` | Add `test_send_monthly_ideas` |
| `tests/test_notion.py` | Add push/pull tests |
| `tests/test_integration.py` | Add `test_idea_pipeline` |
| `tests/conftest.py` | Add monthly schedule env defaults |

---

## Chunk 1: Data Model + Migration

### Task 1: Add `confidence` to Opportunity model + Idea model to db.py

**Files:**
- Modify: `src/muse/db.py`

- [ ] **Step 1: Add imports and models**

Open `src/muse/db.py` and add `ForeignKey` to the SQLAlchemy imports, then add `confidence` field to `Opportunity`, and add the full `Idea` model and `VALID_IDEA_STATUSES` constant.

```python
# Add ForeignKey to imports (line 7 area):
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    text,
)

# Add to Opportunity model (after geo_opportunity, before signal_ids):
    confidence: Mapped[str] = mapped_column(String(16), default="medium")

# Add constant after Opportunity class:
VALID_IDEA_STATUSES = {"pending", "promising", "validated", "abandoned"}

# Add Idea class after VALID_IDEA_STATUSES:
class Idea(Base):
    __tablename__ = "ideas"
    __table_args__ = {"schema": "muse"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
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
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
```

- [ ] **Step 2: Verify import works**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -c "from muse.db import Idea, VALID_IDEA_STATUSES; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/muse/db.py
git commit -m "feat: add Idea model and confidence to Opportunity"
```

### Task 2: Create Alembic migration

**Files:**
- Create: `alembic/versions/xxx_add_ideas_table_and_confidence.py`

- [ ] **Step 1: Generate migration**

Run: `cd /Users/uraurora/Files/moflow/github/muse && alembic revision --autogenerate -m "add ideas table and confidence column"`

- [ ] **Step 2: Clean up migration**

Open the generated file in `alembic/versions/`. Remove any spurious `op.drop_table` calls for Miniflux tables (icons, feeds, entries, users, etc.). The migration should only contain:

**upgrade():**
- `op.add_column('opportunities', sa.Column('confidence', sa.String(length=16), nullable=False, server_default='medium'), schema='muse')`
- `op.create_table('ideas', ..., schema='muse')` with all columns from the Idea model
- `op.create_index('idx_ideas_notion_page_id_null', 'ideas', ['id'], schema='muse', postgresql_where=sa.text('notion_page_id IS NULL'))`
- `op.create_index('idx_ideas_opportunity_id', 'ideas', ['opportunity_id'], schema='muse')`

**downgrade():**
- `op.drop_index('idx_ideas_opportunity_id', table_name='ideas', schema='muse')`
- `op.drop_index('idx_ideas_notion_page_id_null', table_name='ideas', schema='muse')`
- `op.drop_table('ideas', schema='muse')`
- `op.drop_column('opportunities', 'confidence', schema='muse')`

- [ ] **Step 3: Verify migration chain**

Run: `cd /Users/uraurora/Files/moflow/github/muse && alembic history`
Expected: Shows migration chain ending with the new `add_ideas_table_and_confidence` revision

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/
git commit -m "migration: add ideas table and confidence column to opportunities"
```

### Task 3: Update config with monthly schedule settings

**Files:**
- Modify: `src/muse/config.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add settings to config.py**

Add after the `weekly_schedule_minute` line in `Settings`:

```python
    # Monthly schedule (1st of month)
    monthly_schedule_day: int = 1
    monthly_schedule_hour: int = 10
    monthly_schedule_minute: int = 0

    # Notion sync interval (hours, 0 = disabled)
    notion_sync_interval_hours: int = 6
```

- [ ] **Step 2: Add env defaults to conftest.py**

Add to `tests/conftest.py`:

```python
os.environ.setdefault("MONTHLY_SCHEDULE_DAY", "1")
os.environ.setdefault("MONTHLY_SCHEDULE_HOUR", "10")
os.environ.setdefault("MONTHLY_SCHEDULE_MINUTE", "0")
os.environ.setdefault("NOTION_SYNC_INTERVAL_HOURS", "6")
```

- [ ] **Step 3: Verify config loads**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -c "from muse.config import Settings; s = Settings(); print(s.monthly_schedule_day, s.notion_sync_interval_hours)"`
Expected: `1 6`

- [ ] **Step 4: Commit**

```bash
git add src/muse/config.py tests/conftest.py
git commit -m "feat: add monthly schedule and notion sync config settings"
```

### Task 4: Update extract_opportunities_job to persist confidence

**Files:**
- Modify: `src/muse/scheduler.py:207`

- [ ] **Step 1: Add confidence to Opportunity creation**

In `src/muse/scheduler.py`, in the `extract_opportunities_job` function, update the `session.add(Opportunity(...))` call (around line 207) to include:

```python
                confidence=opp.get("confidence", "medium"),
```

Add it after the `geo_opportunity` line and before `signal_ids`.

- [ ] **Step 2: Run existing tests to verify no breakage**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -m pytest tests/test_scheduler_opportunities.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/muse/scheduler.py
git commit -m "feat: persist confidence field when storing opportunities"
```

---

## Chunk 2: IdeaGenerator + Prompts

### Task 5: Create AI prompt templates

**Files:**
- Create: `src/muse/analyzer/prompts/idea_generation_system.txt`
- Create: `src/muse/analyzer/prompts/idea_generation_user.txt`

- [ ] **Step 1: Write system prompt**

Create `src/muse/analyzer/prompts/idea_generation_system.txt`:

```
You are a product ideation expert helping indie developers and small teams (max $max_team_size people) turn market opportunities into concrete, buildable product ideas.

## Your Task

For each opportunity provided, generate 1-2 concrete product ideas with a lean Business Model Canvas. Ideas must be actionable — something a small team could start building this week.

## Evaluation Criteria

- **Buildable by a small team** — no enterprise-scale infrastructure requirements
- **Clear revenue path** — how does it make money within 6 months?
- **Differentiated** — what makes this better than existing solutions?
- **Validatable cheaply** — how to test demand with minimal investment?

## Focus Areas
$focus_areas

## Output Format

Respond with valid JSON only. No markdown, no explanation outside the JSON.

{
  "ideas": [
    {
      "title": "<product name>",
      "one_liner": "<what it does, for whom — one sentence>",
      "target_users": "<specific customer segment>",
      "pain_point": "<what pain it solves>",
      "differentiation": "<why this wins vs existing solutions>",
      "channels": ["<channel 1>", "<channel 2>"],
      "revenue_model": "<subscription|one-time|freemium|ads|marketplace>",
      "key_resources": "<what's needed to build and run>",
      "cost_estimate": "<rough cost structure>",
      "validation_method": "<cheapest way to test demand>",
      "difficulty": <1-5>,
      "source_opportunity_id": "<opportunity ID from input>"
    }
  ],
  "monthly_summary": "<2-3 sentence overview of this month's idea themes>"
}
```

- [ ] **Step 2: Write user prompt**

Create `src/muse/analyzer/prompts/idea_generation_user.txt`:

```
Here are the product opportunities identified this month. Generate 1-2 concrete product ideas for each opportunity.

## Opportunities

$opportunities
```

- [ ] **Step 3: Commit**

```bash
git add src/muse/analyzer/prompts/idea_generation_system.txt src/muse/analyzer/prompts/idea_generation_user.txt
git commit -m "feat: add Layer 3 idea generation prompt templates"
```

### Task 6: Write failing tests for IdeaGenerator

**Files:**
- Create: `tests/test_idea_generator.py`

- [ ] **Step 1: Write test file**

Create `tests/test_idea_generator.py`:

```python
import pytest
from unittest.mock import AsyncMock

from muse.analyzer.idea import IdeaGenerator, IdeaGenerationResult


def _opp(oid: int, title: str, confidence: str = "high") -> dict:
    return {
        "id": f"uuid-{oid}",
        "title": title,
        "description": f"Description of {title}",
        "trend_category": "developer-tools",
        "unmet_need": "Something missing",
        "market_gap": "No solution exists",
        "geo_opportunity": "",
        "confidence": confidence,
    }


@pytest.fixture
def generator(tmp_path):
    sys_prompt = tmp_path / "system.txt"
    sys_prompt.write_text("Generate ideas. Focus: $focus_areas. Team: $max_team_size")
    user_prompt = tmp_path / "user.txt"
    user_prompt.write_text("Opportunities:\n$opportunities")

    mock_client = AsyncMock()
    return IdeaGenerator(
        ai_client=mock_client,
        system_prompt_path=str(sys_prompt),
        user_prompt_path=str(user_prompt),
        focus_areas=["ai-tools", "developer-tools"],
        indie_criteria={"max_team_size": 5},
    )


@pytest.mark.asyncio
async def test_generate_returns_ideas(generator):
    ai_response = {
        "ideas": [
            {
                "title": "CodeReview.ai",
                "one_liner": "AI code review for PRs",
                "target_users": "Small dev teams",
                "pain_point": "Slow code review",
                "differentiation": "Logic errors, not style",
                "channels": ["GitHub Marketplace"],
                "revenue_model": "freemium",
                "key_resources": "AI expertise",
                "cost_estimate": "Low",
                "validation_method": "GitHub Action MVP",
                "difficulty": 3,
                "source_opportunity_id": "uuid-1",
            },
        ],
        "monthly_summary": "AI tools dominated.",
    }
    generator.ai_client.call.return_value = (ai_response, {"input_tokens": 500, "output_tokens": 300})

    opps = [_opp(1, "AI Code Review Gap")]
    result = await generator.generate(opps)

    assert len(result.ideas) == 1
    assert result.ideas[0]["title"] == "CodeReview.ai"
    assert result.monthly_summary == "AI tools dominated."
    assert not result.failed


@pytest.mark.asyncio
async def test_generate_chunks_large_sets(generator):
    generator.max_opportunities_per_call = 2

    generator.ai_client.call.side_effect = [
        ({"ideas": [
            {"title": "Idea 1", "one_liner": "o", "target_users": "t",
             "pain_point": "p", "differentiation": "d", "channels": [],
             "revenue_model": "freemium", "key_resources": "k",
             "cost_estimate": "c", "validation_method": "v", "difficulty": 3,
             "source_opportunity_id": "uuid-1"},
        ], "monthly_summary": "Summary 1."}, {"input_tokens": 100, "output_tokens": 50}),
        ({"ideas": [
            {"title": "Idea 2", "one_liner": "o", "target_users": "t",
             "pain_point": "p", "differentiation": "d", "channels": [],
             "revenue_model": "subscription", "key_resources": "k",
             "cost_estimate": "c", "validation_method": "v", "difficulty": 2,
             "source_opportunity_id": "uuid-3"},
        ], "monthly_summary": "Summary 2."}, {"input_tokens": 100, "output_tokens": 50}),
    ]

    opps = [_opp(i, f"Opp {i}") for i in range(1, 4)]
    result = await generator.generate(opps)

    assert len(result.ideas) == 2
    assert generator.ai_client.call.call_count == 2


@pytest.mark.asyncio
async def test_generate_handles_ai_failure(generator):
    from muse.analyzer.ai_client import AIRequestError
    generator.ai_client.call.side_effect = AIRequestError("API down")

    opps = [_opp(1, "Test")]
    result = await generator.generate(opps)

    assert len(result.ideas) == 0
    assert result.failed
    assert "API down" in result.error


@pytest.mark.asyncio
async def test_generate_partial_chunk_failure(generator):
    """When one chunk fails but another succeeds, partial results are collected."""
    from muse.analyzer.ai_client import AIRequestError

    generator.max_opportunities_per_call = 1

    generator.ai_client.call.side_effect = [
        ({"ideas": [
            {"title": "Surviving Idea", "one_liner": "o", "target_users": "t",
             "pain_point": "p", "differentiation": "d", "channels": [],
             "revenue_model": "freemium", "key_resources": "k",
             "cost_estimate": "c", "validation_method": "v", "difficulty": 3,
             "source_opportunity_id": "uuid-1"},
        ], "monthly_summary": "Partial."}, {"input_tokens": 100, "output_tokens": 50}),
        AIRequestError("Chunk 2 failed"),
    ]

    opps = [_opp(1, "Opp 1"), _opp(2, "Opp 2")]
    result = await generator.generate(opps)

    assert len(result.ideas) == 1
    assert result.ideas[0]["title"] == "Surviving Idea"
    assert result.failed  # marked failed due to chunk 2
    assert result.monthly_summary == "Partial."


@pytest.mark.asyncio
async def test_generate_empty_opportunities(generator):
    result = await generator.generate([])

    assert len(result.ideas) == 0
    assert not result.failed
    generator.ai_client.call.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -m pytest tests/test_idea_generator.py -v`
Expected: FAIL (ImportError — `muse.analyzer.idea` doesn't exist yet)

### Task 7: Implement IdeaGenerator (5 tests)

**Files:**
- Create: `src/muse/analyzer/idea.py`

- [ ] **Step 1: Write implementation**

Create `src/muse/analyzer/idea.py`:

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

    def _build_prompts(self, opportunities: list[dict[str, Any]]) -> tuple[str, str]:
        sys_template = Template(Path(self.system_prompt_path).read_text())
        user_template = Template(Path(self.user_prompt_path).read_text())

        system_prompt = sys_template.safe_substitute(
            focus_areas=", ".join(self.focus_areas),
            max_team_size=self.indie_criteria.get("max_team_size", 5),
        )
        user_prompt = user_template.safe_substitute(
            opportunities=self._format_opportunities(opportunities),
        )
        return system_prompt, user_prompt

    async def generate(self, opportunities: list[dict[str, Any]]) -> IdeaGenerationResult:
        if not opportunities:
            return IdeaGenerationResult()

        result = IdeaGenerationResult()

        chunks = [opportunities[i:i + self.max_opportunities_per_call]
                  for i in range(0, len(opportunities), self.max_opportunities_per_call)]

        all_summaries = []

        for chunk_idx, chunk in enumerate(chunks):
            try:
                system_prompt, user_prompt = self._build_prompts(chunk)
                ai_result, usage = await self.ai_client.call(system_prompt, user_prompt)

                for idea in ai_result.get("ideas", []):
                    result.ideas.append(idea)

                summary = ai_result.get("monthly_summary", "")
                if summary:
                    all_summaries.append(summary)

                logger.info(
                    "idea_chunk_processed",
                    chunk=chunk_idx + 1,
                    total_chunks=len(chunks),
                    ideas=len(ai_result.get("ideas", [])),
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                )

            except AIRequestError as e:
                result.failed = True
                result.error = str(e)
                logger.error("idea_generation_failed", chunk=chunk_idx + 1, error=str(e))

        result.monthly_summary = " ".join(all_summaries) if all_summaries else ""

        logger.info("idea_generation_complete",
                    opportunities=len(opportunities), ideas=len(result.ideas))
        return result
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -m pytest tests/test_idea_generator.py -v`
Expected: 5 passed

- [ ] **Step 3: Commit**

```bash
git add src/muse/analyzer/idea.py tests/test_idea_generator.py
git commit -m "feat: add IdeaGenerator for Layer 3 idea generation"
```

---

## Chunk 3: Publishers (Telegram + Email)

### Task 8: Write failing test for Telegram monthly ideas

**Files:**
- Modify: `tests/test_telegram.py`

- [ ] **Step 1: Add test**

Add to `tests/test_telegram.py`:

```python
@pytest.mark.asyncio
async def test_send_monthly_ideas(publisher, mock_bot):
    ideas = [
        {"title": "CodeReview.ai", "one_liner": "AI code review", "revenue_model": "freemium", "difficulty": 3},
        {"title": "LocalPay SEA", "one_liner": "Payment integration", "revenue_model": "marketplace", "difficulty": 4},
    ]

    await publisher.send_monthly_ideas(
        ideas=ideas,
        monthly_summary="AI tools dominated this month.",
        opportunity_count=5,
        month_label="2026-03",
    )

    mock_bot.send_message.assert_called_once()
    message = mock_bot.send_message.call_args[1]["text"]
    assert "2026-03" in message
    assert "CodeReview.ai" in message
    assert "5" in message
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -m pytest tests/test_telegram.py::test_send_monthly_ideas -v`
Expected: FAIL (AttributeError — no `send_monthly_ideas`)

### Task 9: Implement send_monthly_ideas on TelegramPublisher

**Files:**
- Modify: `src/muse/publisher/telegram.py`

- [ ] **Step 1: Add method**

Add to `TelegramPublisher` (before `send_alert`):

```python
    async def send_monthly_ideas(
        self,
        ideas: list[dict[str, Any]],
        monthly_summary: str,
        opportunity_count: int,
        month_label: str,
    ) -> None:
        lines = [
            "💡 *Muse Monthly Ideas*",
            f"_{month_label} · {opportunity_count} opportunities → {len(ideas)} ideas_",
        ]

        if monthly_summary:
            lines.append("")
            lines.append(monthly_summary)

        if ideas:
            lines.append("")
            for i, idea in enumerate(ideas, 1):
                diff = idea.get("difficulty", 3)
                stars = "⭐" * diff
                lines.append(f"{i}\\. *{idea['title']}* {stars}")
                lines.append(f"   {idea.get('one_liner', '')}")
                lines.append(f"   Revenue: {idea.get('revenue_model', '')} | Difficulty: {diff}/5")
                lines.append("")
        else:
            lines.append("")
            lines.append("No ideas generated this month\\.")

        message = "\n".join(lines)
        await self._send(message)
        logger.info("telegram_monthly_sent", ideas=len(ideas))
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -m pytest tests/test_telegram.py -v`
Expected: 5 passed (4 existing + 1 new)

- [ ] **Step 3: Commit**

```bash
git add src/muse/publisher/telegram.py tests/test_telegram.py
git commit -m "feat: add send_monthly_ideas to TelegramPublisher"
```

### Task 10: Write failing test for Email monthly ideas

**Files:**
- Modify: `tests/test_email.py`

- [ ] **Step 1: Add test**

Add to `tests/test_email.py`:

```python
@pytest.mark.asyncio
async def test_send_monthly_ideas(publisher):
    ideas = [
        {
            "title": "CodeReview.ai",
            "one_liner": "AI code review for PRs",
            "target_users": "Small dev teams",
            "pain_point": "Slow reviews",
            "differentiation": "Logic, not style",
            "channels": ["GitHub Marketplace"],
            "revenue_model": "freemium",
            "key_resources": "AI expertise",
            "cost_estimate": "Low",
            "validation_method": "GitHub Action MVP",
            "difficulty": 3,
        },
    ]

    with patch("muse.publisher.email.aiosmtplib") as mock_smtp:
        mock_smtp.send = AsyncMock()
        await publisher.send_monthly_ideas(
            ideas=ideas,
            monthly_summary="AI tools dominated.",
            opportunity_count=5,
            month_label="2026-03",
        )

        mock_smtp.send.assert_called_once()
        call_args = mock_smtp.send.call_args
        message = call_args[0][0]
        html = message.get_body(preferencelist=("html",)).get_content()
        assert "CodeReview.ai" in html
        assert "2026-03" in message["Subject"]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -m pytest tests/test_email.py::test_send_monthly_ideas -v`
Expected: FAIL (AttributeError — no `send_monthly_ideas`)

### Task 11: Create monthly email template + implement send_monthly_ideas

**Files:**
- Create: `templates/monthly_ideas.html`
- Modify: `src/muse/publisher/email.py`

- [ ] **Step 1: Create email template**

Create `templates/monthly_ideas.html`:

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
  .idea { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
  .idea h3 { margin: 0 0 4px 0; color: #1a1a2e; }
  .one-liner { color: #555; font-style: italic; margin-bottom: 12px; }
  .bmc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .bmc-field { margin: 4px 0; }
  .bmc-label { font-weight: 600; color: #555; font-size: 13px; }
  .difficulty { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; background: #e8eaf6; color: #283593; }
  .revenue { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; background: #e8f5e9; color: #2e7d32; }
  .footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid #e0e0e0; color: #999; font-size: 12px; }
</style>
</head>
<body>
  <h1>Muse Monthly Ideas</h1>
  <div class="meta">{{ month_label }} · {{ opportunity_count }} opportunities → {{ ideas|length }} ideas</div>

  {% if monthly_summary %}
  <div class="summary">
    <strong>This Month:</strong> {{ monthly_summary }}
  </div>
  {% endif %}

  <h2>Product Ideas ({{ ideas|length }})</h2>

  {% for idea in ideas %}
  <div class="idea">
    <h3>{{ loop.index }}. {{ idea.title }}</h3>
    <div class="one-liner">{{ idea.one_liner }}</div>
    <span class="revenue">{{ idea.revenue_model }}</span>
    <span class="difficulty">Difficulty: {{ idea.difficulty }}/5</span>

    <div class="bmc-grid" style="margin-top: 12px;">
      <div class="bmc-field">
        <div class="bmc-label">Target Users</div>
        {{ idea.target_users }}
      </div>
      <div class="bmc-field">
        <div class="bmc-label">Pain Point</div>
        {{ idea.pain_point }}
      </div>
      <div class="bmc-field">
        <div class="bmc-label">Differentiation</div>
        {{ idea.differentiation }}
      </div>
      <div class="bmc-field">
        <div class="bmc-label">Channels</div>
        {{ idea.channels | join(', ') if idea.channels else 'TBD' }}
      </div>
      <div class="bmc-field">
        <div class="bmc-label">Key Resources</div>
        {{ idea.key_resources }}
      </div>
      <div class="bmc-field">
        <div class="bmc-label">Cost Estimate</div>
        {{ idea.cost_estimate }}
      </div>
    </div>

    <div class="bmc-field" style="margin-top: 8px;">
      <div class="bmc-label">Validation Method</div>
      {{ idea.validation_method }}
    </div>
  </div>
  {% endfor %}

  {% if not ideas %}
  <p>No ideas generated this month.</p>
  {% endif %}

  <div class="footer">
    Generated by Muse · Product Inspiration Workflow
  </div>
</body>
</html>
```

- [ ] **Step 2: Add send_monthly_ideas to EmailPublisher**

Add to `src/muse/publisher/email.py` after `send_weekly_digest`:

```python
    async def send_monthly_ideas(
        self,
        ideas: list[dict[str, Any]],
        monthly_summary: str,
        opportunity_count: int,
        month_label: str,
    ) -> None:
        if not self.smtp_host:
            logger.info("email_skipped", reason="no smtp_host configured")
            return

        template_path = TEMPLATE_DIR / "monthly_ideas.html"
        template = Template(template_path.read_text())

        html = template.render(
            ideas=ideas,
            monthly_summary=monthly_summary,
            opportunity_count=opportunity_count,
            month_label=month_label,
        )

        msg = EmailMessage()
        msg["Subject"] = f"Muse Monthly Ideas — {month_label}"
        msg["From"] = self.smtp_user
        msg["To"] = ", ".join(self.recipients)
        msg.set_content(f"Muse Monthly: {len(ideas)} ideas from {opportunity_count} opportunities.")
        msg.add_alternative(html, subtype="html")

        await aiosmtplib.send(
            msg,
            hostname=self.smtp_host,
            port=self.smtp_port,
            username=self.smtp_user,
            password=self.smtp_password,
            start_tls=True,
        )

        logger.info("email_monthly_sent", recipients=len(self.recipients), ideas=len(ideas))
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -m pytest tests/test_email.py -v`
Expected: 3 passed (2 existing + 1 new)

- [ ] **Step 4: Commit**

```bash
git add templates/monthly_ideas.html src/muse/publisher/email.py tests/test_email.py
git commit -m "feat: add send_monthly_ideas to EmailPublisher with template"
```

---

## Chunk 4: Scheduler Jobs + Main

### Task 12: Write failing test for generate_ideas_job

**Files:**
- Create: `tests/test_scheduler_ideas.py`

- [ ] **Step 1: Write test file**

Create `tests/test_scheduler_ideas.py`:

```python
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from muse.config import FocusConfig, Settings


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
async def test_generate_ideas_job_full_flow(settings, focus):
    """Verify the job fetches opportunities, calls AI, stores ideas, and pushes."""
    from muse.scheduler import generate_ideas_job

    mock_opp = MagicMock()
    mock_opp.id = uuid.uuid4()
    mock_opp.title = "AI Code Review Gap"
    mock_opp.description = "Multiple signals"
    mock_opp.trend_category = "developer-tools"
    mock_opp.unmet_need = "Logic review"
    mock_opp.market_gap = "No indie solution"
    mock_opp.geo_opportunity = ""
    mock_opp.confidence = "high"
    mock_opp.created_at = datetime.now(timezone.utc)

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_opp]
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("muse.scheduler.IdeaGenerator") as mock_gen_cls, \
         patch("muse.scheduler.TelegramPublisher") as mock_tg_cls, \
         patch("muse.scheduler.EmailPublisher") as mock_email_cls:

        mock_gen = AsyncMock()
        mock_gen.generate.return_value = MagicMock(
            ideas=[{
                "title": "CodeReview.ai",
                "one_liner": "AI code review",
                "target_users": "Dev teams",
                "pain_point": "Slow review",
                "differentiation": "Logic focus",
                "channels": ["GitHub"],
                "revenue_model": "freemium",
                "key_resources": "AI",
                "cost_estimate": "Low",
                "validation_method": "MVP",
                "difficulty": 3,
                "source_opportunity_id": str(mock_opp.id),
            }],
            monthly_summary="AI dominated.",
            failed=False,
        )
        mock_gen_cls.return_value = mock_gen

        mock_tg = AsyncMock()
        mock_tg_cls.return_value = mock_tg

        mock_email = AsyncMock()
        mock_email_cls.return_value = mock_email

        await generate_ideas_job(settings, focus, mock_session_factory)

        mock_gen.generate.assert_called_once()
        mock_session.add.assert_called()
        mock_tg.send_monthly_ideas.assert_called_once()
        mock_email.send_monthly_ideas.assert_called_once()
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -m pytest tests/test_scheduler_ideas.py -v`
Expected: FAIL (ImportError — `generate_ideas_job` doesn't exist)

### Task 13: Implement generate_ideas_job

**Files:**
- Modify: `src/muse/scheduler.py`

- [ ] **Step 1: Add imports**

Add to the imports in `src/muse/scheduler.py`:

```python
from muse.analyzer.idea import IdeaGenerator
from muse.db import Idea, Opportunity, Signal, State
```

Update the existing `from muse.db import Opportunity, Signal, State` to include `Idea`.

- [ ] **Step 2: Add generate_ideas_job function**

Add after `extract_opportunities_job` in `src/muse/scheduler.py`:

```python
async def generate_ideas_job(settings: Settings, focus: FocusConfig, session_factory) -> None:
    """Monthly job: query month's opportunities → AI idea generation → store → push."""
    job_id = str(uuid.uuid4())[:8]
    logger.info("job_started", job="generate_ideas", job_id=job_id)

    telegram = TelegramPublisher(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )

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
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        smtp_user=settings.smtp_user,
        smtp_password=settings.smtp_password,
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

- [ ] **Step 3: Run tests**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -m pytest tests/test_scheduler_ideas.py tests/test_scheduler_opportunities.py -v`
Expected: ALL passed

- [ ] **Step 4: Commit**

```bash
git add src/muse/scheduler.py tests/test_scheduler_ideas.py
git commit -m "feat: add generate_ideas_job for monthly idea generation"
```

### Task 14: Update main.py with job registration + CLI dispatch

**Files:**
- Modify: `src/muse/main.py`

- [ ] **Step 1: Add imports and update jobs dict**

In `src/muse/main.py`, update the import to include `generate_ideas_job` and `notion_sync_job`:

```python
from muse.scheduler import collect_signals_job, extract_opportunities_job, generate_ideas_job, notion_sync_job
```

Update `run_job` to include new jobs:

```python
    jobs = {
        "collect_signals": collect_signals_job,
        "extract_opportunities": extract_opportunities_job,
        "generate_ideas": generate_ideas_job,
    }
```

Note: `notion_sync_job` has a different signature (no `focus`), so add special handling:

```python
    if job_name == "notion_sync":
        await notion_sync_job(settings, session_factory)
        return
```

Add this before the `if job_name not in jobs` check.

- [ ] **Step 2: Register monthly job**

Add after the `extract_opportunities` scheduler.add_job block:

```python
    scheduler.add_job(
        generate_ideas_job,
        "cron",
        day=settings.monthly_schedule_day,
        hour=settings.monthly_schedule_hour,
        minute=settings.monthly_schedule_minute,
        args=[settings, focus, session_factory],
        id="generate_ideas",
        replace_existing=True,
        misfire_grace_time=7200,
    )

    # Notion sync (only if configured)
    if settings.notion_api_key and settings.notion_ideas_database_id:
        scheduler.add_job(
            notion_sync_job,
            "interval",
            hours=settings.notion_sync_interval_hours,
            args=[settings, session_factory],
            id="notion_sync",
            replace_existing=True,
        )
```

- [ ] **Step 3: Update logger.info to include new jobs**

Update the `scheduler_started` log line to include new jobs in the schedule and jobs list.

- [ ] **Step 4: Verify import works**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -c "from muse.main import main; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/muse/main.py
git commit -m "feat: register generate_ideas and notion_sync jobs in main"
```

---

## Chunk 5: Notion Publisher

### Task 15: Write failing tests for Notion push/pull

**Files:**
- Modify: `tests/test_notion.py`

- [ ] **Step 1: Add push and pull tests**

Add to `tests/test_notion.py`:

```python
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_push_ideas(publisher):
    mock_idea_1 = MagicMock()
    mock_idea_1.id = MagicMock()
    mock_idea_1.title = "CodeReview.ai"
    mock_idea_1.one_liner = "AI code review"
    mock_idea_1.target_users = "Dev teams"
    mock_idea_1.pain_point = "Slow review"
    mock_idea_1.differentiation = "Logic focus"
    mock_idea_1.channels = ["GitHub"]
    mock_idea_1.revenue_model = "freemium"
    mock_idea_1.key_resources = "AI expertise"
    mock_idea_1.cost_estimate = "Low"
    mock_idea_1.validation_method = "MVP"
    mock_idea_1.difficulty = 3
    mock_idea_1.status = "pending"
    mock_idea_1.created_at = datetime.now(timezone.utc)

    with patch("notion_client.AsyncClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.pages.create = AsyncMock(return_value={"id": "notion-page-123"})
        mock_cls.return_value = mock_client

        result = await publisher.push_ideas([mock_idea_1])
        assert len(result) == 1
        assert result[0][1] == "notion-page-123"
        mock_client.pages.create.assert_called_once()


@pytest.mark.asyncio
async def test_pull_status_updates(publisher):
    with patch("notion_client.AsyncClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.databases.query = AsyncMock(return_value={
            "results": [
                {
                    "id": "notion-page-123",
                    "properties": {
                        "Status": {"select": {"name": "promising"}},
                    },
                    "last_edited_time": "2026-03-17T12:00:00.000Z",
                },
            ],
            "has_more": False,
        })
        mock_cls.return_value = mock_client

        updates = await publisher.pull_status_updates()
        assert len(updates) == 1
        assert updates[0][0] == "notion-page-123"
        assert updates[0][1] == "promising"


@pytest.mark.asyncio
async def test_push_ideas_skips_when_unconfigured():
    pub = NotionPublisher(api_key="", ideas_database_id="db-123")
    result = await pub.push_ideas([])
    assert result == []
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -m pytest tests/test_notion.py -v`
Expected: FAIL (AttributeError — no `push_ideas`)

### Task 16: Implement push_ideas and pull_status_updates

**Files:**
- Modify: `src/muse/publisher/notion.py`

- [ ] **Step 1: Rewrite notion.py with full implementation**

Replace the content of `src/muse/publisher/notion.py`:

```python
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
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
            await client.databases.retrieve(database_id=self.ideas_database_id)
            logger.info("notion_health_ok", database_id=self.ideas_database_id)
            return True
        except Exception as e:
            logger.error("notion_health_failed", error=str(e))
            return False

    async def push_ideas(self, ideas: list[Any]) -> list[tuple[uuid.UUID, str]]:
        """Create Notion pages for ideas. Returns list of (idea_id, notion_page_id)."""
        if not self.is_configured() or not ideas:
            return []

        from notion_client import AsyncClient

        client = AsyncClient(auth=self.api_key)
        results = []

        for idea in ideas:
            try:
                properties = self._build_properties(idea)
                page = await client.pages.create(
                    parent={"database_id": self.ideas_database_id},
                    properties=properties,
                )
                results.append((idea.id, page["id"]))
                logger.info("notion_page_created", idea_title=idea.title, page_id=page["id"])
            except Exception as e:
                logger.error("notion_push_failed", idea_title=idea.title, error=str(e))

        return results

    async def pull_status_updates(self) -> list[tuple[str, str, datetime]]:
        """Query Notion for status changes. Returns (page_id, status, last_edited_time)."""
        if not self.is_configured():
            return []

        from notion_client import AsyncClient

        client = AsyncClient(auth=self.api_key)
        updates = []

        try:
            has_more = True
            start_cursor = None

            while has_more:
                kwargs: dict[str, Any] = {"database_id": self.ideas_database_id}
                if start_cursor:
                    kwargs["start_cursor"] = start_cursor

                response = await client.databases.query(**kwargs)

                for page in response.get("results", []):
                    page_id = page["id"]
                    props = page.get("properties", {})

                    status_prop = props.get("Status", {})
                    select_val = status_prop.get("select")
                    if not select_val:
                        continue

                    status = select_val.get("name", "").lower()
                    edited_str = page.get("last_edited_time", "")

                    if edited_str:
                        edited_time = datetime.fromisoformat(edited_str.replace("Z", "+00:00"))
                    else:
                        edited_time = datetime.now(timezone.utc)

                    updates.append((page_id, status, edited_time))

                has_more = response.get("has_more", False)
                start_cursor = response.get("next_cursor")

        except Exception as e:
            logger.error("notion_pull_failed", error=str(e))

        return updates

    def _build_properties(self, idea: Any) -> dict[str, Any]:
        """Build Notion page properties from an Idea object."""
        channels_options = [{"name": ch} for ch in (idea.channels or [])]
        created_date = idea.created_at.isoformat() if idea.created_at else None

        return {
            "Title": {"title": [{"text": {"content": idea.title}}]},
            "One-liner": {"rich_text": [{"text": {"content": idea.one_liner or ""}}]},
            "Target Users": {"rich_text": [{"text": {"content": idea.target_users or ""}}]},
            "Pain Point": {"rich_text": [{"text": {"content": idea.pain_point or ""}}]},
            "Differentiation": {"rich_text": [{"text": {"content": idea.differentiation or ""}}]},
            "Channels": {"multi_select": channels_options},
            "Revenue Model": {"select": {"name": idea.revenue_model or "unknown"}},
            "Key Resources": {"rich_text": [{"text": {"content": idea.key_resources or ""}}]},
            "Cost Estimate": {"rich_text": [{"text": {"content": idea.cost_estimate or ""}}]},
            "Validation": {"rich_text": [{"text": {"content": idea.validation_method or ""}}]},
            "Difficulty": {"select": {"name": str(idea.difficulty)}},
            "Status": {"select": {"name": idea.status or "pending"}},
            "Generated": {"date": {"start": created_date}},
        }
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -m pytest tests/test_notion.py -v`
Expected: 6 passed (3 existing + 3 new)

- [ ] **Step 3: Commit**

```bash
git add src/muse/publisher/notion.py tests/test_notion.py
git commit -m "feat: add push_ideas and pull_status_updates to NotionPublisher"
```

### Task 17: Write failing test for notion_sync_job

**Files:**
- Create: `tests/test_notion_sync.py`

- [ ] **Step 1: Write test file**

Create `tests/test_notion_sync.py`:

```python
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from muse.config import Settings


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
        notion_api_key="ntn_test",
        notion_ideas_database_id="db-123",
    )


@pytest.mark.asyncio
async def test_notion_sync_pushes_new_ideas(settings):
    from muse.scheduler import notion_sync_job

    mock_idea = MagicMock()
    mock_idea.id = uuid.uuid4()
    mock_idea.notion_page_id = None

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_idea]
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("muse.scheduler.NotionPublisher") as mock_notion_cls:
        mock_notion = AsyncMock()
        mock_notion.is_configured.return_value = True
        mock_notion.push_ideas.return_value = [(mock_idea.id, "notion-page-123")]
        mock_notion.pull_status_updates.return_value = []
        mock_notion_cls.return_value = mock_notion

        await notion_sync_job(settings, mock_session_factory)

        mock_notion.push_ideas.assert_called_once()
        mock_session.execute.assert_called()  # update notion_page_id
        mock_session.commit.assert_called()


@pytest.mark.asyncio
async def test_notion_sync_pulls_status_updates(settings):
    from muse.scheduler import notion_sync_job

    mock_session = AsyncMock()
    mock_empty_result = MagicMock()
    mock_empty_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_empty_result)

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("muse.scheduler.NotionPublisher") as mock_notion_cls:
        mock_notion = AsyncMock()
        mock_notion.is_configured.return_value = True
        mock_notion.push_ideas.return_value = []
        mock_notion.pull_status_updates.return_value = [
            ("notion-page-123", "promising", datetime(2026, 3, 17, 12, 0, tzinfo=timezone.utc)),
        ]
        mock_notion_cls.return_value = mock_notion

        await notion_sync_job(settings, mock_session_factory)

        mock_notion.pull_status_updates.assert_called_once()


@pytest.mark.asyncio
async def test_notion_sync_skips_when_unconfigured():
    from muse.scheduler import notion_sync_job

    settings = Settings(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        miniflux_url="http://localhost:8080",
        miniflux_api_key="test",
        telegram_bot_token="123:abc",
        telegram_chat_id="-100test",
        notion_api_key="",
        notion_ideas_database_id="",
    )

    mock_session_factory = MagicMock()

    # Should return immediately without touching session
    await notion_sync_job(settings, mock_session_factory)
    mock_session_factory.assert_not_called()
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -m pytest tests/test_notion_sync.py -v`
Expected: FAIL (ImportError — `notion_sync_job` doesn't exist)

### Task 18: Implement notion_sync_job

**Files:**
- Modify: `src/muse/scheduler.py`

- [ ] **Step 1: Add imports**

Add to `src/muse/scheduler.py` imports:

```python
from sqlalchemy import select, update

from muse.db import Idea, Opportunity, Signal, State, VALID_IDEA_STATUSES
from muse.publisher.notion import NotionPublisher
```

Note: `update` is needed for Notion sync. Update the existing `from sqlalchemy import select` to include `update`.

- [ ] **Step 2: Add notion_sync_job function**

Add after `generate_ideas_job`:

```python
async def notion_sync_job(settings: Settings, session_factory) -> None:
    """Sync ideas with Notion — push new, pull status updates."""
    job_id = str(uuid.uuid4())[:8]
    logger.info("job_started", job="notion_sync", job_id=job_id)

    notion = NotionPublisher(
        api_key=settings.notion_api_key,
        ideas_database_id=settings.notion_ideas_database_id,
    )
    if not notion.is_configured():
        logger.info("notion_sync_skipped", reason="not configured")
        return

    # Push: new ideas → Notion
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
        logger.info("notion_pushed", count=len(pushed))

    # Pull: updated statuses from Notion → DB
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
        logger.info("notion_pulled", count=len(updates))

    logger.info("job_completed", job="notion_sync", job_id=job_id)
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -m pytest tests/test_notion_sync.py tests/test_scheduler_ideas.py -v`
Expected: ALL passed

- [ ] **Step 4: Commit**

```bash
git add src/muse/scheduler.py tests/test_notion_sync.py
git commit -m "feat: add notion_sync_job for bidirectional Notion sync"
```

---

## Chunk 6: Integration Test + Full Suite

### Task 19: Add integration test for idea pipeline

**Files:**
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Add test**

Add to `tests/test_integration.py` after `test_opportunity_pipeline`:

```python
@pytest.mark.asyncio
@respx.mock
async def test_idea_pipeline(settings, focus, db):
    """Opportunities → idea generation → store → push."""
    _, _, session_factory = db

    # Seed opportunities (simulating past month)
    async with session_factory() as session:
        for i in range(1, 3):
            session.add(Opportunity(
                title=f"Opportunity {i}",
                description=f"Description {i}",
                trend_category="developer-tools",
                unmet_need=f"Need {i}",
                market_gap=f"Gap {i}",
                geo_opportunity="",
                confidence="high",
                signal_ids=[],
                week_of=datetime.now(timezone.utc).date(),
            ))
        await session.commit()

    # Mock Claude API for idea generation
    ai_result = json.dumps({
        "ideas": [
            {
                "title": "TestIdea",
                "one_liner": "A test idea",
                "target_users": "Developers",
                "pain_point": "Testing pain",
                "differentiation": "Better tests",
                "channels": ["GitHub"],
                "revenue_model": "freemium",
                "key_resources": "Dev time",
                "cost_estimate": "Low",
                "validation_method": "MVP",
                "difficulty": 2,
                "source_opportunity_id": "will-not-match",
            }
        ],
        "monthly_summary": "Testing dominated.",
    })
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json={
            "content": [{"type": "text", "text": ai_result}],
            "usage": {"input_tokens": 500, "output_tokens": 300},
        })
    )

    # Mock Telegram
    bot_instance = AsyncMock()
    bot_instance.send_message = AsyncMock()
    bot_instance.__aenter__ = AsyncMock(return_value=bot_instance)
    bot_instance.__aexit__ = AsyncMock(return_value=False)

    from muse.scheduler import generate_ideas_job

    with patch("muse.publisher.telegram.Bot", return_value=bot_instance), \
         patch("muse.publisher.email.aiosmtplib") as mock_smtp:
        mock_smtp.send = AsyncMock()
        await generate_ideas_job(settings, focus, session_factory)

    # Verify: idea stored
    async with session_factory() as session:
        ideas = (await session.execute(select(Idea))).scalars().all()
        assert len(ideas) == 1
        assert ideas[0].title == "TestIdea"
        assert ideas[0].status == "pending"

    # Verify: Telegram push called
    bot_instance.send_message.assert_called_once()
```

- [ ] **Step 2: Add missing imports to test_integration.py**

Add to the imports at the top:

```python
from muse.db import Base, Idea, Opportunity, Signal, State, make_engine, make_session_factory
```

Update the existing import to include `Idea`.

- [ ] **Step 3: Run full test suite**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -m pytest tests/ -v --ignore=tests/test_integration.py`
Expected: ALL unit tests pass

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -m pytest tests/test_integration.py -v` (requires Docker for testcontainers)
Expected: ALL integration tests pass (if Docker available)

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add idea pipeline integration test"
```

### Task 20: Run full test suite and final verification

- [ ] **Step 1: Run all unit tests**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -m pytest tests/ --ignore=tests/test_integration.py -v`
Expected: ALL passed (should be ~25+ tests)

- [ ] **Step 2: Verify all imports work**

Run: `cd /Users/uraurora/Files/moflow/github/muse && python -c "from muse.main import main; from muse.scheduler import generate_ideas_job, notion_sync_job; from muse.analyzer.idea import IdeaGenerator; from muse.db import Idea, VALID_IDEA_STATUSES; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 3: Final commit if any loose changes**

```bash
git status
# If any uncommitted changes, commit them
```
