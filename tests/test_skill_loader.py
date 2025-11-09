"""Tests for reading skill metadata from disk."""

from pathlib import Path

import pytest

from codex_sub_agent.skill_loader import load_agent_skills
from codex_sub_agent.config_models import InvalidConfiguration


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_load_agent_skills_parses_manifest(tmp_path: Path) -> None:
    agent_dir = tmp_path / "agents" / "workflow"
    skill_dir = agent_dir / "skills" / "deep_focus"
    _write(
        skill_dir / "SKILL.md",
        """---
name: Deep Focus
description: Stay on task
---
Always plan before coding.
""",
    )
    _write(skill_dir / "extra.txt", "Aux guidance")

    skills = load_agent_skills(agent_dir)
    assert len(skills) == 1
    skill = skills[0]
    assert skill.slug == "deep_focus"
    assert skill.attachments[0].filename == "extra.txt"


def test_load_agent_skills_requires_frontmatter(tmp_path: Path) -> None:
    agent_dir = tmp_path / "agents" / "workflow"
    skill_dir = agent_dir / "skills" / "broken"
    _write(skill_dir / "SKILL.md", "name: Missing separators")

    with pytest.raises(InvalidConfiguration):
        load_agent_skills(agent_dir)
