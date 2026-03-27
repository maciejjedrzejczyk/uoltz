"""Centralized configuration loaded from environment variables.

All skills and modules should import from here instead of reading
os.getenv() directly. This ensures a single source of truth.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class LLMConfig:
    """LLM server configuration."""
    base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "http://localhost:1234/v1"))
    api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", "lm-studio"))
    model_id: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "qwen2.5-14b-instruct"))
    temperature: float = field(default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0.7")))
    max_tokens: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_TOKENS", "4096")))


@dataclass(frozen=True)
class SignalConfig:
    """Signal messenger configuration."""
    api_url: str = field(default_factory=lambda: os.getenv("SIGNAL_API_URL", "http://localhost:9922"))
    number: str = field(default_factory=lambda: os.getenv("SIGNAL_NUMBER", ""))
    allowed_numbers: frozenset[str] = field(default_factory=lambda: _parse_allowed())


@dataclass(frozen=True)
class WhisperConfig:
    """Voice transcription configuration."""
    model_size: str = field(default_factory=lambda: os.getenv("WHISPER_MODEL", "base"))
    device: str = field(default_factory=lambda: os.getenv("WHISPER_DEVICE", "cpu"))
    compute_type: str = field(default_factory=lambda: os.getenv("WHISPER_COMPUTE_TYPE", "int8"))


def _parse_allowed() -> frozenset[str]:
    raw = os.getenv("ALLOWED_NUMBERS", "").strip()
    if not raw:
        return frozenset()
    return frozenset(n.strip() for n in raw.split(",") if n.strip())


# Singletons — created once at import time
llm = LLMConfig()
signal = SignalConfig()
whisper = WhisperConfig()


def make_model():
    """Create an OpenAIModel instance from the centralized LLM config."""
    from strands.models.openai import OpenAIModel
    return OpenAIModel(
        client_args={
            "base_url": llm.base_url,
            "api_key": llm.api_key,
        },
        model_id=llm.model_id,
        params={
            "temperature": llm.temperature,
            "max_tokens": llm.max_tokens,
        },
    )


def formatting_instruction() -> str:
    """Return the current formatting instruction based on runtime state.

    Skills should append this to their agent system prompts so that
    sub-agents respect the user's /md on|off toggle.
    """
    from runtime import state
    if state.markdown:
        return "\n\nFormat your responses using markdown for readability."
    return (
        "\n\nCRITICAL FORMATTING RULE: Do NOT use any markdown formatting. "
        "No asterisks for bold/italic, no # headers, no - or * bullet points, "
        "no ``` code blocks, no [links](url). Use plain text only. "
        "Use line breaks and spacing for structure instead."
    )
