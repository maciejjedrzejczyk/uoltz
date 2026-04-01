"""Wrapper that compresses an agent's output before passing it downstream in the graph.

Each agent works with full-fidelity data internally, but its output is
summarized into a compact form (under a word limit) before the Graph
hands it to the next node. This prevents context overflow at merge points
(fact_checker, synthesizer) without losing research quality.
"""

import logging
from strands import Agent
import config

logger = logging.getLogger(__name__)

DEFAULT_MAX_WORDS = 400

CONDENSE_PROMPT_TEMPLATE = (
    "Condense the following agent output into a dense briefing of at most "
    "{max_words} words. Preserve ALL key facts, data points, URLs, and "
    "conclusions. Drop filler, repetition, and verbose explanations. "
    "Keep the same structure (headings, bullet points).\n\n"
    "---\n{text}\n---"
)


class CondensingAgent:
    """Wraps a Strands Agent, condensing its output before returning.

    Implements the AgentBase protocol (__call__ and invoke_async) so it
    can be used as a Graph node executor.
    """

    def __init__(self, agent: Agent, max_words: int = DEFAULT_MAX_WORDS):
        self.agent = agent
        self.max_words = max_words
        # Expose attributes the Graph inspects
        self.messages = agent.messages
        self.state = agent.state

    def _condense(self, text: str) -> str:
        """Use a lightweight LLM call to compress the output."""
        if len(text.split()) <= self.max_words:
            return text

        model = config.make_model()
        condenser = Agent(
            name=f"{self.agent.name}_condenser",
            model=model,
            system_prompt="You are a precise text condenser. Output only the condensed text.",
        )
        prompt = CONDENSE_PROMPT_TEMPLATE.format(max_words=self.max_words, text=text)
        try:
            result = condenser(prompt)
            condensed = str(result)
            logger.info("Condensed %s: %d → %d words",
                        self.agent.name, len(text.split()), len(condensed.split()))
            return condensed
        except Exception as e:
            logger.warning("Condensing failed for %s: %s — using truncation fallback",
                           self.agent.name, e)
            words = text.split()[:self.max_words]
            return " ".join(words) + "\n\n[... condensed by truncation]"

    def __call__(self, prompt=None, **kwargs):
        result = self.agent(prompt, **kwargs)
        original_text = str(result)
        condensed_text = self._condense(original_text)
        result.message["content"] = [{"text": condensed_text}]
        return result

    async def invoke_async(self, prompt=None, **kwargs):
        result = await self.agent.invoke_async(prompt, **kwargs)
        original_text = str(result)
        condensed_text = self._condense(original_text)
        result.message["content"] = [{"text": condensed_text}]
        return result
