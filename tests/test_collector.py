import pytest
import respx
import httpx

from muse.collector.miniflux import MinifluxCollector


@pytest.fixture
def collector():
    return MinifluxCollector(
        base_url="http://miniflux:8080",
        api_key="test-key",
        source_mapping={"PH Feed": "producthunt"},
    )


def _make_entry(entry_id: int, title: str, feed_title: str = "PH Feed") -> dict:
    return {
        "id": entry_id,
        "title": title,
        "url": f"https://example.com/{entry_id}",
        "content": f"Description for {title}",
        "feed": {"title": feed_title},
    }


@pytest.mark.asyncio
@respx.mock
async def test_fetch_entries_returns_parsed_entries(collector):
    respx.get("http://miniflux:8080/v1/entries").mock(
        return_value=httpx.Response(200, json={
            "total": 1,
            "entries": [_make_entry(1, "Cool AI Tool")],
        })
    )
    entries = await collector.fetch_new_entries(after_entry_id=0)
    assert len(entries) == 1
    assert entries[0].entry_id == 1
    assert entries[0].title == "Cool AI Tool"
    assert entries[0].source == "producthunt"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_entries_unknown_feed_uses_slug(collector):
    respx.get("http://miniflux:8080/v1/entries").mock(
        return_value=httpx.Response(200, json={
            "total": 1,
            "entries": [_make_entry(2, "Some Post", feed_title="Unknown Blog")],
        })
    )
    entries = await collector.fetch_new_entries(after_entry_id=0)
    assert entries[0].source == "unknown-blog"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_entries_paginates(collector):
    route = respx.get("http://miniflux:8080/v1/entries")
    route.side_effect = [
        httpx.Response(200, json={
            "total": 150,
            "entries": [_make_entry(i, f"Entry {i}") for i in range(1, 101)],
        }),
        httpx.Response(200, json={
            "total": 150,
            "entries": [_make_entry(i, f"Entry {i}") for i in range(101, 151)],
        }),
    ]
    entries = await collector.fetch_new_entries(after_entry_id=0)
    assert len(entries) == 150


@pytest.mark.asyncio
@respx.mock
async def test_fetch_entries_handles_api_error(collector):
    respx.get("http://miniflux:8080/v1/entries").mock(
        return_value=httpx.Response(500)
    )
    with pytest.raises(httpx.HTTPStatusError):
        await collector.fetch_new_entries(after_entry_id=0)
