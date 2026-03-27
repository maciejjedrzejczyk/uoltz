"""Meta-skill: generates new skills from natural language descriptions.

Uses an LLM agent to produce skill.yaml + Python tool module, then
writes them to disk under app/skills/<name>/.
"""

import logging
import re
from pathlib import Path

from strands import Agent, tool
import config

logger = logging.getLogger(__name__)

SKILLS_DIR = Path("data/custom_skills")  # external, volume-mounted

GENERATOR_PROMPT = """\
You are a skill generator for a Signal AI chatbot built with Strands Agents.

Your job: given a description of a desired skill, produce TWO files that
form a complete, working skill plugin.

CONVENTIONS YOU MUST FOLLOW:

1. Every skill lives in its own folder under app/skills/<skill_name>/
2. The folder contains:
   - skill.yaml (manifest)
   - __init__.py (empty)
   - <module_name>.py (tool implementations)

3. skill.yaml format:
   ```yaml
   name: skill_name
   description: What this skill does.
   version: "1.0.0"
   enabled: true
   tools:
     - "module_name:function_name"
   ```

4. Python module format:
   - Import: `from strands import tool`
   - Each tool is a function decorated with `@tool`
   - The docstring is CRITICAL — the LLM reads it to decide when to use the tool
   - First paragraph = description, then Args section for parameters
   - Use type hints on all parameters
   - Return a string

5. For config access, import: `import config`
   - `config.make_model()` creates an OpenAI-compatible model instance
   - `config.formatting_instruction()` returns the current markdown toggle text
   - `config.llm`, `config.signal`, `config.whisper` for settings

6. For web search, import: `from skills.web_search.search import web_search`

7. Keep it simple. Minimal dependencies. Use only what's in requirements.txt:
   strands-agents[openai], strands-agents-tools, httpx, python-dotenv,
   pyyaml, ddgs, faster-whisper, croniter

8. Skill name must be a valid Python identifier (lowercase, underscores).

OUTPUT FORMAT — respond with EXACTLY this structure, no extra text:

===SKILL_NAME===
<skill_name>
===MODULE_NAME===
<module_name>
===SKILL_YAML===
<complete skill.yaml content>
===MODULE_PY===
<complete Python module content>
===END===
"""


def _parse_output(raw: str) -> dict | None:
    """Parse the structured output from the generator agent."""
    try:
        skill_name = re.search(r"===SKILL_NAME===\s*(.+?)\s*===", raw).group(1).strip()
        module_name = re.search(r"===MODULE_NAME===\s*(.+?)\s*===", raw).group(1).strip()
        skill_yaml = re.search(r"===SKILL_YAML===\s*(.+?)\s*===MODULE_PY===", raw, re.DOTALL).group(1).strip()
        module_py = re.search(r"===MODULE_PY===\s*(.+?)\s*===END===", raw, re.DOTALL).group(1).strip()

        # Clean up markdown code fences if the LLM wrapped them
        for fence in ("```yaml", "```python", "```"):
            skill_yaml = skill_yaml.replace(fence, "")
            module_py = module_py.replace(fence, "")

        return {
            "skill_name": skill_name,
            "module_name": module_name,
            "skill_yaml": skill_yaml.strip(),
            "module_py": module_py.strip(),
        }
    except (AttributeError, IndexError) as e:
        logger.error("Failed to parse generator output: %s", e)
        return None


def _write_skill(parsed: dict) -> Path:
    """Write the generated skill files to disk."""
    skill_dir = SKILLS_DIR / parsed["skill_name"]
    skill_dir.mkdir(parents=True, exist_ok=True)

    (skill_dir / "__init__.py").write_text("")
    (skill_dir / "skill.yaml").write_text(parsed["skill_yaml"] + "\n")
    (skill_dir / f"{parsed['module_name']}.py").write_text(parsed["module_py"] + "\n")

    return skill_dir


@tool
def create_skill(description: str) -> str:
    """Generate a new skill for the bot from a natural language description.

    Use this when the user asks to create, build, or add a new skill/tool
    to the bot. Describe what the skill should do and this tool will generate
    the complete skill folder with all necessary files.

    After creation, the bot needs a restart to load the new skill.

    Args:
        description: A detailed description of what the skill should do,
                     including what tools it should provide and when they
                     should be used.
    """
    logger.info("Generating skill from description: %s", description[:100])

    model = config.make_model()
    generator = Agent(
        name="skill_generator",
        model=model,
        system_prompt=GENERATOR_PROMPT,
    )

    try:
        result = generator(
            f"Create a skill based on this description:\n\n{description}"
        )
        raw = str(result)
    except Exception as e:
        return f"Skill generation failed (LLM error): {e}"

    parsed = _parse_output(raw)
    if parsed is None:
        return (
            "Failed to parse the generated skill. The LLM output didn't match "
            "the expected format. Try rephrasing your description.\n\n"
            f"Raw output:\n{raw[:1000]}"
        )

    # Validate skill name
    if not re.match(r"^[a-z][a-z0-9_]*$", parsed["skill_name"]):
        return f"Invalid skill name: '{parsed['skill_name']}'. Must be lowercase with underscores."

    # Check for conflicts
    if (SKILLS_DIR / parsed["skill_name"]).exists():
        return (
            f"Skill '{parsed['skill_name']}' already exists. "
            f"Delete app/skills/{parsed['skill_name']}/ first or ask for a different name."
        )

    skill_dir = _write_skill(parsed)

    return (
        f"Skill '{parsed['skill_name']}' created at {skill_dir}/\n\n"
        f"Files:\n"
        f"  - skill.yaml\n"
        f"  - __init__.py\n"
        f"  - {parsed['module_name']}.py\n\n"
        f"Restart the bot to load it. The new tools will be auto-discovered."
    )


@tool
def list_skills_on_disk() -> str:
    """List all skill folders currently on disk (including disabled ones).

    Use this to check what skills exist before creating a new one.
    """
    skills = []
    for child in sorted(SKILLS_DIR.iterdir()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        manifest = child / "skill.yaml"
        if manifest.exists():
            import yaml
            data = yaml.safe_load(manifest.read_text())
            status = "enabled" if data.get("enabled", True) else "disabled"
            skills.append(f"  {child.name} ({status}): {data.get('description', 'no description')}")
        else:
            skills.append(f"  {child.name} (no manifest)")

    if not skills:
        return "No skills found on disk."
    return f"Skills on disk ({len(skills)}):\n" + "\n".join(skills)
