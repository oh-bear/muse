import json

import httpx
import pytest
import respx

from muse.analyzer.ai_client import AIClient, AIRequestError

CLAUDE_URL = "https://api.anthropic.com/v1/messages"


@pytest.fixture
def client():
    return AIClient(provider="claude", api_key="sk-test", base_delay=0.01)


def _claude_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "content": [{"type": "text", "text": content}],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
    )


@pytest.mark.asyncio
@respx.mock
async def test_call_returns_parsed_json(client):
    payload = {"entries": [{"score": 4}]}
    respx.post(CLAUDE_URL).mock(return_value=_claude_response(json.dumps(payload)))
    result, usage = await client.call("system prompt", "user prompt")
    assert result == payload
    assert usage["input_tokens"] == 100


@pytest.mark.asyncio
@respx.mock
async def test_call_retries_on_invalid_json(client):
    route = respx.post(CLAUDE_URL)
    route.side_effect = [
        _claude_response("not json"),
        _claude_response(json.dumps({"entries": []})),
    ]
    result, usage = await client.call("sys", "user")
    assert result == {"entries": []}


@pytest.mark.asyncio
@respx.mock
async def test_call_raises_after_all_retries_fail(client):
    respx.post(CLAUDE_URL).mock(return_value=_claude_response("not json"))
    with pytest.raises(AIRequestError):
        await client.call("sys", "user")


@pytest.mark.asyncio
@respx.mock
async def test_call_retries_on_http_error(client):
    route = respx.post(CLAUDE_URL)
    route.side_effect = [
        httpx.Response(429),
        _claude_response(json.dumps({"entries": []})),
    ]
    result, usage = await client.call("sys", "user")
    assert result == {"entries": []}
