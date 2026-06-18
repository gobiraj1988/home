"""Central configuration for the APEX Quant MCP servers.

All settings are read from environment variables (optionally loaded from a
``.env`` file sitting next to the project root). Import :data:`settings` and
read attributes; never read ``os.environ`` directly elsewhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (parent of this package) if present.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    """Resolved configuration for every APEX MCP server."""

    # --- Filesystem RAG ---
    data_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("APEX_DATA_DIR", str(Path.home() / "APEX_AGI_Forex_Trading_Bot"))
        )
    )
    index_dir: Path | None = field(
        default_factory=lambda: (
            Path(os.environ["APEX_INDEX_DIR"]) if os.getenv("APEX_INDEX_DIR") else None
        )
    )
    rag_extensions: list[str] = field(
        default_factory=lambda: _split_csv(
            os.getenv("APEX_RAG_EXTENSIONS", ".md,.txt,.pdf,.docx,.csv")
        )
    )

    # --- MT5 ---
    mt5_login: str = field(default_factory=lambda: os.getenv("MT5_LOGIN", ""))
    mt5_password: str = field(default_factory=lambda: os.getenv("MT5_PASSWORD", ""))
    mt5_server: str = field(default_factory=lambda: os.getenv("MT5_SERVER", ""))
    mt5_terminal_path: str = field(
        default_factory=lambda: os.getenv("MT5_TERMINAL_PATH", "")
    )

    # --- Zapier sharing ---
    zapier_webhook_url: str = field(
        default_factory=lambda: os.getenv("ZAPIER_WEBHOOK_URL", "")
    )
    zapier_file_webhook_url: str = field(
        default_factory=lambda: os.getenv("ZAPIER_FILE_WEBHOOK_URL", "")
    )

    # --- Logging ---
    log_level: str = field(
        default_factory=lambda: os.getenv("APEX_LOG_LEVEL", "INFO").upper()
    )

    @property
    def resolved_index_dir(self) -> Path:
        """Directory where the RAG index is persisted."""
        return self.index_dir or (self.data_dir / ".apex_index")

    @property
    def file_webhook(self) -> str:
        """Webhook used for file uploads, falling back to the main one."""
        return self.zapier_file_webhook_url or self.zapier_webhook_url


settings = Settings()
