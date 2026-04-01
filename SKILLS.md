# Skills

Skills are auto-discovered from `app/skills/`. Each skill is a folder with a `skill.yaml` manifest and Python tool modules. Use `/skills` in chat to see what's loaded.

## Built-in Skills

| Skill | Tools | Description |
|-------|-------|-------------|
| `web_search` | `web_search` | DuckDuckGo search, no API key needed |
| `research` | `research_topic` | Multi-source web + news search with date verification and AI synthesis. Best for factual lookups: weather, stock prices, current events |
| `brainstorm` | `brainstorm_topic` | Multi-agent brainstorming v2 with domain-aware specialists, fact-checking, YouTube video analysis, RSS feed context, prior brainstorm awareness, and confidence-scored reports. Saves results to `data/brainstorms/` |
| `youtube_summary` | `summarize_youtube` | Extract YouTube transcripts (captions or Whisper fallback) and produce detailed video summaries. Handles long videos via chunked summarization |
| `summarize` | `summarize_content` | Fetch and summarize any URL or raw text. Extracts article content with BeautifulSoup, converts to markdown, produces TLDR + key points |
| `rss_digest` | `rss_digest` | FreshRSS integration — fetches unread articles from monitored feeds (The Register, AWS blogs), summarizes each, marks as read |
| `notes` | `save_note`, `list_notes`, `read_note` | Local JSON-backed note-taking |
| `shell` | `run_shell_command` | Guarded local shell command execution (dangerous commands blocked) |
| `skill_builder` | `create_skill`, `list_skills_on_disk` | Generate new skills from natural language descriptions at runtime. Writes to `data/custom_skills/` for auto-discovery on restart |
| `signal_admin` | 9 tools | Register/verify numbers, link devices, create/delete groups, send messages to individuals and groups |

## Brainstorm Skill (v2)

The brainstorm skill uses a multi-agent Graph pipeline with 8 agents:

```
decomposer ──┬── specialist*   ──┐
             ├── critic        ──┤
             ├── researcher    ──├── fact_checker ──► synthesizer
             ├── pragmatist    ──┤
             └── media_scout   ──┘

* specialist = technical_architect | strategist | creative_director | visionary
  (selected automatically based on topic domain)
```

Key capabilities:

- **Domain-aware specialists** — the decomposer classifies the topic (tech, business, creative, general) and swaps in the appropriate specialist agent
- **Fact-checking** — a dedicated fact-checker agent cross-references claims from all specialists, spot-checks via web search, and marks claims as VERIFIED/UNVERIFIED/DISPUTED
- **YouTube video analysis** — the media scout searches for relevant YouTube videos and extracts transcript insights
- **RSS feed context** — pulls recent articles from FreshRSS feeds into the decomposer's context (if configured)
- **Prior brainstorm awareness** — scans `data/brainstorms/` for past sessions on related topics to avoid rehashing
- **Confidence scoring** — the synthesizer tags each recommendation as HIGH/MEDIUM/LOW confidence based on source verification
- **User context** — accepts an optional `context` parameter (e.g. "solo developer, $5k budget") to tailor advice
- **Temporal grounding** — all agents know today's date to avoid outdated reasoning

Usage: `/brainstorm <topic>` or ask the agent to brainstorm naturally.

## Creating a New Skill

### From the template

1. Copy the template:
   ```bash
   cp -r app/skills/_template app/skills/my_skill
   ```

2. Edit `app/skills/my_skill/skill.yaml`:
   ```yaml
   name: my_skill
   description: What this skill does.
   version: "1.0.0"
   enabled: true
   tools:
     - "my_module:my_tool_function"
   ```

3. Implement your tools in `app/skills/my_skill/my_module.py` using the `@tool` decorator from Strands

4. Restart the bot — skills are auto-discovered from the `app/skills/` directory

Set `enabled: false` in `skill.yaml` to disable a skill without deleting it.

### From natural language (skill_builder)

You can also ask the bot to create a skill for you at runtime:

> "Create a skill that fetches the top Hacker News stories and summarizes them"

The `skill_builder` skill will generate the `skill.yaml` and Python module, write them to `data/custom_skills/`, and the new skill will be available after a restart.

### Skill anatomy

```
app/skills/my_skill/
├── skill.yaml          # Manifest: name, description, tool references
├── __init__.py         # Empty (required for Python imports)
└── my_module.py        # Tool implementations with @tool decorator
```

### skill.yaml reference

```yaml
name: my_skill                          # Must be a valid Python identifier
description: What this skill does.      # Shown in /skills and system prompt
version: "1.0.0"
enabled: true                           # Set false to disable without deleting

tools:                                  # List of "module:function" references
  - "my_module:my_tool_function"

# Optional: register a direct slash command (bypasses LLM routing)
command: /mycommand
command_arg: input_param                # Parameter name to pass user input to
command_usage: "/mycommand <input>"     # Usage hint shown on empty invocation
```

### Tool implementation

```python
from strands import tool

@tool
def my_tool_function(query: str) -> str:
    """Short description of what this tool does.

    Longer description that helps the LLM decide WHEN to use this tool.
    Be specific about the use cases.

    Args:
        query: Description of the parameter.
    """
    # Your implementation here
    return "result"
```

Key conventions:
- The docstring is critical — the LLM reads it to decide when to invoke the tool
- Always return a string
- Use type hints on all parameters
- For config access: `import config` (provides `config.make_model()`, `config.llm`, etc.)
- For web search: `from skills.web_search.search import web_search`
- For formatting: append `config.formatting_instruction()` to sub-agent system prompts

### Discovery locations

Skills are loaded from two directories:

| Location | Purpose |
|----------|---------|
| `app/skills/` | Built-in skills (shipped with the bot) |
| `data/custom_skills/` | External skills (generated by skill_builder, survives container rebuilds) |
