"""Skill metadata structures and helpers for registering function tools."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from agents import function_tool
from agents.tool import FunctionTool
from pydantic import BaseModel, Field


class AgentSkillAttachment(BaseModel):
    """Metadata describing optional files bundled with a skill."""

    filename: str
    relative_path: str
    absolute_path: Path
    size_bytes: int

    def read_text(self) -> str:
        """Return the attachment contents, assuming UTF-8 text."""

        return self.absolute_path.read_text(encoding="utf-8")


class AgentSkill(BaseModel):
    """Runtime representation of an agent skill and its assets."""

    slug: str
    name: str
    description: str
    instructions: str
    directory: Path
    attachments: list[AgentSkillAttachment] = Field(default_factory=list)

    @property
    def tool_name(self) -> str:
        """Return a sanitized function tool name derived from the slug."""

        sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", self.slug).strip("_") or "skill"
        return f"skill_{sanitized}" if not sanitized.startswith("skill_") else sanitized

    def preview_excerpt(self, limit: int = 500) -> str:
        """Return a trimmed preview of the instructions for lightweight calls."""

        text = self.instructions.strip()
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    def build_tool(self) -> FunctionTool:
        """Create a function tool that exposes this skill to the agent loop."""

        description = f"{self.description} (skill: {self.name})"

        @function_tool(name_override=self.tool_name, description_override=description)
        def use_skill(intent: Literal["preview", "full"] = "preview") -> str:
            if intent not in {"preview", "full"}:
                raise ValueError("intent must be 'preview' or 'full'.")

            include_full = intent == "full"
            payload: dict[str, object] = {
                "skill": {
                    "slug": self.slug,
                    "name": self.name,
                    "description": self.description,
                },
                "preview": self.preview_excerpt(),
                "attachments": [
                    {
                        "filename": attachment.filename,
                        "relative_path": attachment.relative_path,
                        "size_bytes": attachment.size_bytes,
                        "available_via": "intent='full'",
                    }
                    for attachment in self.attachments
                ],
            }

            if include_full:
                payload["instructions"] = self.instructions
                if self.attachments:
                    payload["attachment_contents"] = {
                        attachment.relative_path: attachment.read_text() for attachment in self.attachments
                    }

            return json.dumps(payload, indent=2)

        return use_skill


def render_skill_section(skills: list[AgentSkill]) -> str:
    """Render an instructional section summarizing available skills."""

    if not skills:
        return ""

    lines = ["", "## Available Skills", ""]
    for skill in skills:
        lines.append(
            f"- **{skill.name}** (tool `{skill.tool_name}`): {skill.description} "
            "Call the tool with intent='full' to read the entire skill and any attachments."
        )
    return "\n".join(lines)
