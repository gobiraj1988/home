"""Smoke tests for APEX Quant MCP.

These check the things we can verify without MetaTrader5, a live terminal, or a
configured Zapier webhook: config loading, sandbox path safety, formatting
helpers, and that each server module imports and exposes a ``main`` callable.
"""

from __future__ import annotations

import importlib

import pytest


def test_config_loads():
    from apex_mcp.config import settings

    assert settings.data_dir is not None
    assert isinstance(settings.rag_extensions, list)
    assert settings.resolved_index_dir is not None


def test_safe_resolve_blocks_traversal():
    from apex_mcp.common import PathOutsideSandboxError, safe_resolve

    with pytest.raises(PathOutsideSandboxError):
        safe_resolve("../../../../etc/passwd")


def test_markdown_table():
    from apex_mcp.common import markdown_table

    out = markdown_table([{"a": 1, "b": 2}], ["a", "b"])
    assert "| a | b |" in out
    assert "| 1 | 2 |" in out


def test_human_bytes():
    from apex_mcp.common import human_bytes

    assert human_bytes(0).endswith("B")
    assert "KB" in human_bytes(2048)


@pytest.mark.parametrize(
    "module",
    ["apex_mcp.rag_server", "apex_mcp.mt5_server", "apex_mcp.share_server"],
)
def test_server_modules_have_main(module):
    """Each server imports cleanly and exposes a callable main().

    Skips gracefully if optional heavy deps (mcp/pandas/etc.) aren't installed
    in this environment — the point is to catch import-time bugs when they are.
    """
    try:
        mod = importlib.import_module(module)
    except ImportError as exc:  # missing optional dep in this env
        pytest.skip(f"optional dependency not installed: {exc}")
    assert callable(getattr(mod, "main", None)), f"{module} must expose main()"
