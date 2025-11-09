"""Helpers for loading agent-specific skills from disk."""

from __future__ import annotations

from pathlib import Path

from .skills import AgentSkill, AgentSkillAttachment
from .config_models import InvalidConfiguration


def _strip_quotes(value: str) -> str:
    """Return ``value`` without surrounding single or double quotes.

    Args:
        value: Raw string extracted from the manifest line.

    Returns:
        The trimmed string with matching quotes removed.
    """

    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def _parse_skill_manifest(lines: list[str], skill_file: Path) -> dict[str, str]:
    """Convert a YAML-like frontmatter block into a manifest dictionary.

    Args:
        lines: Frontmatter lines located between the `---` delimiters.
        skill_file: Path to the skill file currently being parsed (used for errors).

    Returns:
        A dictionary containing at least the ``name`` and ``description`` keys.

    Raises:
        InvalidConfiguration: If mandatory keys are missing or malformed.
    """

    manifest: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise InvalidConfiguration(
                f"Skill file {skill_file} manifest lines must use 'key: value' syntax."
            )
        key, value = line.split(":", 1)
        manifest[key.strip()] = _strip_quotes(value)

    for required in ("name", "description"):
        if not manifest.get(required):
            raise InvalidConfiguration(
                f"Skill file {skill_file} must declare '{required}' in the manifest."
            )
    return manifest


def _split_skill_file(content: str, skill_file: Path) -> tuple[dict[str, str], str]:
    """Separate a skill file into manifest metadata and instructional text.

    Args:
        content: Entire contents of ``SKILL.md``.
        skill_file: Path used for more descriptive error messages.

    Returns:
        Tuple of (manifest, instruction_body).

    Raises:
        InvalidConfiguration: If the frontmatter is missing, malformed, or contains no body.
    """

    text = content.lstrip()
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise InvalidConfiguration(
            f"Skill file {skill_file} must begin with a frontmatter block delimited by '---'."
        )

    closing_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing_index = index
            break
    if closing_index is None:
        raise InvalidConfiguration(
            f"Skill file {skill_file} frontmatter is missing a closing '---' delimiter."
        )

    manifest_lines = lines[1:closing_index]
    manifest = _parse_skill_manifest(manifest_lines, skill_file)
    body = "\n".join(lines[closing_index + 1 :]).strip()
    if not body:
        raise InvalidConfiguration(f"Skill file {skill_file} must include instructional content after the manifest.")
    return manifest, body


def load_agent_skills(agent_path: Path) -> list[AgentSkill]:
    """Load every skill under ``agent_path/skills``.

    Args:
        agent_path: Directory containing the agent bundle.

    Returns:
        List of :class:`AgentSkill` instances discovered beneath the agent.

    Raises:
        InvalidConfiguration: If a skill directory exists without a ``SKILL.md`` file.
    """

    skills_parent = agent_path / "skills"
    if not skills_parent.is_dir():
        return []

    skills: list[AgentSkill] = []
    for skill_dir in sorted(p for p in skills_parent.iterdir() if p.is_dir()):
        skill_file = skill_dir / "SKILL.md"
        try:
            content = skill_file.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise InvalidConfiguration(f"Skill directory {skill_dir} is missing SKILL.md.") from exc

        manifest, body = _split_skill_file(content, skill_file)
        attachments: list[AgentSkillAttachment] = []
        for candidate in sorted(path for path in skill_dir.rglob("*") if path.is_file()):
            if candidate.name == "SKILL.md":
                continue
            rel_path = candidate.relative_to(skill_dir)
            attachments.append(
                AgentSkillAttachment(
                    filename=candidate.name,
                    relative_path=str(rel_path),
                    absolute_path=candidate,
                    size_bytes=candidate.stat().st_size,
                )
            )

        skills.append(
            AgentSkill(
                slug=skill_dir.name,
                name=manifest["name"],
                description=manifest["description"],
                instructions=body,
                directory=skill_dir,
                attachments=attachments,
            )
        )

    return skills


__all__ = ["load_agent_skills"]
