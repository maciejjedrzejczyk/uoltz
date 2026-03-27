"""Voice message transcription using faster-whisper (local, no cloud)."""

import logging
import tempfile
from pathlib import Path

import httpx
from faster_whisper import WhisperModel

import config

logger = logging.getLogger(__name__)

# Lazy-loaded singleton — model downloads on first use
_model: WhisperModel | None = None

AUDIO_CONTENT_TYPES = {"audio/aac", "audio/mp4", "audio/mpeg", "audio/ogg", "audio/x-m4a"}


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        cfg = config.whisper
        logger.info("Loading Whisper model '%s' (device=%s, compute=%s)...",
                     cfg.model_size, cfg.device, cfg.compute_type)
        _model = WhisperModel(cfg.model_size, device=cfg.device, compute_type=cfg.compute_type)
        logger.info("Whisper model loaded.")
    return _model


def transcribe_audio(audio_path: str) -> str:
    """Transcribe an audio file to text."""
    model = _get_model()
    segments, info = model.transcribe(audio_path)
    text = " ".join(s.text for s in segments).strip()
    logger.info("Transcribed %s: lang=%s (%.0f%%), %d chars",
                audio_path, info.language, info.language_probability * 100, len(text))
    return text


def download_and_transcribe(signal_api_url: str, attachment_id: str) -> str:
    """Download an attachment from signal-cli-rest-api and transcribe it."""
    url = f"{signal_api_url.rstrip('/')}/v1/attachments/{attachment_id}"

    with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as tmp:
        tmp_path = tmp.name
        try:
            resp = httpx.get(url, timeout=30)
            resp.raise_for_status()
            tmp.write(resp.content)
            tmp.flush()
            return transcribe_audio(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)
