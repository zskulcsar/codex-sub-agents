"""Helpers for turning configuration into runnable Agents and MCP metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from agents import Agent, ModelSettings
import mcp.types as mcp_types

from .config_models import AgentSettings, InvalidConfiguration, SubAgentConfig


@dataclass(frozen=True)
class AgentBlueprint:
    """Immutable recipe for constructing an Agents SDK Agent."""

    agent_id: str
    settings: AgentSettings
    mcp_server_names: list[str]

    def build_agent(self, tools: list[Any], mcp_servers: Iterable[Any]) -> Agent[Any]:
        model_settings = ModelSettings()
        if self.settings.temperature is not None:
            model_settings.temperature = self.settings.temperature
        if self.settings.reasoning_tokens:
            model_settings.max_tokens = self.settings.reasoning_tokens

        return Agent(
            name=self.settings.name,
            instructions=self.settings.instructions,
            model=self.settings.model,
            model_settings=model_settings,
            tools=tools,
            mcp_servers=list(mcp_servers),
        )


@dataclass(frozen=True)
class AgentAliasEntry:
    alias: str
    tool_name: str
    blueprint: AgentBlueprint
    description: str
    expose_in_tools: bool = True


class AgentRegistry:
    """Holds configured agents and exposes aliases for MCP tools and CLI use."""

    def __init__(self, config: SubAgentConfig):
        self.config = config
        agents = config.available_agents()
        self._blueprints: dict[str, AgentBlueprint] = {
            agent_id: AgentBlueprint(
                agent_id=agent_id,
                settings=settings,
                mcp_server_names=list(settings.mcp_servers),
            )
            for agent_id, settings in agents.items()
        }

        if not config.aliases:
            raise InvalidConfiguration("No aliases defined in [aliases]. At least one alias is required.")

        self.tool_entries: dict[str, AgentAliasEntry] = {}
        self.aliases_by_agent: dict[str, list[str]] = {agent_id: [] for agent_id in agents}
        used_tool_names: set[str] = set()

        for alias, agent_id in config.aliases.items():
            blueprint = self._blueprints.get(agent_id)
            if blueprint is None:
                raise InvalidConfiguration(f"Alias '{alias}' references unknown agent '{agent_id}'.")
            tool_name = self._make_tool_name(alias, used_tool_names)
            used_tool_names.add(tool_name)
            entry = AgentAliasEntry(
                alias=alias,
                tool_name=tool_name,
                blueprint=blueprint,
                description=self._summarize_agent(blueprint),
                expose_in_tools=True,
            )
            self.tool_entries[tool_name] = entry
            self.aliases_by_agent[agent_id].append(alias)

        self.cli_aliases: dict[str, AgentAliasEntry] = {}
        for entry in self.tool_entries.values():
            self.cli_aliases[entry.alias] = entry
            self.cli_aliases[entry.tool_name] = entry

        for agent_id, blueprint in self._blueprints.items():
            if agent_id not in self.cli_aliases:
                fallback_tool = self._make_tool_name(agent_id, used_tool_names)
                entry = AgentAliasEntry(
                    alias=agent_id,
                    tool_name=fallback_tool,
                    blueprint=blueprint,
                    description=self._summarize_agent(blueprint),
                    expose_in_tools=False,
                )
                self.cli_aliases[agent_id] = entry
                self.cli_aliases[fallback_tool] = entry

        self.tool_definitions: list[mcp_types.Tool] = [
            mcp_types.Tool(
                name=entry.tool_name,
                description=entry.description,
                inputSchema={
                    "type": "object",
                    "properties": {
                        "request": {
                            "type": "string",
                            "description": "Optional override for the agent's entry message.",
                        }
                    },
                    "additionalProperties": False,
                },
            )
            for entry in sorted(self.tool_entries.values(), key=lambda e: e.tool_name)
        ]

    def resolve_tool_name(self, tool_name: str) -> AgentAliasEntry:
        if tool_name not in self.tool_entries:
            raise InvalidConfiguration(f"Unknown tool '{tool_name}'.")
        return self.tool_entries[tool_name]

    def resolve_cli_alias(self, alias: str) -> AgentAliasEntry:
        if alias not in self.cli_aliases:
            raise InvalidConfiguration(f"Unknown agent '{alias}'. Available: {', '.join(sorted(self.cli_aliases))}")
        return self.cli_aliases[alias]

    def iter_agent_summaries(self):
        for agent_id, blueprint in sorted(self._blueprints.items()):
            yield agent_id, blueprint.settings, sorted(self.aliases_by_agent.get(agent_id, []))

    @staticmethod
    def _summarize_agent(blueprint: AgentBlueprint) -> str:
        primary_line = blueprint.settings.instructions.strip().splitlines()[0].strip()
        if len(primary_line) > 200:
            primary_line = primary_line[:197].rstrip() + "..."
        return f"{blueprint.settings.name}: {primary_line}"

    @staticmethod
    def _make_tool_name(alias: str, used: set[str]) -> str:
        sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", alias)
        sanitized = sanitized.strip("_") or "agent"
        candidate = sanitized
        index = 2
        while candidate in used:
            candidate = f"{sanitized}_{index}"
            index += 1
        if not re.fullmatch(r"[A-Za-z0-9_-]+", candidate):
            raise InvalidConfiguration(f"Cannot derive a valid tool name from alias '{alias}'.")
        return candidate


__all__ = ["AgentAliasEntry", "AgentBlueprint", "AgentRegistry"]
