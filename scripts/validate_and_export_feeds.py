"""Validate RSS feed URLs and export working feeds as OPML for Miniflux import."""

from __future__ import annotations

import asyncio
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

FEEDS: list[dict[str, str]] = [
    # --- 产品发现 & 独立开发 ---
    {"title": "Product Hunt - Today", "url": "https://www.producthunt.com/feed", "category": "product-discovery"},
    {"title": "Hacker News - Best", "url": "https://hnrss.org/best?points=50", "category": "product-discovery"},
    {"title": "GitHub Trending", "url": "https://mshibanami.github.io/GitHubTrendingRSS/daily/all.xml", "category": "product-discovery"},
    {"title": "HN Ask", "url": "https://hnrss.org/ask?points=30", "category": "product-discovery"},

    # --- 趋势 & 技术洞察 ---
    {"title": "TechCrunch", "url": "https://techcrunch.com/feed/", "category": "tech-trends"},
    {"title": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "category": "tech-trends"},
    {"title": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "category": "tech-trends"},
    {"title": "Y Combinator Blog", "url": "https://www.ycombinator.com/blog/rss/", "category": "tech-trends"},
    {"title": "Stratechery", "url": "https://stratechery.com/feed/", "category": "tech-trends"},

    # --- AI & 开发者工具 ---
    {"title": "OpenAI Blog", "url": "https://openai.com/blog/rss.xml", "category": "ai-devtools"},
    {"title": "Hugging Face Blog", "url": "https://huggingface.co/blog/feed.xml", "category": "ai-devtools"},
    {"title": "Simon Willison", "url": "https://simonwillison.net/atom/everything/", "category": "ai-devtools"},
    {"title": "The Changelog", "url": "https://changelog.com/feed", "category": "ai-devtools"},

    # --- Reddit ---
    {"title": "r/SideProject", "url": "https://www.reddit.com/r/SideProject/.rss", "category": "reddit"},
    {"title": "r/startups", "url": "https://www.reddit.com/r/startups/.rss", "category": "reddit"},
    {"title": "r/Entrepreneur", "url": "https://www.reddit.com/r/Entrepreneur/.rss", "category": "reddit"},
    {"title": "r/SaaS", "url": "https://www.reddit.com/r/SaaS/.rss", "category": "reddit"},

    # --- 中文 / 亚洲市场 ---
    {"title": "36氪", "url": "https://36kr.com/feed", "category": "chinese"},
    {"title": "少数派", "url": "https://sspai.com/feed", "category": "chinese"},
    {"title": "小众软件", "url": "https://www.appinn.com/feed/", "category": "chinese"},
    {"title": "V2EX", "url": "https://www.v2ex.com/index.xml", "category": "chinese"},
]


@dataclass
class FeedResult:
    title: str
    url: str
    category: str
    ok: bool
    status: int | None = None
    error: str | None = None


async def check_feed(client: httpx.AsyncClient, feed: dict[str, str]) -> FeedResult:
    try:
        resp = await client.get(feed["url"], follow_redirects=True)
        # Accept 200 and check if it looks like XML/RSS
        is_feed = resp.status_code == 200 and (
            "xml" in resp.headers.get("content-type", "")
            or "rss" in resp.headers.get("content-type", "")
            or "atom" in resp.headers.get("content-type", "")
            or resp.text.strip().startswith("<?xml")
            or "<rss" in resp.text[:500]
            or "<feed" in resp.text[:500]
        )
        return FeedResult(
            title=feed["title"],
            url=feed["url"],
            category=feed["category"],
            ok=is_feed,
            status=resp.status_code,
            error=None if is_feed else f"not a valid feed (content-type: {resp.headers.get('content-type', 'unknown')})",
        )
    except Exception as e:
        return FeedResult(
            title=feed["title"],
            url=feed["url"],
            category=feed["category"],
            ok=False,
            error=str(e),
        )


def generate_opml(results: list[FeedResult]) -> str:
    opml = ET.Element("opml", version="2.0")
    head = ET.SubElement(opml, "head")
    ET.SubElement(head, "title").text = "Muse RSS Feeds"
    body = ET.SubElement(opml, "body")

    categories: dict[str, ET.Element] = {}
    for r in results:
        if not r.ok:
            continue
        if r.category not in categories:
            categories[r.category] = ET.SubElement(
                body, "outline", text=r.category, title=r.category
            )
        ET.SubElement(
            categories[r.category],
            "outline",
            type="rss",
            text=r.title,
            title=r.title,
            xmlUrl=r.url,
        )

    ET.indent(opml, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(opml, encoding="unicode")


async def main() -> None:
    print(f"Validating {len(FEEDS)} feeds...\n")

    async with httpx.AsyncClient(
        timeout=15.0,
        headers={"User-Agent": "Mozilla/5.0 (Muse RSS Validator)"},
    ) as client:
        results = await asyncio.gather(*[check_feed(client, f) for f in FEEDS])

    ok_feeds = [r for r in results if r.ok]
    fail_feeds = [r for r in results if not r.ok]

    print(f"✓ {len(ok_feeds)} feeds OK:")
    for r in ok_feeds:
        print(f"  [{r.category}] {r.title} ({r.status})")

    if fail_feeds:
        print(f"\n✗ {len(fail_feeds)} feeds FAILED:")
        for r in fail_feeds:
            print(f"  [{r.category}] {r.title} — {r.error}")

    # Export OPML with working feeds only
    opml_path = "scripts/muse_feeds.opml"
    opml_content = generate_opml(ok_feeds)
    with open(opml_path, "w") as f:
        f.write(opml_content)
    print(f"\nOPML exported to {opml_path} ({len(ok_feeds)} feeds)")


if __name__ == "__main__":
    asyncio.run(main())
