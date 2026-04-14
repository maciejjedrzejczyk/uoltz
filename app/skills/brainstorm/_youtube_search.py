"""YouTube transcript extraction tool for the brainstorm media_scout agent."""

import logging
from strands import tool

logger = logging.getLogger(__name__)

MAX_TRANSCRIPT_CHARS = 6000


@tool
def youtube_search(url: str) -> str:
    """Extract the transcript from a YouTube video URL.

    Use this to get the spoken content of a YouTube video for analysis.
    Pass a YouTube URL and receive the transcript text.

    Args:
        url: A YouTube video URL.
    """
    from skills.youtube_summary.youtube import _extract_url, _get_transcript_captions

    yt_url = _extract_url(url) or url.strip()
    logger.info("Extracting transcript for brainstorm: %s", yt_url)

    transcript = _get_transcript_captions(yt_url)
    if not transcript:
        return f"Could not extract transcript from {yt_url}"

    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        transcript = transcript[:MAX_TRANSCRIPT_CHARS] + "\n\n[... transcript truncated]"

    return f"Transcript from {yt_url}:\n\n{transcript}"
