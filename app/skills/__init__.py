"""Auto-discovering skill/tool plugin system.

Each skill lives in its own subdirectory under skills/ and contains:
  - skill.yaml   — manifest with metadata, description, and tool list
  - *.py         — Python modules containing @tool-decorated functions

The registry scans all subdirectories, loads manifests, and collects tools.
To add a new skill: create a folder, add skill.yaml + your tool modules.
"""

from skills.registry import SkillRegistry, discover_skills

__all__ = ["SkillRegistry", "discover_skills"]
