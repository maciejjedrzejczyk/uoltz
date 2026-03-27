"""Web search tool using DuckDuckGo (no API key needed)."""

from strands import tool
from ddgs import DDGS


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for information using DuckDuckGo.

    Use this tool when the user asks you to look something up, research a topic,
    find current information, or when you need facts you don't know.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            return "No results found."

        formatted = []
        for r in results:
            formatted.append(f"**{r['title']}**\n{r['body']}\nURL: {r['href']}")
        return "\n\n---\n\n".join(formatted)
    except Exception as e:
        return f"Search failed: {e}"
