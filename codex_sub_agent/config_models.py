"""Core data models shared across configuration loading and runtime."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class OpenAISettings(BaseModel):
    """OpenAI platform settings that apply to every sub-agent run."""

    api_key_env_var: str = Field(default="OPENAI_API_KEY")
    default_api: Literal["responses", "chat_completions"] = Field(default="responses")


class AgentSettings(BaseModel):
    """Concrete configuration for a single sub-agent role."""

    name: str
    model: str = Field(default="gpt-5")
    instructions: str
    default_prompt: str
    temperature: float | None = Field(default=None)
    reasoning_tokens: int | None = Field(default=None)
    mcp_servers: list[str] = Field(default_factory=list)
    skills: list["AgentSkill"] = Field(default_factory=list)


class MCPStdioConfig(BaseModel):
    """Definition for launching an MCP server over stdio."""

    type: Literal["stdio"]
    name: str
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    client_session_timeout_seconds: float = Field(default=300.0)


class MCPHttpConfig(BaseModel):
    """Definition for connecting to an MCP server over HTTP(S)."""

    type: Literal["http"]
    name: str
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    bearer_token_env_var: str | None = None
    client_session_timeout_seconds: float = Field(default=60.0)


MCPConfig = MCPStdioConfig | MCPHttpConfig


class SubAgentConfig(BaseModel):
    """Aggregate data model describing all sub-agent runtime requirements."""

    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    agent: AgentSettings | None = None
    agents: dict[str, AgentSettings] = Field(default_factory=dict)
    default_agent_id: str | None = None
    aliases: dict[str, str] = Field(default_factory=dict)
    mcp_servers: dict[str, MCPConfig] = Field(default_factory=dict)

    model_config = {"use_enum_values": True, "populate_by_name": True}

    def _agent_map(self) -> dict[str, AgentSettings]:
        mapping: dict[str, AgentSettings] = dict(self.agents)
        if self.agent is not None:
            mapping.setdefault("default", self.agent)
        return mapping

    def available_agents(self) -> dict[str, AgentSettings]:
        agents = self._agent_map()
        if not agents:
            raise InvalidConfiguration("Configuration must define at least one agent.")
        return agents

    def resolve_agent(self, agent_id: str | None) -> tuple[str, AgentSettings]:
        agents = self.available_agents()
        if agent_id:
            resolved_id = self.aliases.get(agent_id, agent_id)
            if resolved_id not in agents:
                raise InvalidConfiguration(
                    f"Agent '{agent_id}' not found. Available agents: {', '.join(sorted(agents))}"
                )
            return resolved_id, agents[resolved_id]

        if self.default_agent_id:
            if self.default_agent_id not in agents:
                raise InvalidConfiguration(
                    f"default_agent '{self.default_agent_id}' is not defined in agents."
                )
            return self.default_agent_id, agents[self.default_agent_id]

        chosen = sorted(agents)[0]
        return chosen, agents[chosen]


class InvalidConfiguration(Exception):
    """Raised when the configuration file cannot be parsed."""


from .skills import AgentSkill  # noqa: E402  (circular-friendly import)

__all__ = [
    "AgentSettings",
    "InvalidConfiguration",
    "MCPConfig",
    "MCPHttpConfig",
    "MCPStdioConfig",
    "OpenAISettings",
    "SubAgentConfig",
]
