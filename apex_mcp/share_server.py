"""APEX Share MCP server.

Lets Claude auto-share APEX backtest results and report files with the team via
a single Zapier "Catch Hook" webhook. The user wires a Zap whose trigger is
"Webhooks by Zapier -> Catch Hook" and fans the payload out to Slack (post a
message) and Google Drive (upload a file). This server therefore handles **no**
Slack/Drive API credentials of its own -- it only POSTs structured JSON to the
configured webhook URL(s).

Configuration (see :mod:`apex_mcp.config`):
- ``ZAPIER_WEBHOOK_URL``      -> ``settings.zapier_webhook_url`` (messages + results)
- ``ZAPIER_FILE_WEBHOOK_URL`` -> ``settings.zapier_file_webhook_url`` (file uploads;
  falls back to the main webhook via ``settings.file_webhook``)

Every tool returns a friendly, actionable string and never raises out of the
tool boundary, so Claude always gets a usable response.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from apex_mcp.common import get_logger, human_bytes, safe_resolve
from apex_mcp.config import settings

logger = get_logger(__name__)

mcp = FastMCP("apex-share")

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

# Maximum size of a report file we are willing to inline into a webhook payload.
# Zapier and most downstream apps choke well before this; 8 MB is a safe ceiling.
MAX_FILE_BYTES = 8 * 1024 * 1024

# File suffixes we treat as plain text and send inline as ``content``. Anything
# else is treated as binary and base64-encoded.
TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".tsv",
    ".html",
    ".htm",
    ".json",
    ".log",
    ".yaml",
    ".yml",
}

# How the user sets things up -- reused in several friendly messages.
_SETUP_HINT = (
    "Set up: create a Zap with trigger 'Webhooks by Zapier -> Catch Hook', copy "
    "its URL, and export it as ZAPIER_WEBHOOK_URL (and optionally "
    "ZAPIER_FILE_WEBHOOK_URL for file uploads). Point the Zap's actions at Slack "
    "(post message) and Google Drive (upload file)."
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _utc_now() -> str:
    """Return the current time as a UTC ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _post(payload: dict, *, url: str) -> dict:
    """POST ``payload`` as JSON to ``url`` and return a small status dict.

    Never raises: network/HTTP errors are caught and returned as an ``error``
    field in the result dict so callers can craft a friendly message.

    Returns a dict shaped like::

        {"ok": bool, "status_code": int | None, "text": str, "error": str | None}
    """
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=payload)
        snippet = (response.text or "")[:300]
        result = {
            "ok": response.is_success,
            "status_code": response.status_code,
            "text": snippet,
            "error": None,
        }
        logger.info(
            "POST %s -> %s (ok=%s)", payload.get("event"), response.status_code, result["ok"]
        )
        return result
    except httpx.HTTPError as exc:  # connection errors, timeouts, etc.
        logger.warning("Webhook POST failed: %s", exc)
        return {"ok": False, "status_code": None, "text": "", "error": str(exc)}
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.exception("Unexpected error during webhook POST")
        return {"ok": False, "status_code": None, "text": "", "error": str(exc)}


def _webhook_or_hint(url: str, *, what: str) -> str | None:
    """Return ``None`` if ``url`` is configured, else an actionable hint string."""
    if url and url.strip():
        return None
    return (
        f"No webhook configured for {what}. I can't share anything until a Zapier "
        f"Catch Hook URL is set.\n\n{_SETUP_HINT}"
    )


def _mask_url(url: str) -> str:
    """Mask a webhook URL, revealing only its host and last 4 characters."""
    if not url:
        return "(not set)"
    try:
        host = httpx.URL(url).host or "?"
    except Exception:
        host = "?"
    tail = url[-4:] if len(url) >= 4 else url
    return f"{host}/...{tail}"


def _format_metrics(metrics: dict[str, Any] | None) -> str:
    """Render a metrics dict as compact Slack-friendly markdown bullet lines."""
    if not metrics:
        return ""
    lines = []
    for key, value in metrics.items():
        label = str(key).replace("_", " ").title()
        lines.append(f"- *{label}:* {value}")
    return "\n".join(lines)


def _summarize_result(result: dict, *, action: str) -> str:
    """Turn a :func:`_post` result dict into a friendly success/failure string."""
    if result.get("ok"):
        return f"OK: {action} (HTTP {result.get('status_code')}). The Zap should now run."
    if result.get("error"):
        return (
            f"FAILED: {action} could not reach the webhook: {result['error']}. "
            "Check your network and that the Zapier webhook URL is correct."
        )
    return (
        f"FAILED: {action} -- webhook returned HTTP {result.get('status_code')}: "
        f"{result.get('text') or '(no body)'}"
    )


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #


@mcp.tool()
def share_backtest_results(
    strategy: str,
    symbol: str,
    timeframe: str,
    summary: str,
    metrics: dict | None = None,
    channel: str = "",
) -> str:
    """Share APEX backtest results with the team via the Zapier webhook.

    This is the headline tool: it builds a tidy, structured payload and POSTs it
    to the configured Zapier Catch Hook, which fans it out to Slack (and any other
    connected actions). A preformatted ``slack_text`` markdown block is included
    so the Zap can post it directly without extra mapping.

    Args:
        strategy: Name of the strategy that was backtested (e.g. "Mean Reversion v3").
        symbol: Instrument tested (e.g. "EURUSD", "BTCUSD").
        timeframe: Bar timeframe (e.g. "M15", "H1", "D1").
        summary: A short human-readable summary of how the backtest went.
        metrics: Optional dict of headline metrics. Recommended keys:
            ``net_profit``, ``win_rate``, ``profit_factor``, ``max_drawdown``,
            ``sharpe``, ``total_trades``. Any keys are accepted.
        channel: Optional Slack channel override (e.g. "#quant-results"). Leave
            empty to use the channel configured in the Zap.

    Returns:
        A clear success or failure message. If the webhook URL is not configured,
        returns actionable setup instructions instead of failing silently.
    """
    hint = _webhook_or_hint(settings.zapier_webhook_url, what="backtest results")
    if hint:
        return hint

    metrics_md = _format_metrics(metrics)
    slack_lines = [
        f":bar_chart: *APEX Backtest Results -- {strategy}*",
        f"*Symbol:* {symbol}   *Timeframe:* {timeframe}",
        "",
        summary.strip(),
    ]
    if metrics_md:
        slack_lines += ["", "*Metrics*", metrics_md]
    slack_text = "\n".join(slack_lines)

    payload = {
        "event": "backtest_results",
        "strategy": strategy,
        "symbol": symbol,
        "timeframe": timeframe,
        "summary": summary,
        "metrics": metrics or {},
        "channel": channel,
        "timestamp": _utc_now(),
        "slack_text": slack_text,
    }

    result = _post(payload, url=settings.zapier_webhook_url)
    return _summarize_result(
        result, action=f"shared backtest results for {strategy} on {symbol} {timeframe}"
    )


@mcp.tool()
def share_report_file(file_path: str, title: str = "", note: str = "") -> str:
    """Share a local report file with the team (e.g. upload to Google Drive via the Zap).

    Reads a report from disk and POSTs it to the file webhook. Text-like files
    (txt/md/csv/html/json/...) are sent inline as ``content``; binary files (pdf,
    images, etc.) are base64-encoded and sent as ``content_b64`` with
    ``encoding: "base64"`` so the Zap can decode and upload them to Google Drive.

    Args:
        file_path: Path to the report file. Resolved safely inside the configured
            APEX data directory; paths escaping it are rejected.
        title: Optional human-friendly title for the upload (defaults to filename).
        note: Optional note/description to accompany the file.

    Returns:
        A clear success or failure message, including the file size. Files larger
        than 8 MB are rejected with an explanation rather than POSTed.
    """
    hint = _webhook_or_hint(settings.file_webhook, what="file uploads")
    if hint:
        return hint

    # Resolve safely inside the sandbox; reject traversal / missing files.
    try:
        resolved = safe_resolve(file_path)
    except Exception as exc:
        return f"FAILED: invalid file path '{file_path}': {exc}"

    if not resolved.exists():
        return f"FAILED: file not found: {resolved}"
    if not resolved.is_file():
        return f"FAILED: not a regular file: {resolved}"

    size = resolved.stat().st_size
    if size > MAX_FILE_BYTES:
        return (
            f"FAILED: '{resolved.name}' is {human_bytes(size)}, which exceeds the "
            f"{human_bytes(MAX_FILE_BYTES)} limit for webhook sharing. Trim or "
            "compress the file, or upload it to Drive manually."
        )

    is_text = resolved.suffix.lower() in TEXT_SUFFIXES
    payload: dict[str, Any] = {
        "event": "report_file",
        "filename": resolved.name,
        "title": title or resolved.name,
        "note": note,
        "size_bytes": size,
        "size_human": human_bytes(size),
        "timestamp": _utc_now(),
    }

    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        return f"FAILED: could not read '{resolved.name}': {exc}"

    if is_text:
        try:
            payload["content"] = raw.decode("utf-8")
            payload["encoding"] = "utf-8"
        except UnicodeDecodeError:
            # Looked like text by extension but isn't valid UTF-8; fall back to binary.
            is_text = False

    if not is_text:
        payload["content_b64"] = base64.b64encode(raw).decode("ascii")
        payload["encoding"] = "base64"

    result = _post(payload, url=settings.file_webhook)
    return _summarize_result(
        result, action=f"shared report file '{resolved.name}' ({human_bytes(size)})"
    )


@mcp.tool()
def send_team_message(text: str, channel: str = "") -> str:
    """Send an ad-hoc message to the team via the Zapier webhook (e.g. to Slack).

    Args:
        text: The message body to send.
        channel: Optional Slack channel override (e.g. "#quant"). Leave empty to
            use the channel configured in the Zap.

    Returns:
        A clear success or failure message, or setup instructions if no webhook
        is configured.
    """
    hint = _webhook_or_hint(settings.zapier_webhook_url, what="team messages")
    if hint:
        return hint

    payload = {
        "event": "message",
        "text": text,
        "channel": channel,
        "slack_text": text,
        "timestamp": _utc_now(),
    }
    result = _post(payload, url=settings.zapier_webhook_url)
    return _summarize_result(result, action="sent team message")


@mcp.tool()
def share_status() -> str:
    """Report whether the Zapier webhooks are configured (URLs are masked).

    Never prints a full webhook URL -- only the host and last 4 characters are
    shown. Includes a short reminder of how to set up the Zap.

    Returns:
        A human-readable status report.
    """
    main_set = bool(settings.zapier_webhook_url.strip())
    file_url = settings.file_webhook
    file_set = bool(file_url.strip())
    dedicated_file = bool(settings.zapier_file_webhook_url.strip())

    lines = [
        "APEX Share -- webhook status",
        f"- Main webhook (messages + results): "
        f"{'configured' if main_set else 'NOT set'} ({_mask_url(settings.zapier_webhook_url)})",
        f"- File webhook (uploads): "
        f"{'configured' if file_set else 'NOT set'} ({_mask_url(file_url)})"
        + ("" if dedicated_file else " [falls back to main webhook]"),
        "",
        _SETUP_HINT,
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> None:
    """Run the APEX Share MCP server over stdio."""
    logger.info("Starting apex-share MCP server")
    mcp.run()


if __name__ == "__main__":
    main()
