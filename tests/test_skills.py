"""Tests for the skills runtime helpers."""

import asyncio
import json
from pathlib import Path

from codex_sub_agent.skills import AgentSkill, AgentSkillAttachment, render_skill_section


def test_agent_skill_tool_preview_and_full(tmp_path: Path) -> None:
    attachment_path = tmp_path / "skill" / "note.txt"
    attachment_path.parent.mkdir(parents=True, exist_ok=True)
    attachment_path.write_text("Extended details", encoding="utf-8")

    skill = AgentSkill(
        slug="deep_focus",
        name="Deep Focus",
        description="Stay on the main goal",
        instructions="Always brainstorm before touching files.",
        directory=attachment_path.parent,
        attachments=[
            AgentSkillAttachment(
                filename="note.txt",
                relative_path="note.txt",
                absolute_path=attachment_path,
                size_bytes=attachment_path.stat().st_size,
            )
        ],
    )

    tool = skill.build_tool()

    async def _call(intent: str) -> dict:
        return json.loads(await tool.on_invoke_tool(None, json.dumps({"intent": intent})))

    preview = asyncio.run(_call("preview"))
    assert preview["skill"]["name"] == "Deep Focus"
    assert "instructions" not in preview

    full = asyncio.run(_call("full"))
    assert full["instructions"].startswith("Always")
    assert "attachment_contents" in full


def test_render_skill_section_lists_tools(tmp_path: Path) -> None:
    skill = AgentSkill(
        slug="deploy",
        name="Deploy",
        description="Release process",
        instructions="Follow the release checklist.",
        directory=tmp_path,
    )

    rendered = render_skill_section([skill])
    assert "Deploy" in rendered
    assert "skill_deploy" in rendered
