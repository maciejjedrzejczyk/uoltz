"""LinkedIn post proposal skill — curates trending topics and drafts short posts.

Sources:
  1. FreshRSS — unread articles from tech/cloud/AI feeds
  2. YouTube — recent videos on trending topics
  3. Web search — DuckDuckGo for fresh developments

Pipeline:
  1. Gather raw material from all sources
  2. LLM selects the 3-4 most compelling topics
  3. Drafts a short LinkedIn post proposal for each
"""

import logging
from datetime import datetime, timezone

from strands import Agent, tool
from ddgs import DDGS
import config

logger = logging.getLogger(__name__)

# RSS feeds relevant to software dev, cloud, and AI
LINKEDIN_FEEDS = {
    "feed/223": "AWS Architecture Blog",
    "feed/225": "AWS Compute Blog",
    "feed/226": "AWS DevOps Blog",
    "feed/228": "AWS Machine Learning Blog",
    "feed/230": "AWS Open Source Blog",
    "feed/235": "Containers",
    "feed/236": "Jeff Barr – AWS News Blog",
    "feed/405": "Hacker News",
    "feed/420": "InfoQ",
    "feed/445": "Simon Willison's Weblog",
    "feed/448": "AI Jason",
    "feed/471": "antirez",
    "feed/474": "The Pragmatic Engineer",
    "feed/475": "Epoch AI | Blog",
    "feed/480": "Ahead of AI",
    "feed/485": "Import AI",
    "feed/17": "The Register",
}


def _gather_rss(max_items: int = 10) -> list[dict]:
    """Fetch unread articles from curated tech/AI feeds."""
    try:
        from skills.rss_digest.rss import _get_auth_token, _get_unread_items
    except ImportError:
        logger.warning("RSS digest skill not available")
        return []

    auth = _get_auth_token()
    if not auth:
        return []

    items = _get_unread_items(auth, list(LINKEDIN_FEEDS.keys()), count=max_items)
    return [
        {"source": "rss", "feed": LINKEDIN_FEEDS.get(i.get("feed", ""), "RSS"),
         "title": i["title"], "url": i["url"]}
        for i in items if i.get("url")
    ]


def _gather_web(focus: str) -> list[dict]:
    """Search for recent developments in tech/cloud/AI."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    queries = [
        f"{focus} {today}" if focus else f"software engineering AI cloud news {today}",
    ]
    items = []
    try:
        with DDGS() as ddgs:
            for q in queries:
                for r in ddgs.news(q, max_results=5):
                    items.append({
                        "source": "web",
                        "feed": r.get("source", "web"),
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                    })
    except Exception as e:
        logger.warning("Web search failed: %s", e)
    return items


def _gather_youtube(focus: str) -> list[dict]:
    """Search YouTube for recent tech/AI videos."""
    query = focus if focus else "software engineering AI cloud computing"
    items = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.videos(f"{query} site:youtube.com", max_results=5):
                items.append({
                    "source": "youtube",
                    "feed": "YouTube",
                    "title": r.get("title", ""),
                    "url": r.get("content", r.get("url", "")),
                })
    except Exception as e:
        logger.warning("YouTube search failed: %s", e)
    return items


def _format_sources(items: list[dict]) -> str:
    """Format gathered items into a text block for the LLM."""
    if not items:
        return "(no sources found)"
    lines = []
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. [{item['source'].upper()} / {item['feed']}] {item['title']}\n   {item['url']}")
    return "\n".join(lines)


@tool
def propose_linkedin_posts(focus: str = "") -> str:
    """Propose 3-4 LinkedIn post ideas based on trending tech, cloud, and AI topics.

    Gathers material from RSS feeds, YouTube, and web news, then drafts
    short post proposals — each covering a single topic with a source link.

    Use this when the user wants LinkedIn content ideas, post suggestions,
    or wants to share something interesting from the tech world.

    Args:
        focus: Optional focus area (e.g. "kubernetes", "LLM agents",
               "serverless"). If empty, covers general software/cloud/AI.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logger.info("Gathering LinkedIn post material (focus: %s)", focus or "general")

    rss_items = _gather_rss()
    web_items = _gather_web(focus)
    yt_items = _gather_youtube(focus)

    all_items = rss_items + web_items + yt_items
    sources_text = _format_sources(all_items)

    logger.info("Gathered %d sources (rss=%d, web=%d, yt=%d)",
                len(all_items), len(rss_items), len(web_items), len(yt_items))

    model = config.make_model()
    drafter = Agent(
        name="linkedin_drafter",
        model=model,
        system_prompt=(
            f"You are a LinkedIn content strategist for a tech professional "
            f"who works in software development, cloud engineering, and AI. "
            f"Today is {today}.\n\n"
            "You will receive a list of recent articles, videos, and news items. "
            "Your job:\n\n"
            "1. Pick the 3-4 MOST interesting and share-worthy topics\n"
            "2. For each, draft a SHORT LinkedIn post proposal:\n"
            "   - A compelling hook (first line that grabs attention)\n"
            "   - 2-3 sentences of insight or opinion (not just a summary)\n"
            "   - A question or call-to-action to drive engagement\n"
            "   - The source link\n\n"
            "Guidelines:\n"
            "- Each post should cover ONE topic only\n"
            "- Keep each post under 100 words\n"
            "- Sound authentic and opinionated, not corporate\n"
            "- Prioritize topics that spark discussion\n"
            "- Include relevant hashtags (2-3 per post)\n"
            "- Number each proposal clearly (1, 2, 3, 4)\n"
            + config.formatting_instruction()
        ),
    )

    prompt = (
        f"Here are today's sources across RSS feeds, web news, and YouTube.\n"
        f"Focus area: {focus or 'general software dev / cloud / AI'}\n\n"
        f"{sources_text}\n\n"
        f"Pick the 3-4 best topics and draft LinkedIn post proposals."
    )

    try:
        result = drafter(prompt)
        return str(result)
    except Exception as e:
        logger.exception("LinkedIn post generation failed")
        return f"Failed to generate post proposals: {e}"
