"""YouTube summary skill — extract transcript and summarize video content."""

import logging
import re
import tempfile
from pathlib import Path

from strands import Agent, tool
import config

logger = logging.getLogger(__name__)

_YT_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]{11})"
)

CHUNK_SIZE = 8000  # chars per transcript chunk for summarization


def _extract_url(text: str) -> str | None:
    """Pull the first YouTube URL from input text."""
    m = _YT_PATTERN.search(text)
    return m.group(0) if m else None


def _get_transcript_captions(url: str) -> str | None:
    """Try to get subtitles/captions via yt-dlp (no audio download)."""
    import yt_dlp

    with tempfile.TemporaryDirectory() as tmp:
        out_path = str(Path(tmp) / "subs")
        opts = {
            "skip_download": True,
            "writeautomaticsub": True,
            "writesubtitles": True,
            "subtitleslangs": ["en", "en-orig"],
            "subtitlesformat": "vtt",
            "outtmpl": out_path,
            "quiet": True,
            "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as e:
            logger.warning("Caption extraction failed: %s", e)
            return None

        # Find any downloaded subtitle file
        for vtt in Path(tmp).glob("*.vtt"):
            raw = vtt.read_text()
            # Strip VTT headers and timestamps, keep only text lines
            lines = []
            for line in raw.splitlines():
                line = line.strip()
                if not line or line.startswith("WEBVTT") or line.startswith("Kind:") \
                        or line.startswith("Language:") or "-->" in line or line.isdigit():
                    continue
                # Remove VTT tags like <c> </c>
                line = re.sub(r"<[^>]+>", "", line)
                if line and (not lines or line != lines[-1]):
                    lines.append(line)
            if lines:
                logger.info("Extracted captions: %d chars", sum(len(l) for l in lines))
                return " ".join(lines)
    return None


def _transcribe_audio(url: str) -> str:
    """Download audio and transcribe with Whisper."""
    import yt_dlp
    from transcribe import transcribe_audio

    with tempfile.TemporaryDirectory() as tmp:
        out_path = str(Path(tmp) / "audio.%(ext)s")
        opts = {
            "format": "bestaudio/best",
            "outtmpl": out_path,
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        audio_file = next(Path(tmp).glob("audio.*"), None)
        if not audio_file:
            raise RuntimeError("yt-dlp did not produce an audio file")

        logger.info("Transcribing audio: %s", audio_file)
        return transcribe_audio(str(audio_file))


def _chunk_text(text: str, size: int = CHUNK_SIZE) -> list[str]:
    """Split text into chunks at sentence boundaries."""
    if len(text) <= size:
        return [text]

    chunks, start = [], 0
    while start < len(text):
        end = start + size
        if end >= len(text):
            chunks.append(text[start:])
            break
        # Try to break at a sentence boundary
        boundary = text.rfind(". ", start, end)
        if boundary <= start:
            boundary = text.rfind(" ", start, end)
        if boundary <= start:
            boundary = end
        else:
            boundary += 1  # include the period/space
        chunks.append(text[start:boundary])
        start = boundary
    return chunks


def _summarize_text(text: str, context: str = "") -> str:
    """Summarize a piece of text using a sub-agent."""
    model = config.make_model()
    agent = Agent(
        name="yt-summarizer",
        model=model,
        system_prompt=(
            "You are a precise summarizer of video transcripts. "
            "Capture ALL key points, arguments, examples, and details. "
            "Do not omit information. Be thorough but concise."
            + config.formatting_instruction()
        ),
    )
    prompt = f"{context}Summarize this transcript section:\n\n{text}"
    return str(agent(prompt))


@tool
def summarize_youtube(url: str) -> str:
    """Summarize a YouTube video by extracting its transcript and producing a detailed summary.

    Use this when the user shares a YouTube link and wants to know what the
    video is about, wants a summary, recap, or TLDR of a YouTube video.

    Args:
        url: A YouTube video URL.
    """
    yt_url = _extract_url(url) or url.strip()
    logger.info("Processing YouTube video: %s", yt_url)

    # Step 1: Get transcript — prefer captions, fall back to Whisper
    transcript = _get_transcript_captions(yt_url)
    source = "captions"
    if not transcript:
        logger.info("No captions found, falling back to Whisper transcription")
        try:
            transcript = _transcribe_audio(yt_url)
            source = "whisper"
        except Exception as e:
            return f"Failed to get transcript: {e}"

    if not transcript or not transcript.strip():
        return "Could not extract any transcript from this video."

    logger.info("Transcript ready (%s): %d chars", source, len(transcript))

    # Step 2: Chunk and summarize
    chunks = _chunk_text(transcript)

    if len(chunks) == 1:
        return _summarize_text(chunks[0])

    # Summarize each chunk, then merge
    logger.info("Long transcript — splitting into %d chunks", len(chunks))
    chunk_summaries = []
    for i, chunk in enumerate(chunks):
        logger.info("Summarizing chunk %d/%d", i + 1, len(chunks))
        summary = _summarize_text(
            chunk,
            context=f"This is part {i + 1} of {len(chunks)} of a video transcript. ",
        )
        chunk_summaries.append(summary)

    # Final merge pass
    merged = "\n\n---\n\n".join(
        f"[Part {i + 1}]\n{s}" for i, s in enumerate(chunk_summaries)
    )
    logger.info("Producing final merged summary")
    return _summarize_text(
        merged,
        context=(
            f"Below are summaries of {len(chunks)} consecutive parts of a single "
            "YouTube video. Combine them into one cohesive, detailed summary that "
            "covers everything. "
        ),
    )
