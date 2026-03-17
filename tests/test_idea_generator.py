from unittest.mock import AsyncMock

import pytest

from muse.analyzer.idea import IdeaGenerator


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
    generator.ai_client.call.return_value = (
        ai_response,
        {"input_tokens": 500, "output_tokens": 300},
    )

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
        (
            {
                "ideas": [
                    {
                        "title": "Idea 1",
                        "one_liner": "o",
                        "target_users": "t",
                        "pain_point": "p",
                        "differentiation": "d",
                        "channels": [],
                        "revenue_model": "freemium",
                        "key_resources": "k",
                        "cost_estimate": "c",
                        "validation_method": "v",
                        "difficulty": 3,
                        "source_opportunity_id": "uuid-1",
                    },
                ],
                "monthly_summary": "Summary 1.",
            },
            {"input_tokens": 100, "output_tokens": 50},
        ),
        (
            {
                "ideas": [
                    {
                        "title": "Idea 2",
                        "one_liner": "o",
                        "target_users": "t",
                        "pain_point": "p",
                        "differentiation": "d",
                        "channels": [],
                        "revenue_model": "subscription",
                        "key_resources": "k",
                        "cost_estimate": "c",
                        "validation_method": "v",
                        "difficulty": 2,
                        "source_opportunity_id": "uuid-3",
                    },
                ],
                "monthly_summary": "Summary 2.",
            },
            {"input_tokens": 100, "output_tokens": 50},
        ),
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
        (
            {
                "ideas": [
                    {
                        "title": "Surviving Idea",
                        "one_liner": "o",
                        "target_users": "t",
                        "pain_point": "p",
                        "differentiation": "d",
                        "channels": [],
                        "revenue_model": "freemium",
                        "key_resources": "k",
                        "cost_estimate": "c",
                        "validation_method": "v",
                        "difficulty": 3,
                        "source_opportunity_id": "uuid-1",
                    },
                ],
                "monthly_summary": "Partial.",
            },
            {"input_tokens": 100, "output_tokens": 50},
        ),
        AIRequestError("Chunk 2 failed"),
    ]

    opps = [_opp(1, "Opp 1"), _opp(2, "Opp 2")]
    result = await generator.generate(opps)

    assert len(result.ideas) == 1
    assert result.ideas[0]["title"] == "Surviving Idea"
    assert result.failed
    assert result.monthly_summary == "Partial."


@pytest.mark.asyncio
async def test_generate_empty_opportunities(generator):
    result = await generator.generate([])

    assert len(result.ideas) == 0
    assert not result.failed
    generator.ai_client.call.assert_not_called()
