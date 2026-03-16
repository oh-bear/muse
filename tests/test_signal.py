import pytest
from unittest.mock import AsyncMock

from muse.analyzer.signal import SignalDetector
from muse.collector.miniflux import MinifluxEntry


def _entry(eid: int, title: str) -> MinifluxEntry:
    return MinifluxEntry(entry_id=eid, title=title, url=f"https://x.com/{eid}", content=f"Desc {title}", source="producthunt")


@pytest.fixture
def detector(tmp_path):
    sys_prompt = tmp_path / "system.txt"
    sys_prompt.write_text("Evaluate entries. Focus: $focus_areas. Exclude: $exclude_areas. Team: $max_team_size")
    user_prompt = tmp_path / "user.txt"
    user_prompt.write_text("Entries:\n$entries")

    mock_client = AsyncMock()
    return SignalDetector(
        ai_client=mock_client,
        system_prompt_path=str(sys_prompt),
        user_prompt_path=str(user_prompt),
        focus_areas=["ai-tools"],
        exclude_areas=["crypto"],
        score_threshold=3,
        indie_criteria={"max_team_size": 5},
        batch_size=10,
    )


@pytest.mark.asyncio
async def test_detect_returns_high_scoring_entries(detector):
    ai_response = {
        "entries": [
            {"entry_id": 1, "score": 4, "tags": ["ai"], "summary": "Good tool", "reason": "Real pain"},
            {"entry_id": 2, "score": 2, "tags": ["other"], "summary": "Meh", "reason": "Noise"},
        ]
    }
    detector.ai_client.call.return_value = (ai_response, {"input_tokens": 100, "output_tokens": 50})

    entries = [_entry(1, "AI Tool"), _entry(2, "Meh Tool")]
    result = await detector.detect(entries)

    assert len(result.signals) == 1
    assert result.signals[0]["entry_id"] == 1
    assert result.signals[0]["score"] == 4


@pytest.mark.asyncio
async def test_detect_batches_entries(detector):
    detector.batch_size = 2
    detector.ai_client.call.side_effect = [
        ({"entries": [
            {"entry_id": 1, "score": 4, "tags": [], "summary": "x", "reason": "y"},
            {"entry_id": 2, "score": 4, "tags": [], "summary": "x", "reason": "y"},
        ]}, {"input_tokens": 100, "output_tokens": 50}),
        ({"entries": [
            {"entry_id": 3, "score": 4, "tags": [], "summary": "x", "reason": "y"},
        ]}, {"input_tokens": 50, "output_tokens": 25}),
    ]

    entries = [_entry(i, f"Tool {i}") for i in range(1, 4)]
    result = await detector.detect(entries)

    assert len(result.signals) == 3
    assert detector.ai_client.call.call_count == 2


@pytest.mark.asyncio
async def test_detect_tracks_failed_batches(detector):
    from muse.analyzer.ai_client import AIRequestError

    detector.batch_size = 2
    detector.ai_client.call.side_effect = [
        AIRequestError("API down"),
        ({"entries": [{"entry_id": 3, "score": 4, "tags": [], "summary": "x", "reason": "y"}]},
         {"input_tokens": 50, "output_tokens": 25}),
    ]

    entries = [_entry(i, f"Tool {i}") for i in range(1, 4)]
    result = await detector.detect(entries)

    assert result.failed_batches == 1
    assert result.total_batches == 2
    assert len(result.signals) == 1
