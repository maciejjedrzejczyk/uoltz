"""Multi-agent brainstorming skill using Strands Graph pattern.

Pipeline:
  1. Decomposer — breaks the topic into angles (with date context + prior brainstorms)
  2. Domain classifier selects specialist agents dynamically
  3. Parallel ideation agents (5 specialists + media_scout)
  4. Fact-checker cross-references all outputs
  5. Synthesizer — merges into a confidence-scored structured report
  6. Saves results to data/brainstorms/<slug>/

Graph topology (default):
  decomposer ──┬── visionary    ──┐
               ├── critic       ──┤
               ├── researcher   ──├── fact_checker ──► synthesizer
               ├── pragmatist   ──┤
               └── media_scout  ──┘
"""

import os
import re
import logging
from datetime import datetime, timezone
from pathlib import Path

from strands import Agent, tool
from strands.multiagent import GraphBuilder
from skills.web_search.search import web_search
from skills.brainstorm._youtube_search import youtube_search
import config

logger = logging.getLogger(__name__)

BRAINSTORMS_DIR = Path("data/brainstorms")


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_]+", "-", slug).strip("-")[:60]


def _find_prior_brainstorms(topic: str, max_results: int = 3) -> str:
    """Scan past brainstorm reports for related topics."""
    if not BRAINSTORMS_DIR.is_dir():
        return ""

    topic_words = set(re.sub(r"[^\w\s]", "", topic.lower()).split())
    if not topic_words:
        return ""

    scored = []
    for report_path in BRAINSTORMS_DIR.glob("*/REPORT.md"):
        folder_name = report_path.parent.name
        # Strip timestamp prefix (YYYYMMDD-HHMMSS_)
        slug_part = re.sub(r"^\d{8}-\d{6}_", "", folder_name)
        slug_words = set(slug_part.replace("-", " ").split())
        overlap = len(topic_words & slug_words)
        if overlap > 0:
            scored.append((overlap, folder_name, report_path))

    if not scored:
        return ""

    scored.sort(key=lambda x: x[0], reverse=True)
    sections = ["PRIOR BRAINSTORMS ON RELATED TOPICS:\n"]
    for _, folder_name, report_path in scored[:max_results]:
        try:
            text = report_path.read_text()
            # Take just the first 500 chars as a summary
            preview = text[:500].strip()
            sections.append(f"[{folder_name}]\n{preview}\n...\n")
        except Exception:
            continue

    return "\n".join(sections) if len(sections) > 1 else ""


def _get_rss_context(topic: str) -> str:
    """Pull recent articles from FreshRSS feeds if configured and relevant."""
    try:
        from skills.rss_digest.rss import _get_auth_token, _get_unread_items, MONITORED_FEEDS
    except ImportError:
        return ""

    auth = _get_auth_token()
    if not auth:
        return ""

    items = _get_unread_items(auth, list(MONITORED_FEEDS.keys()), count=5)
    if not items:
        return ""

    lines = ["RECENT ARTICLES FROM CURATED RSS FEEDS:\n"]
    for item in items:
        lines.append(f"- [{item['feed']}] {item['title']}: {item['url']}")

    return "\n".join(lines)


def _classify_domain(topic: str) -> str:
    """Simple keyword-based domain classification."""
    topic_lower = topic.lower()

    tech_keywords = {"api", "code", "software", "app", "database", "cloud", "ai",
                     "ml", "devops", "kubernetes", "docker", "python", "javascript",
                     "architecture", "microservice", "server", "deploy", "infra",
                     "algorithm", "framework", "backend", "frontend", "saas", "llm"}
    business_keywords = {"startup", "revenue", "market", "customer", "pricing",
                         "growth", "strategy", "competitor", "funding", "b2b", "b2c",
                         "sales", "marketing", "roi", "profit", "business model"}
    creative_keywords = {"design", "art", "music", "writing", "story", "brand",
                         "creative", "content", "video", "game", "ux", "ui"}

    words = set(re.sub(r"[^\w\s]", "", topic_lower).split())

    scores = {
        "tech": len(words & tech_keywords),
        "business": len(words & business_keywords),
        "creative": len(words & creative_keywords),
    }

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def _build_brainstorm_graph(topic: str, context: str = "") -> "Graph":
    """Construct the brainstorming agent graph with domain-aware specialists."""
    model = config.make_model()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    domain = _classify_domain(topic)

    # --- Prior brainstorms + RSS context ---
    prior = _find_prior_brainstorms(topic)
    rss_context = _get_rss_context(topic)

    extra_context = ""
    if context:
        extra_context += f"\nUSER CONTEXT: {context}\n"
    if prior:
        extra_context += f"\n{prior}\n"
    if rss_context:
        extra_context += f"\n{rss_context}\n"

    # --- Decomposer (with temporal grounding + prior awareness) ---
    decomposer = Agent(
        name="decomposer",
        model=model,
        system_prompt=(
            f"You are a strategic thinker. Today's date is {today}.\n\n"
            "Given a topic, break it down into 4-6 distinct angles, "
            "sub-questions, or dimensions worth exploring. "
            "Output a numbered list. Be creative and thorough.\n\n"
            "If prior brainstorms on related topics are provided below, "
            "acknowledge them and focus on NEW angles not already covered.\n"
            f"{extra_context}"
        ),
    )

    # --- Domain-specific specialist swap (#8) ---
    if domain == "tech":
        specialist_name = "technical_architect"
        specialist_prompt = (
            f"You are a senior technical architect. Today is {today}. "
            "Given a topic and its decomposed angles, propose system designs, "
            "technology choices, scalability considerations, and technical "
            "trade-offs. Consider current best practices and emerging tech. "
            "Structure your output with clear headings."
        )
    elif domain == "business":
        specialist_name = "strategist"
        specialist_prompt = (
            f"You are a business strategist. Today is {today}. "
            "Given a topic and its decomposed angles, analyze market dynamics, "
            "competitive landscape, go-to-market strategies, unit economics, "
            "and growth levers. Structure your output with clear headings."
        )
    elif domain == "creative":
        specialist_name = "creative_director"
        specialist_prompt = (
            f"You are a creative director. Today is {today}. "
            "Given a topic and its decomposed angles, explore aesthetic "
            "directions, audience engagement, storytelling approaches, "
            "and innovative formats. Structure your output with clear headings."
        )
    else:
        specialist_name = "visionary"
        specialist_prompt = (
            f"You are a bold, future-oriented visionary. Today is {today}. "
            "Given a topic and its decomposed angles, generate ambitious, "
            "unconventional ideas. Think 10 years ahead. Push boundaries. "
            "Dream big. Structure your output with clear headings."
        )

    specialist = Agent(
        name=specialist_name,
        model=model,
        system_prompt=specialist_prompt,
    )

    critic = Agent(
        name="critic",
        model=model,
        system_prompt=(
            f"You are a sharp critical thinker. Today is {today}. "
            "Given a topic and its decomposed angles, identify risks, "
            "blind spots, potential failures, and counter-arguments. "
            "Be constructive but unflinching. "
            "Structure your output with clear headings."
        ),
    )

    researcher = Agent(
        name="researcher",
        model=model,
        tools=[web_search],
        system_prompt=(
            f"You are a thorough researcher. Today is {today}. "
            "Given a topic and its decomposed angles, use the web_search "
            "tool to find relevant facts, precedents, case studies, and "
            "data points that inform the discussion. "
            "Search for multiple aspects of the topic. Cite sources with URLs. "
            "Structure your output with clear headings."
        ),
    )

    pragmatist = Agent(
        name="pragmatist",
        model=model,
        system_prompt=(
            f"You are a practical implementer. Today is {today}. "
            "Given a topic and its decomposed angles, propose concrete, "
            "actionable steps, timelines, resource requirements, and quick wins. "
            "Focus on what can be done NOW. "
            "Structure your output with clear headings."
            + (f"\n\nUser context to tailor advice: {context}" if context else "")
        ),
    )

    media_scout = Agent(
        name="media_scout",
        model=model,
        tools=[web_search, youtube_search],
        system_prompt=(
            f"You are a media researcher specializing in video content. "
            f"Today is {today}.\n\n"
            "Given a topic and its decomposed angles:\n"
            "1. Use web_search to find relevant YouTube videos on the topic "
            "(search for: '<topic> site:youtube.com')\n"
            "2. Use youtube_search to extract transcripts from the most "
            "promising video URLs (up to 3 videos)\n"
            "3. Distill key insights, expert opinions, tutorials, and unique "
            "perspectives found in the video content\n\n"
            "Structure your output with clear headings. Cite video titles and "
            "URLs for each insight."
        ),
    )

    # --- Fact-checker (#2) ---
    fact_checker = Agent(
        name="fact_checker",
        model=model,
        tools=[web_search],
        system_prompt=(
            f"You are a rigorous fact-checker. Today is {today}.\n\n"
            "You receive outputs from multiple brainstorming agents. Your job:\n"
            "1. Cross-reference claims between agents — flag contradictions\n"
            "2. Verify key factual claims using web_search (spot-check 3-5 claims)\n"
            "3. Mark each major claim as VERIFIED, UNVERIFIED, or DISPUTED\n"
            "4. Note any outdated information\n\n"
            "Output a structured fact-check report. Be concise — focus on "
            "claims that matter, not obvious opinions."
        ),
    )

    # --- Synthesizer (with confidence scoring #7) ---
    synthesizer = Agent(
        name="synthesizer",
        model=model,
        system_prompt=(
            f"You are a master synthesizer. Today is {today}.\n\n"
            f"You receive outputs from specialist agents ({specialist_name}, "
            "critic, researcher, pragmatist, media_scout) AND a fact-checker "
            "report that marks claims as VERIFIED/UNVERIFIED/DISPUTED.\n\n"
            "Merge them into a single, well-structured brainstorming report:\n"
            "1. Executive Summary\n"
            "2. Key Ideas (ranked by potential impact, each with a confidence "
            "tag: HIGH if backed by verified sources, MEDIUM if partially "
            "supported, LOW if purely speculative)\n"
            "3. Risks & Mitigations\n"
            "4. Supporting Evidence (web and video sources)\n"
            "5. Fact-Check Highlights (contradictions or disputed claims)\n"
            "6. Recommended Next Steps\n"
            "7. Open Questions\n\n"
            "Be comprehensive but concise."
            + config.formatting_instruction()
        ),
    )

    # --- Build graph ---
    builder = GraphBuilder()

    builder.add_node(decomposer, "decomposer")
    builder.add_node(specialist, specialist_name)
    builder.add_node(critic, "critic")
    builder.add_node(researcher, "researcher")
    builder.add_node(pragmatist, "pragmatist")
    builder.add_node(media_scout, "media_scout")
    builder.add_node(fact_checker, "fact_checker")
    builder.add_node(synthesizer, "synthesizer")

    # Decomposer fans out to all five ideation agents in parallel
    builder.add_edge("decomposer", specialist_name)
    builder.add_edge("decomposer", "critic")
    builder.add_edge("decomposer", "researcher")
    builder.add_edge("decomposer", "pragmatist")
    builder.add_edge("decomposer", "media_scout")

    # All five converge into fact_checker
    builder.add_edge(specialist_name, "fact_checker")
    builder.add_edge("critic", "fact_checker")
    builder.add_edge("researcher", "fact_checker")
    builder.add_edge("pragmatist", "fact_checker")
    builder.add_edge("media_scout", "fact_checker")

    # Fact-checker feeds into synthesizer
    builder.add_edge("fact_checker", "synthesizer")

    builder.set_entry_point("decomposer")
    builder.set_execution_timeout(900)  # 15 min — extra time for fact-checking

    return builder.build()


def _save_results(topic: str, context: str, graph_result) -> Path:
    """Save brainstorm results to a project folder."""
    slug = _slugify(topic)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    project_dir = BRAINSTORMS_DIR / f"{timestamp}_{slug}"
    project_dir.mkdir(parents=True, exist_ok=True)

    for node_id, node_result in graph_result.results.items():
        content = str(node_result.result) if node_result.result else "(no output)"
        (project_dir / f"{node_id}.md").write_text(
            f"# {node_id.title()} — {topic}\n\n{content}\n"
        )

    synth = graph_result.results.get("synthesizer")
    final_report = str(synth.result) if synth and synth.result else "(synthesis failed)"
    (project_dir / "REPORT.md").write_text(
        f"# Brainstorm Report: {topic}\n\n"
        f"_Generated: {timestamp}_\n\n"
        f"{final_report}\n"
    )

    (project_dir / "meta.txt").write_text(
        f"topic: {topic}\n"
        f"context: {context or '(none)'}\n"
        f"domain: {_classify_domain(topic)}\n"
        f"timestamp: {timestamp}\n"
        f"status: {graph_result.status}\n"
        f"execution_order: {[n.node_id for n in graph_result.execution_order]}\n"
    )

    return project_dir


@tool
def brainstorm_topic(topic: str, context: str = "") -> str:
    """Run a multi-agent brainstorming session on a topic.

    This orchestrates multiple AI agents in parallel to explore a topic from
    different perspectives, then fact-checks and synthesizes everything into
    a confidence-scored structured report.

    Use this when the user wants to brainstorm, ideate, explore an idea deeply,
    or think through a problem from multiple angles.

    Results are saved to data/brainstorms/ as a project folder with individual
    agent outputs and a final synthesized report.

    Args:
        topic: The topic, question, or idea to brainstorm about.
        context: Optional user context to tailor the brainstorm (e.g.
                 "solo developer, $5k budget, targeting B2B SaaS").
    """
    logger.info("Starting brainstorm on: %s (domain: %s, context: %s)",
                topic, _classify_domain(topic), context[:80] if context else "none")

    try:
        graph = _build_brainstorm_graph(topic, context)
        result = graph(f"Brainstorm deeply on this topic: {topic}")

        project_dir = _save_results(topic, context, result)
        logger.info("Brainstorm saved to %s", project_dir)

        synth = result.results.get("synthesizer")
        report = str(synth.result) if synth and synth.result else "(synthesis failed)"

        return (
            f"Brainstorm complete. Results saved to {project_dir}\n\n"
            f"--- REPORT ---\n\n{report}"
        )
    except Exception as e:
        logger.exception("Brainstorm failed")
        return f"Brainstorm failed: {e}"
