"""Skill registry: auto-discovers and loads skill plugins from subdirectories.

Scans two locations:
  1. Built-in: app/skills/  (shipped with the bot)
  2. External: data/custom_skills/  (volume-mounted, survives container rebuilds)
"""

import importlib
import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

BUILTIN_SKILLS_DIR = Path(__file__).parent
EXTERNAL_SKILLS_DIR = Path("data/custom_skills")


@dataclass
class SkillManifest:
    """Parsed skill.yaml metadata."""

    name: str
    description: str
    version: str = "0.1.0"
    enabled: bool = True
    tools: list[str] = field(default_factory=list)
    # Optional direct slash command (e.g. "/summarize")
    command: str | None = None
    # Which parameter name to pass user input to (e.g. "content", "topic", "query")
    command_arg: str | None = None
    # Usage hint shown when command is called without args
    command_usage: str | None = None


@dataclass
class DirectCommand:
    """A resolved direct slash command pointing to a tool function."""
    command: str          # e.g. "/summarize"
    skill_name: str
    func: callable
    arg_name: str | None  # parameter name for user input, None = no args
    usage: str | None


@dataclass
class SkillRegistry:
    """Holds all discovered skills and their collected tool functions."""

    skills: list[SkillManifest] = field(default_factory=list)
    tools: list = field(default_factory=list)
    commands: dict[str, DirectCommand] = field(default_factory=dict)  # "/cmd" → DirectCommand

    def summary(self) -> str:
        """Return a human-readable summary for the system prompt."""
        if not self.skills:
            return "No skills loaded."
        lines = []
        for s in self.skills:
            cmd = f" (command: {s.command})" if s.command else ""
            lines.append(f"- {s.name} (v{s.version}): {s.description}{cmd}")
        return "\n".join(lines)

    def commands_help(self) -> str:
        """Return formatted help text for all direct commands."""
        if not self.commands:
            return ""
        lines = []
        for cmd_name, dc in sorted(self.commands.items()):
            usage = dc.usage or f"{cmd_name} <input>"
            lines.append(f"  {usage}  —  {dc.skill_name}")
        return "\n".join(lines)


def _load_manifest(skill_dir: Path) -> SkillManifest | None:
    """Load and parse a skill.yaml manifest."""
    manifest_path = skill_dir / "skill.yaml"
    if not manifest_path.exists():
        logger.warning("Skipping %s — no skill.yaml found", skill_dir.name)
        return None

    try:
        data = yaml.safe_load(manifest_path.read_text())
        return SkillManifest(
            name=data["name"],
            description=data.get("description", ""),
            version=data.get("version", "0.1.0"),
            enabled=data.get("enabled", True),
            tools=data.get("tools", []),
            command=data.get("command"),
            command_arg=data.get("command_arg"),
            command_usage=data.get("command_usage"),
        )
    except Exception as e:
        logger.error("Failed to load manifest %s: %s", manifest_path, e)
        return None


def _resolve_tool(skill_dir: Path, tool_ref: str, is_external: bool = False):
    """Resolve a 'module:function' reference to an actual callable.

    For built-in skills: uses dotted import (skills.<dir>.<module>)
    For external skills: uses importlib.util to load from file path
    """
    module_name, func_name = tool_ref.split(":")

    if is_external:
        # Load directly from file path for external skills
        module_path = skill_dir / f"{module_name}.py"
        if not module_path.exists():
            logger.error("Module file not found: %s", module_path)
            return None
        try:
            spec_name = f"custom_skills.{skill_dir.name}.{module_name}"
            spec = importlib.util.spec_from_file_location(spec_name, module_path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec_name] = mod
            spec.loader.exec_module(mod)
            return getattr(mod, func_name)
        except Exception as e:
            logger.error("Failed to load external tool %s from %s: %s", tool_ref, skill_dir.name, e)
            return None
    else:
        # Standard dotted import for built-in skills
        dotted = f"skills.{skill_dir.name}.{module_name}"
        try:
            mod = importlib.import_module(dotted)
            return getattr(mod, func_name)
        except Exception as e:
            logger.error("Failed to resolve tool %s from %s: %s", tool_ref, skill_dir.name, e)
            return None


def _scan_directory(base: Path, registry: SkillRegistry, is_external: bool = False):
    """Scan a single directory for skill subdirectories."""
    if not base.is_dir():
        return

    label = "external" if is_external else "built-in"
    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue

        manifest = _load_manifest(child)
        if manifest is None:
            continue
        if not manifest.enabled:
            logger.info("Skill '%s' (%s) is disabled, skipping", manifest.name, label)
            continue

        loaded_tools = []
        for tool_ref in manifest.tools:
            tool_func = _resolve_tool(child, tool_ref, is_external=is_external)
            if tool_func is not None:
                loaded_tools.append(tool_func)

        registry.skills.append(manifest)
        registry.tools.extend(loaded_tools)

        # Register direct command if declared
        if manifest.command and loaded_tools:
            cmd = manifest.command if manifest.command.startswith("/") else f"/{manifest.command}"
            registry.commands[cmd.lower()] = DirectCommand(
                command=cmd.lower(),
                skill_name=manifest.name,
                func=loaded_tools[0],  # command invokes the first tool
                arg_name=manifest.command_arg,
                usage=manifest.command_usage,
            )
            logger.info("  Registered command: %s → %s", cmd, manifest.name)

        logger.info("Loaded %s skill '%s' with %d tool(s)", label, manifest.name, len(loaded_tools))


def discover_skills() -> SkillRegistry:
    """Scan built-in and external skill directories and load all enabled skills."""
    registry = SkillRegistry()

    _scan_directory(BUILTIN_SKILLS_DIR, registry, is_external=False)
    _scan_directory(EXTERNAL_SKILLS_DIR, registry, is_external=True)

    logger.info(
        "Skill discovery complete: %d skill(s), %d tool(s) total",
        len(registry.skills),
        len(registry.tools),
    )
    return registry
