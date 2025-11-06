"""Codex sub-agent package."""

from importlib import metadata

__all__ = ["__version__"]

try:
    __version__ = metadata.version("codex-sub-agent")
except metadata.PackageNotFoundError:  # pragma: no cover - during local dev
    __version__ = "0.0.0"
