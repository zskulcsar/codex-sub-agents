# Agents & Skills

This page explains how the Codex sub-agent package discovers agent definitions, wires in skills, and exposes those capabilities to the OpenAI Agents SDK. Use it whenever you need to add a new persona, reason about prompts, or understand how skills become callable tools at runtime.

## Agent Bundle Anatomy

Each agent lives inside `config/agents/<agent-id>/` and ships three core files:

| File | Purpose |
| --- | --- |
| `agent.toml` | Structured fields such as `name`, `model`, `reasoning_tokens`, and `mcp_servers`. |
| `instructions.md` | Long-form guidance that becomes the agent’s system prompt. |
| `entry_message.md` | Default kickoff message that the runner passes to the agent loop when no `--request` override is supplied. |

During `codex_sub_agent.config_loader.load_config`, each directory is parsed into an `AgentSettings` object. The CLI (`codex_sub_agent.cli.AgentBlueprint`) later turns that object into an `Agent`, applying temperature, reasoning token, MCP server, and tool wiring.

### Instructions vs. Entry Message

- **`instructions.md`** should describe the persona’s goals, constraints, and mandatory workflows. The loader trims whitespace and injects a skill summary (see below) so you don’t have to duplicate that prose.
- **`entry_message.md`** is much shorter—think of it as the first user utterance. When you run `codex-sub-agent --run-agent <alias>`, supplying `--request "..."` overrides this entry message only.

## Skill Folders

Agents can opt into first-class skills by creating an adjacent `skills/` directory:

```
config/agents/workflow/
  agent.toml
  instructions.md
  entry_message.md
  skills/
    using_superpowers/
      SKILL.md
      large_skill_file.md
    deep_focus/
      SKILL.md
```

Every skill folder must contain a `SKILL.md` with YAML front matter followed by instructional text:

```markdown
---
name: Deep Focus
description: Stay on the main objective.
tags: [workflow, planning]
---
Always brainstorm before coding and confirm the plan with the user.

WARNING: `large_skill_file.md` consumes ~12k tokens. Only read it when editing long-form prose.
```

Rules worth remembering:

1. Front matter needs at least `name` and `description`. Additional keys (e.g., `tags`, `warning`) become part of the manifest handed to the agent at runtime.
2. The body text (everything after the closing `---`) becomes the full instructions returned by the skill tool when the agent requests it.
3. Any other files inside the skill directory are treated as attachments. Their relative path and size are surfaced to the agent, and their contents stream back only when the caller explicitly asks for the “full” version of the skill.

## How Skills Become Tools

When the loader finds skills, it stores them on `AgentSettings.skills`. Later, `AgentBlueprint.build_agent` turns each skill into a function tool named `skill_<slug>` (sanitized from the folder name). The tool:

- Accepts a single argument, `intent`, which can be `"preview"` (default) or `"full"`.
- Returns JSON containing the manifest, a short preview excerpt, and attachment metadata. When `intent="full"`, the response also includes the complete instructions plus the textual contents of every attachment.

At runtime, OpenAI’s agent loop decides when to call these tools—your `instructions.md` should explicitly tell the model *when* each skill matters (e.g., “Call `skill_using_superpowers` before touching any files”). Because tools are real function calls, the model can defer reading large attachments until it truly needs them, keeping token usage minimal.

## Writing Effective Skills

- **Keep the manifest tight.** Descriptions should be one sentence describing *why* the agent would call the skill. That text feeds both the instructions summary and the tool description.
- **Use attachments sparingly.** Large references belong in separate files with clear warnings in the body text. Your agent can fetch them on demand via `intent="full"` while sticking to the cheaper preview for normal runs.
- **Treat skills as reusable modules.** If multiple agents need the same behavior, copy the skill folder into each agent’s `skills/` directory. Because tool names include the slug, avoid collisions such as `skills/common` and `skills/common_v2` in the same agent.

## Prompt Augmentation

Right after `instructions.md` is read, the loader appends an auto-generated “Available Skills” section similar to:

```
## Available Skills

- **Deep Focus** (tool `skill_deep_focus`): Stay on the main objective. Call the tool with intent='full' to read the entire skill and any attachments.
- **Using Superpowers** (tool `skill_using_superpowers`): Mandatory workflow checklist. Call the tool with intent='full' to see every checklist item.
```

That summary keeps the main prompt current even if skills change frequently, and it teaches the agent which tool names to invoke. You only need to maintain `instructions.md` and the individual `SKILL.md` files—the rest is automatic.

## Capability Checklist

- ✅ Multiple agents per repository; each agent controls its own model settings and MCP servers.
- ✅ Skills automatically appear as tools with preview/full semantics, including attachment streaming.
- ✅ Entry messages remain customizable per run via `--request` or the MCP tool `arguments.request` field.
- ⚙️ Coming soon: helper endpoints for listing and partially reading attachments without pulling the entire file (see project backlog).

By following this structure you ensure every workflow persona gets consistent prompts, easy-to-find skills, and predictable tooling inside the broader Agents SDK runtime.
