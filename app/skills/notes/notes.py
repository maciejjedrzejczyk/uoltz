"""Simple local note-taking tool backed by JSON files."""

import json
from pathlib import Path
from datetime import datetime, timezone
from strands import tool

NOTES_DIR = Path("data/notes")
NOTES_DIR.mkdir(parents=True, exist_ok=True)


def _notes_file() -> Path:
    return NOTES_DIR / "notes.json"


def _load_notes() -> list[dict]:
    f = _notes_file()
    if f.exists():
        return json.loads(f.read_text())
    return []


def _save_notes(notes: list[dict]):
    _notes_file().write_text(json.dumps(notes, indent=2))


@tool
def save_note(title: str, content: str) -> str:
    """Save a note for later reference.

    Use this when the user asks you to remember something, take a note,
    or save information for later.

    Args:
        title: A short title for the note.
        content: The note content.
    """
    notes = _load_notes()
    notes.append({
        "title": title,
        "content": content,
        "created": datetime.now(timezone.utc).isoformat(),
    })
    _save_notes(notes)
    return f"Note saved: '{title}'"


@tool
def list_notes() -> str:
    """List all saved notes.

    Use this when the user asks to see their notes or what has been saved.
    """
    notes = _load_notes()
    if not notes:
        return "No notes saved yet."
    lines = [f"- {n['title']} ({n['created'][:10]})" for n in notes]
    return "\n".join(lines)


@tool
def read_note(title: str) -> str:
    """Read a specific note by title.

    Args:
        title: The title of the note to read (case-insensitive partial match).
    """
    notes = _load_notes()
    for n in notes:
        if title.lower() in n["title"].lower():
            return f"**{n['title']}** ({n['created'][:10]})\n\n{n['content']}"
    return f"No note found matching '{title}'."
