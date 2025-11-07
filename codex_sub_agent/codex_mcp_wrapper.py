"""Wrapper that launches `npx codex mcp` while filtering Codex-only notifications."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import List


def main(argv: List[str] | None = None) -> int:
    """Proxy `codex mcp-server` while stripping Codex-only notifications.

    Args:
        argv: Optional CLI argument override used during testing.

    Returns:
        Exit code from the underlying `codex mcp-server` process.
    """
    argv = argv or sys.argv[1:]
    command = ["npx", "-y", "codex", "mcp-server", *argv]

    process = subprocess.Popen(
        command,
        stdin=sys.stdin,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        bufsize=1,
    )

    assert process.stdout is not None

    try:
        for line in process.stdout:
            stripped = line.strip()
            if not stripped:
                continue

            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                print(line, end="")
                continue

            if payload.get("method") == "codex/event":
                # Codex CLI emits telemetry via `codex/event`; the python MCP client
                # rejects unknown notification types, so we silently drop them here.
                continue

            print(line, end="")
    finally:
        if process.stdin:
            process.stdin.close()
        process.wait()

    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
