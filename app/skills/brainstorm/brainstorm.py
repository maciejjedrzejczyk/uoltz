"""Multi-agent brainstorming skill using Strands Graph pattern.

Pipeline:
  1. Decomposer — breaks the topic into angles/sub-questions
  2. Parallel ideation agents (Visionary, Critic, Researcher, Pragmatist)
  3. Synthesizer — merges all perspectives into a structured report
  4. Saves results to data/brainstorms/<slug>/

Graph topology:
  decomposer ──┬── visionary  ──┐
               ├── critic     ──┤
               ├── researcher ──├── synthesizer
               └── pragmatist ──┘
"""

import os
import re
import logging
from datetime import datetime, timezone
from pathlib import Path

from strands import Agent, tool
from strands.multiagent import GraphBuilder
from skills.web_search.search import web_search
import config

logger = logging.getLogger(__name__)

BRAINSTORMS_DIR = Path("data/brainstorms")


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_]+", "-", slug).strip("-")[:60]


def _build_brainstorm_graph() -> "Graph":
    """Construct the brainstorming agent graph."""
    model = config.make_model()

    decomposer = Agent(
        name="decomposer",
        model=model,
        system_prompt=(
            "You are a strategic thinker. Given a topic, break it down into "
            "4-6 distinct angles, sub-questions, or dimensions worth exploring. "
            "Output a numbered list. Be creative and thorough."
        ),
    )

    visionary = Agent(
        name="visionary",
        model=model,
        system_prompt=(
            "You are a bold, future-oriented visionary. Given a topic and its "
            "decomposed angles, generate ambitious, unconventional ideas. "
            "Think 10 years ahead. Push boundaries. Dream big. "
            "Structure your output with clear headings."
        ),
    )

    critic = Agent(
        name="critic",
        model=model,
        system_prompt=(
            "You are a sharp critical thinker. Given a topic and its decomposed "
            "angles, identify risks, blind spots, potential failures, and "
            "counter-arguments. Be constructive but unflinching. "
            "Structure your output with clear headings."
        ),
    )

    researcher = Agent(
        name="researcher",
        model=model,
        tools=[web_search],
        system_prompt=(
            "You are a thorough researcher. Given a topic and its decomposed "
            "angles, use the web_search tool to find relevant facts, precedents, "
            "case studies, and data points that inform the discussion. "
            "Search for multiple aspects of the topic. Cite sources with URLs. "
            "Structure your output with clear headings."
        ),
    )

    pragmatist = Agent(
        name="pragmatist",
        model=model,
        system_prompt=(
            "You are a practical implementer. Given a topic and its decomposed "
            "angles, propose concrete, actionable steps, timelines, resource "
            "requirements, and quick wins. Focus on what can be done NOW. "
            "Structure your output with clear headings."
        ),
    )

    synthesizer = Agent(
        name="synthesizer",
        model=model,
        system_prompt=(
            "You are a master synthesizer. You receive outputs from four "
            "perspectives: Visionary, Critic, Researcher, and Pragmatist. "
            "Merge them into a single, well-structured brainstorming report with:\n"
            "1. Executive Summary\n"
            "2. Key Ideas (ranked by potential impact)\n"
            "3. Risks & Mitigations\n"
            "4. Supporting Evidence\n"
            "5. Recommended Next Steps\n"
            "6. Open Questions\n\n"
            "Be comprehensive but concise."
            + config.formatting_instruction()
        ),
    )

    builder = GraphBuilder()

    builder.add_node(decomposer, "decomposer")
    builder.add_node(visionary, "visionary")
    builder.add_node(critic, "critic")
    builder.add_node(researcher, "researcher")
    builder.add_node(pragmatist, "pragmatist")
    builder.add_node(synthesizer, "synthesizer")

    # Decomposer fans out to all four ideation agents in parallel
    builder.add_edge("decomposer", "visionary")
    builder.add_edge("decomposer", "critic")
    builder.add_edge("decomposer", "researcher")
    builder.add_edge("decomposer", "pragmatist")

    # All four converge into the synthesizer
    builder.add_edge("visionary", "synthesizer")
    builder.add_edge("critic", "synthesizer")
    builder.add_edge("researcher", "synthesizer")
    builder.add_edge("pragmatist", "synthesizer")

    builder.set_entry_point("decomposer")
    builder.set_execution_timeout(600)  # 10 min safety limit

    return builder.build()


def _save_results(topic: str, graph_result) -> Path:
    """Save brainstorm results to a project folder."""
    slug = _slugify(topic)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    project_dir = BRAINSTORMS_DIR / f"{timestamp}_{slug}"
    project_dir.mkdir(parents=True, exist_ok=True)

    # Save each agent's output as a separate file
    for node_id, node_result in graph_result.results.items():
        content = str(node_result.result) if node_result.result else "(no output)"
        (project_dir / f"{node_id}.md").write_text(
            f"# {node_id.title()} — {topic}\n\n{content}\n"
        )

    # The synthesizer output is the final report
    synth = graph_result.results.get("synthesizer")
    final_report = str(synth.result) if synth and synth.result else "(synthesis failed)"
    (project_dir / "REPORT.md").write_text(
        f"# Brainstorm Report: {topic}\n\n"
        f"_Generated: {timestamp}_\n\n"
        f"{final_report}\n"
    )

    # Save metadata
    (project_dir / "meta.txt").write_text(
        f"topic: {topic}\n"
        f"timestamp: {timestamp}\n"
        f"status: {graph_result.status}\n"
        f"execution_order: {[n.node_id for n in graph_result.execution_order]}\n"
    )

    return project_dir


@tool
def brainstorm_topic(topic: str) -> str:
    """Run a multi-agent brainstorming session on a topic.

    This orchestrates multiple AI agents in parallel to explore a topic from
    different perspectives (visionary, critic, researcher, pragmatist), then
    synthesizes everything into a structured report.

    Use this when the user wants to brainstorm, ideate, explore an idea deeply,
    or think through a problem from multiple angles.

    Results are saved to data/brainstorms/ as a project folder with individual
    agent outputs and a final synthesized report.

    Args:
        topic: The topic, question, or idea to brainstorm about.
    """
    logger.info("Starting brainstorm on: %s", topic)

    try:
        graph = _build_brainstorm_graph()
        result = graph(f"Brainstorm deeply on this topic: {topic}")

        project_dir = _save_results(topic, result)
        logger.info("Brainstorm saved to %s", project_dir)

        # Return the synthesized report to the user
        synth = result.results.get("synthesizer")
        report = str(synth.result) if synth and synth.result else "(synthesis failed)"

        return (
            f"Brainstorm complete. Results saved to {project_dir}\n\n"
            f"--- REPORT ---\n\n{report}"
        )
    except Exception as e:
        logger.exception("Brainstorm failed")
        return f"Brainstorm failed: {e}"
