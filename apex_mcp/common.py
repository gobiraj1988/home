"""Shared helpers used across all APEX MCP servers.

Provides logging setup, safe path resolution (to keep the RAG server inside
its sandbox), and small formatting utilities for returning tidy text/markdown
to Claude.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from .config import settings

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger. Logs go to stderr so they never corrupt the
    stdio JSON-RPC stream that MCP uses on stdout."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()  # defaults to stderr
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, settings.log_level, logging.INFO))
        logger.propagate = False
    return logger


# --------------------------------------------------------------------------- #
# Sandboxed path resolution
# --------------------------------------------------------------------------- #


class PathOutsideSandboxError(ValueError):
    """Raised when a requested path escapes the configured data directory."""


def safe_resolve(relative_or_abs: str, *, base: Path | None = None) -> Path:
    """Resolve ``relative_or_abs`` and guarantee the result stays inside the
    sandbox ``base`` (defaults to ``settings.data_dir``).

    Prevents path-traversal (``../../etc/passwd``) from reaching outside the
    research-docs folder.
    """
    base = (base or settings.data_dir).resolve()
    candidate = Path(relative_or_abs)
    resolved = candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()
    if base != resolved and base not in resolved.parents:
        raise PathOutsideSandboxError(
            f"Path '{relative_or_abs}' is outside the allowed data directory '{base}'."
        )
    return resolved


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #


def human_bytes(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PB"


def markdown_table(rows: Iterable[dict[str, Any]], columns: list[str] | None = None) -> str:
    """Render a list of dicts as a GitHub-flavoured markdown table."""
    rows = list(rows)
    if not rows:
        return "_(no rows)_"
    columns = columns or list(rows[0].keys())
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = "\n".join(
        "| " + " | ".join(str(row.get(c, "")) for c in columns) + " |" for row in rows
    )
    return "\n".join([header, sep, body])
