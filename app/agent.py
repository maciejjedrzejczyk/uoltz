"""Strands Agent configured with an OpenAI-compatible LLM and auto-discovered skills."""

import logging

import httpx
from strands import Agent
from strands.models.openai import OpenAIModel
from skills import discover_skills, SkillRegistry
import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_BASE = """\
You are a helpful AI assistant communicating through Signal messenger.

You have access to the following skill sets:
{skills_summary}

When the user asks you to brainstorm, think step by step and provide
structured ideas. When researching, use the web search tool and
synthesize the results into a clear summary.

For Signal account management tasks (registering numbers, creating groups,
linking devices), use the signal_admin tools.

Always be direct and helpful. If you're unsure, say so.
"""

# Module-level references so we can swap them at runtime
_agent: Agent | None = None
_registry: SkillRegistry | None = None


def _build_system_prompt(registry: SkillRegistry) -> str:
    """Build the system prompt with current runtime settings."""
    base = SYSTEM_PROMPT_BASE.format(skills_summary=registry.summary())
    base += config.formatting_instruction()
    return base


def create_agent(model_id: str | None = None) -> tuple[Agent, SkillRegistry]:
    """Create and return a configured Strands Agent.

    Args:
        model_id: Override model ID. If None, uses config.llm.model_id.
    """
    global _agent, _registry

    from runtime import state

    mid = model_id or config.llm.model_id
    max_tok = state.max_tokens or config.llm.max_tokens

    model = OpenAIModel(
        client_args={
            "base_url": config.llm.base_url,
            "api_key": config.llm.api_key,
        },
        model_id=mid,
        params={
            "temperature": config.llm.temperature,
            "max_tokens": max_tok,
        },
    )

    if _registry is None:
        _registry = discover_skills()

    system_prompt = _build_system_prompt(_registry)

    _agent = Agent(
        model=model,
        tools=_registry.tools,
        system_prompt=system_prompt,
    )

    return _agent, _registry


def get_agent() -> Agent:
    """Return the current agent instance."""
    if _agent is None:
        raise RuntimeError("Agent not initialized. Call create_agent() first.")
    return _agent


def get_registry() -> SkillRegistry:
    """Return the current skill registry."""
    if _registry is None:
        raise RuntimeError("Registry not initialized. Call create_agent() first.")
    return _registry


def refresh_system_prompt():
    """Update the agent's system prompt (e.g. after toggling markdown)."""
    if _agent is not None and _registry is not None:
        _agent.system_prompt = _build_system_prompt(_registry)


def list_available_models() -> list[str]:
    """Query the LLM server for available models."""
    try:
        resp = httpx.get(f"{config.llm.base_url}/models", timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return [m["id"] for m in data]
    except Exception as e:
        logger.error("Failed to list models: %s", e)
        return []


def get_current_model_id() -> str:
    """Return the model ID the agent is currently using."""
    if _agent is not None:
        return _agent.model.config.get("model_id", config.llm.model_id)
    return config.llm.model_id


def get_current_max_tokens() -> int:
    """Return the effective max_tokens the agent is using."""
    from runtime import state
    return state.max_tokens or config.llm.max_tokens


def _lmstudio_api_base() -> str:
    """Derive the LM Studio management API base from the OpenAI-compat URL.

    e.g. http://10.36.35.54:1234/v1 → http://10.36.35.54:1234
    """
    base = config.llm.base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return base


def ensure_model_loaded(model_id: str | None = None) -> bool:
    """Ensure the model is loaded on the LLM server, loading it if necessary.

    Checks /v1/models for the target model. If missing, triggers a load
    via LM Studio's management API and waits for it to become available.

    Returns True if the model is ready, False on failure.
    """
    mid = model_id or config.llm.model_id

    # Check if already loaded
    try:
        resp = httpx.get(f"{config.llm.base_url}/models", timeout=10)
        resp.raise_for_status()
        loaded = [m["id"] for m in resp.json().get("data", [])]
        if mid in loaded:
            logger.debug("Model '%s' already loaded", mid)
            return True
    except Exception as e:
        logger.warning("Could not check loaded models: %s", e)

    # Not loaded — trigger load via LM Studio API
    logger.info("Model '%s' not loaded, triggering load...", mid)
    api = _lmstudio_api_base()
    try:
        resp = httpx.post(
            f"{api}/api/v1/models/load",
            json={"model": mid},
            timeout=120,
        )
        resp.raise_for_status()
        logger.info("Model '%s' loaded successfully", mid)
        return True
    except Exception as e:
        logger.error("Failed to load model '%s': %s", mid, e)
        return False


def server_reload_model(model_id: str, context_length: int) -> str:
    """Unload then reload a model on the LLM server with a new context window.

    Uses LM Studio's /api/v1/models/unload and /api/v1/models/load endpoints.
    """
    api = _lmstudio_api_base()

    # Unload current model (ignore errors — might not be loaded)
    try:
        httpx.post(
            f"{api}/api/v1/models/unload",
            json={"instance_id": model_id},
            timeout=30,
        )
    except Exception:
        pass  # model might not be loaded, that's fine

    # Load with new context length
    resp = httpx.post(
        f"{api}/api/v1/models/load",
        json={
            "model": model_id,
            "context_length": context_length,
            "echo_load_config": True,
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()

    load_config = data.get("load_config", {})
    actual_ctx = load_config.get("context_length", context_length)
    load_time = data.get("load_time_seconds", "?")

    return f"Loaded {model_id} with context_length={actual_ctx} in {load_time}s"
