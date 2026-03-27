"""Real-time research skill using multi-step web search and synthesis.

Strategy:
  1. Determine today's date for temporal grounding
  2. Decompose the query into 2-3 targeted search queries
  3. Execute searches, collecting results with URLs
  4. Synthesize into a concise, sourced report
"""

import logging
from datetime import datetime, timezone

from strands import Agent, tool
from strands.models.openai import OpenAIModel
import config
from skills.web_search.search import web_search as _raw_web_search
from ddgs import DDGS

logger = logging.getLogger(__name__)


def _search(query: str, max_results: int = 5) -> list[dict]:
    """Run a DuckDuckGo search and return raw result dicts."""
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        logger.error("Search failed for '%s': %s", query, e)
        return []


def _news_search(query: str, max_results: int = 5) -> list[dict]:
    """Run a DuckDuckGo news search for recent articles."""
    try:
        with DDGS() as ddgs:
            return list(ddgs.news(query, max_results=max_results))
    except Exception as e:
        logger.error("News search failed for '%s': %s", query, e)
        return []


def _gather_sources(topic: str) -> str:
    """Run multiple searches and compile raw source material."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Web search with date context
    web_results = _search(f"{topic} {today}", max_results=5)
    # News search for recency
    news_results = _news_search(topic, max_results=5)
    # Fallback broader search without date
    broad_results = _search(topic, max_results=3)

    sections = [f"TODAY'S DATE: {today}\n"]

    if news_results:
        sections.append("=== RECENT NEWS ===")
        for r in news_results:
            title = r.get("title", "")
            body = r.get("body", "")
            url = r.get("url", "")
            date = r.get("date", "")
            sections.append(f"[{date}] {title}\n{body}\nURL: {url}\n")

    if web_results:
        sections.append("=== WEB RESULTS ===")
        for r in web_results:
            sections.append(f"{r.get('title', '')}\n{r.get('body', '')}\nURL: {r.get('href', '')}\n")

    if broad_results:
        sections.append("=== ADDITIONAL CONTEXT ===")
        for r in broad_results:
            sections.append(f"{r.get('title', '')}\n{r.get('body', '')}\nURL: {r.get('href', '')}\n")

    if len(sections) == 1:
        sections.append("No search results found.")

    return "\n".join(sections)


@tool
def research_topic(topic: str) -> str:
    """Research a topic using real-time web search and produce a sourced report.

    Use this when the user asks about current events, weather, stock prices,
    news, sports scores, or anything that requires up-to-date information.

    This tool searches multiple sources (web + news), verifies the current date,
    and synthesizes a concise report with links.

    Args:
        topic: The topic or question to research (e.g. "current weather in Warsaw",
               "AMZN stock price", "political situation in Middle East").
    """
    logger.info("Researching: %s", topic)

    sources = _gather_sources(topic)

    model = config.make_model()
    analyst = Agent(
        name="research_analyst",
        model=model,
        system_prompt=(
            "You are a research analyst producing concise, factual briefings. "
            "You will receive raw search results about a topic. Your job:\n\n"
            "1. Verify what today's date is (provided in the data)\n"
            "2. Extract the most relevant, current facts\n"
            "3. Discard outdated or irrelevant results\n"
            "4. Produce a SHORT report (max 300 words) with:\n"
            "   - A one-line summary at the top\n"
            "   - Key facts as bullet points\n"
            "   - Source links at the bottom (max 5 most relevant)\n\n"
            "Be precise with numbers, dates, and attributions. "
            "If data is conflicting, note the discrepancy. "
            "If information seems outdated, say so explicitly."
            + config.formatting_instruction()
        ),
    )

    prompt = (
        f"Research request: {topic}\n\n"
        f"Here are the raw search results:\n\n{sources}\n\n"
        f"Produce a concise, sourced report."
    )

    try:
        result = analyst(prompt)
        return str(result)
    except Exception as e:
        logger.exception("Research synthesis failed")
        return f"Research failed during synthesis: {e}\n\nRaw sources:\n{sources[:2000]}"
