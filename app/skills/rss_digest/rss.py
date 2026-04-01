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
    "feed/487": "*Walter Bloomberg / @DeItaone",  # finance
    "feed/400": "404 Media",  # IT
    "feed/412": "A Wealth of Common Sense",  # finance
    "feed/448": "AI Jason",  # AI
    "feed/484": "AI w zasięgu biznesu",  # AI
    "feed/480": "Ahead of AI",  # AI
    "feed/382": "All Things Distributed",  # aws
    "feed/476": "Andrej Karpathy / @karpathy",  # AI
    "feed/26": "Blogi bossa.pl",  # finance
    "feed/483": "Conversations with Tyler",  # AI
    "feed/372": "David Heinemeier Hansson",  # IT
    "feed/460": "Derek Thompson",  # US:Blogi
    "feed/427": "DoublePulsar - Medium",  # Security
    "feed/31": "Doxa - Przemysław A. Słomski",  # finance
    "feed/32": "DwaGrosze",  # PL:Blogi
    "feed/33": "Dziennik Śledczy",  # PL:Blogi
    "feed/469": "Ed Zitron's Where's Your Ed At",  # finance
    "feed/486": "Embrace The Red",  # Security
    "feed/475": "Epoch AI | Blog",  # AI
    "feed/479": "Eric Balchunas / @EricBalchunas",  # finance
    "feed/463": "Everyday Astronaut",  # space
    "feed/482": "Fran Schwartzkopff / @FranSchwar",  # finance
    "feed/466": "GrapheneOS",  # Security
    "feed/405": "Hacker News",  # IT
    "feed/38": "ITwiz",  # IT
    "feed/485": "Import AI",  # AI
    "feed/7": "IndependentTrader.pl",  # finance
    "feed/420": "InfoQ",  # IT
    "feed/39": "Informatyk Zakładowy",  # IT
    "feed/74": "Jeff Geerling's Blog",  # IT
    "feed/481": "Ken Klippenstein",  # US:Blogi
    "feed/408": "Last Week in AWS",  # US:Blogi
    "feed/488": "Lobsters",  # US:Blogi
    "feed/44": "Maczeta Ockhama",  # PL:Blogi
    "feed/426": "Map Happenings",  # US:Blogi
    "feed/411": "Marcus on AI",  # US:Blogi
    "feed/491": "Marginal Revolution",  # US:Blogi
    "feed/458": "NASA",  # space
    "feed/464": "NASASpaceflight",  # space
    "feed/48": "Niebezpiecznik.pl",  # IT
    "feed/341": "Noahpinion",  # US:Blogi
    "feed/455": "Ollama models",  # AI
    "feed/468": "Paul Kedrosky",  # finance
    "feed/462": "Philip Sloss",  # space
    "feed/404": "PlanB",  # finance
    "feed/54": "Podtwórca",  # PL:Blogi
    "feed/55": "Pokolenie Ikea",  # PL:Blogi
    "feed/10": "Przegląd Finansowy",  # finance
    "feed/57": "Przekraczając Granice",  # PL:Blogi
    "feed/478": "RenMac: Renaissance Macro Research",  # finance
    "feed/402": "Replicate's blog",  # US:Blogi
    "feed/424": "Rynek kapitałowy w pigułce",  # finance
    "feed/428": "SITUATIONAL AWARENESS",  # AI
    "feed/79": "Schneier on Security",  # Security
    "feed/465": "Scott Manley",  # space
    "feed/445": "Simon Willison's Weblog",  # AI
    "feed/454": "Simon Willison's Newsletter",  # AI
    "feed/459": "SpaceNews",  # space
    "feed/59": "Stanisław Michalkiewicz",  # PL:Blogi
    "feed/401": "Stockbroker.pl",  # PL:Blogi
    "feed/489": "Techmeme",  # US:Blogi
    "feed/61": "Terroryzm Geopolityka Izrael Iran Islam CIA FSB",  # PL:Blogi
    "feed/413": "The Eclectic Light Company",  # US:Blogi
    "feed/473": "The Power Law",  # AI
    "feed/474": "The Pragmatic Engineer",  # AI
    "feed/425": "War on the Rocks",  # US:Blogi
    "feed/391": "Warsaw Now!",  # PL:Blogi
    "feed/396": "Web3 is Going Just Great",  # US:Blogi
    "feed/470": "Works in Progress RSS Feed",  # US:Blogi
    "feed/492": "YTS RSS",  # Uncategorized
    "feed/339": "Zapiski czynione po drodze",  # PL:Blogi
    "feed/83": "Zaufana Trzecia Strona",  # Security
    "feed/67": "mikrowyprawy z Warszawy",  # PL:Blogi
    "feed/73": "wolność równość ludobójstwo",  # PL:Blogi
    "feed/471": "antirez",  # AI
}

# ── All available feeds (uncomment to add) ───────────────────────────


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
