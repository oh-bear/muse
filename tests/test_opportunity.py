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
