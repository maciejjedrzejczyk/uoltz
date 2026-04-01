"""FreshRSS digest skill — fetches unread articles, summarizes, sends via Signal.

Uses the Google Reader-compatible API exposed by FreshRSS.
"""

import logging
import httpx
import config
from strands import Agent, tool
from skills.summarize.summarize import _fetch_url

logger = logging.getLogger(__name__)

# Feed IDs to monitor (discovered from FreshRSS API)
MONITORED_FEEDS = {
    "feed/17": "The Register",
    "feed/223": "AWS Architecture Blog",
    "feed/224": "AWS Cloud Enterprise Strategy Blog",
    "feed/225": "AWS Compute Blog",
    "feed/226": "AWS DevOps Blog",
    "feed/227": "AWS Developer Tools Blog",
    "feed/228": "AWS Machine Learning Blog",
    "feed/230": "AWS Open Source Blog",
    "feed/231": "AWS Security Blog",
    "feed/233": "AWS Training and Certification Blog",
    "feed/235": "Containers",
    "feed/236": "Jeff Barr – AWS News Blog",
    "feed/237": "The Internet of Things on AWS – Official Blog",
 
}


MAX_ARTICLES_PER_RUN = 5


def _get_auth_token() -> str | None:
    """Authenticate with FreshRSS and return an auth token."""
    cfg = config.freshrss
    if not cfg.url or not cfg.user:
        logger.error("FreshRSS not configured in .env")
        return None

    try:
        resp = httpx.post(
            f"{cfg.url}/api/greader.php/accounts/ClientLogin",
            data={"Email": cfg.user, "Passwd": cfg.api_password},
            timeout=15,
        )
        for line in resp.text.strip().split("\n"):
            if line.startswith("Auth="):
                return line[5:]
    except Exception as e:
        logger.error("FreshRSS auth failed: %s", e)
    return None


def _get_unread_items(auth: str, feed_ids: list[str], count: int = MAX_ARTICLES_PER_RUN) -> list[dict]:
    """Fetch unread items from specific feeds."""
    cfg = config.freshrss
    url = (
        f"{cfg.url}/api/greader.php/reader/api/0/stream/contents/user/-/state/com.google/reading-list"
        f"?output=json&n={count}&xt=user/-/state/com.google/read"
    )

    try:
        resp = httpx.get(
            url,
            headers={"Authorization": f"GoogleLogin auth={auth}"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("Failed to fetch unread items: %s", e)
        return []

    # Filter to only monitored feeds
    items = []
    for item in data.get("items", []):
        origin = item.get("origin", {}).get("streamId", "")
        if origin in feed_ids:
            title = item.get("title", "Untitled")
            link = ""
            for alt in item.get("alternate", []):
                if alt.get("type") == "text/html":
                    link = alt.get("href", "")
                    break
            if not link:
                # Fallback: try canonical
                for can in item.get("canonical", []):
                    link = can.get("href", "")
                    break

            feed_name = MONITORED_FEEDS.get(origin, origin)
            item_id = item.get("id", "")

            items.append({
                "id": item_id,
                "title": title,
                "url": link,
                "feed": feed_name,
            })

    return items[:count]


def _mark_as_read(auth: str, item_ids: list[str]):
    """Mark items as read in FreshRSS."""
    cfg = config.freshrss
    try:
        for item_id in item_ids:
            httpx.post(
                f"{cfg.url}/api/greader.php/reader/api/0/edit-tag",
                headers={"Authorization": f"GoogleLogin auth={auth}"},
                data={
                    "i": item_id,
                    "a": "user/-/state/com.google/read",
                },
                timeout=15,
            )
    except Exception as e:
        logger.error("Failed to mark items as read: %s", e)


def _summarize_article(title: str, url: str) -> str:
    """Fetch and summarize a single article."""
    if not url:
        return f"{title}\n(no URL available)"

    content = _fetch_url(url)
    if content.startswith("[Failed") or content.startswith("[Could not"):
        return f"{title}\n{url}\n(could not fetch content)"

    model = config.make_model()
    summarizer = Agent(
        name="rss_summarizer",
        model=model,
        system_prompt=(
            "You are a concise article summarizer. Produce a 2-3 sentence summary "
            "of the article content. Focus on the key takeaway. No preamble."
            + config.formatting_instruction()
        ),
    )

    try:
        result = summarizer(f"Summarize this article titled '{title}':\n\n{content[:8000]}")
        return str(result)
    except Exception as e:
        logger.error("Summary failed for %s: %s", title, e)
        return f"(summary failed: {e})"


@tool
def rss_digest(feed_filter: str = "") -> str:
    """Fetch unread articles from FreshRSS, summarize them, and return a digest.

    Use this when the user asks about RSS feeds, news digest, unread articles,
    or wants to catch up on their subscriptions.

    Currently monitors: The Register and AWS Blogs.

    Args:
        feed_filter: Optional filter to match feed names (e.g. "register", "aws").
                     If empty, checks all monitored feeds.
    """
    auth = _get_auth_token()
    if not auth:
        return "FreshRSS authentication failed. Check FRESHRSS_* settings in .env."

    # Filter feeds if requested
    if feed_filter:
        filter_lower = feed_filter.lower()
        feed_ids = [fid for fid, name in MONITORED_FEEDS.items() if filter_lower in name.lower()]
        if not feed_ids:
            available = ", ".join(MONITORED_FEEDS.values())
            return f"No feeds matching '{feed_filter}'. Available: {available}"
    else:
        feed_ids = list(MONITORED_FEEDS.keys())

    logger.info("Checking FreshRSS for unread items in %d feed(s)", len(feed_ids))
    items = _get_unread_items(auth, feed_ids)

    if not items:
        return "No unread articles in monitored feeds."

    logger.info("Found %d unread article(s), summarizing...", len(items))

    digests = []
    read_ids = []
    for item in items:
        logger.info("Summarizing: %s (%s)", item["title"], item["feed"])
        summary = _summarize_article(item["title"], item["url"])
        digests.append(
            f"[{item['feed']}]\n"
            f"{item['title']}\n"
            f"{summary}\n"
            f"{item['url']}"
        )
        read_ids.append(item["id"])

    # Mark as read so they don't appear again
    _mark_as_read(auth, read_ids)
    logger.info("Marked %d article(s) as read", len(read_ids))

    header = f"RSS Digest ({len(items)} article(s)):\n"
    return header + "\n\n---\n\n".join(digests)
