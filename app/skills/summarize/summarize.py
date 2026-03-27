"""Summarization skill — summarize URLs or raw text."""

import logging
import re

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify
from strands import Agent, tool
import config

logger = logging.getLogger(__name__)

_URL_PATTERN = re.compile(r"https?://\S+")

# Headers to look like a real browser (some sites block plain httpx)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _fetch_url(url: str) -> str:
    """Fetch a URL and extract readable text content."""
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=20, follow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        return f"[Failed to fetch URL: {e}]"

    content_type = resp.headers.get("content-type", "")

    # If it's plain text or JSON, return as-is
    if "text/plain" in content_type or "application/json" in content_type:
        return resp.text[:15000]

    # HTML — extract article content
    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove noise: scripts, styles, nav, footer, ads
    for tag in soup.find_all(["script", "style", "nav", "footer", "header",
                               "aside", "iframe", "noscript"]):
        tag.decompose()

    # Try to find the main content area
    article = (
        soup.find("article")
        or soup.find("main")
        or soup.find(attrs={"role": "main"})
        or soup.find(class_=re.compile(r"article|post|content|entry", re.I))
        or soup.body
    )

    if article is None:
        return "[Could not extract content from page]"

    # Convert to markdown for clean readable text
    text = markdownify(str(article), strip=["img", "a"]).strip()

    # Truncate to avoid blowing up the context window
    if len(text) > 12000:
        text = text[:12000] + "\n\n[... content truncated for length]"

    return text


@tool
def summarize_content(content: str) -> str:
    """Summarize a URL or a block of text.

    Use this when the user asks to summarize, recap, or give a TLDR of:
    - A URL / web page / article link
    - A block of text they paste in
    - Any content they want condensed

    If the content contains a URL, the page will be fetched automatically.

    Args:
        content: A URL to fetch and summarize, or raw text to summarize.
    """
    # Check if the content contains a URL
    url_match = _URL_PATTERN.search(content)
    if url_match:
        url = url_match.group(0).rstrip(".,;:!?)")
        logger.info("Fetching URL for summarization: %s", url)
        source_text = _fetch_url(url)
        source_label = f"URL: {url}"
    else:
        source_text = content
        source_label = "provided text"

    if not source_text or source_text.startswith("[Failed") or source_text.startswith("[Could not"):
        return source_text

    logger.info("Summarizing %s (%d chars)", source_label, len(source_text))

    model = config.make_model()
    summarizer = Agent(
        name="summarizer",
        model=model,
        system_prompt=(
            "You are a concise summarizer. You receive content and produce a clear, "
            "well-structured summary. Your output should include:\n\n"
            "1. A one-line TLDR at the top\n"
            "2. Key points (3-7 bullet points)\n"
            "3. Any notable quotes or data points\n\n"
            "Be accurate. Don't invent information not in the source. "
            "Keep the total summary under 400 words."
            + config.formatting_instruction()
        ),
    )

    prompt = (
        f"Summarize the following content from {source_label}:\n\n"
        f"---\n{source_text}\n---"
    )

    try:
        result = summarizer(prompt)
        return str(result)
    except Exception as e:
        logger.exception("Summarization failed")
        return f"Summarization failed: {e}"
