from muse.collector.filter import pre_filter
from muse.collector.miniflux import MinifluxEntry


def _entry(title: str, content: str = "") -> MinifluxEntry:
    return MinifluxEntry(entry_id=1, title=title, url="https://x.com", content=content, source="test")


def test_exclude_matching_keywords():
    entries = [_entry("New Crypto Exchange"), _entry("AI Code Editor")]
    result = pre_filter(entries, exclude=["crypto", "web3"])
    assert len(result) == 1
    assert result[0].title == "AI Code Editor"


def test_exclude_is_case_insensitive():
    entries = [_entry("CRYPTO trading bot")]
    result = pre_filter(entries, exclude=["crypto"])
    assert len(result) == 0


def test_exclude_checks_content_too():
    entries = [_entry("New Tool", content="This is a web3 platform")]
    result = pre_filter(entries, exclude=["web3"])
    assert len(result) == 0


def test_empty_exclude_passes_all():
    entries = [_entry("Anything"), _entry("Goes")]
    result = pre_filter(entries, exclude=[])
    assert len(result) == 2
