"""APEX Quant MCP — MetaTrader 5 market-data server.

A FastMCP server that lets Claude query a *live* MetaTrader 5 terminal: OHLCV
candles, symbol metadata, ticks, account state and open positions.

Design notes
------------
* The official ``MetaTrader5`` pip package is **Windows-only** and is NOT
  expected to be installed in the (Linux) build/CI environment. Therefore every
  reference to it is imported *lazily* inside :class:`MT5Connection`. Importing
  this module never requires ``MetaTrader5`` to be present — only actually
  *calling* a tool does.
* Every tool first ensures the connection, and returns a **friendly error
  string** instead of raising, so Claude always receives usable text.
* NumPy / structured-array values are converted to native Python types before
  formatting so the markdown stays clean.

Run with ``python -m apex_mcp.mt5_server`` (after installing ``MetaTrader5`` and
``mcp`` on a Windows host with a running MT5 terminal).
"""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import FastMCP

from apex_mcp.common import get_logger, markdown_table
from apex_mcp.config import settings

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    import MetaTrader5 as _mt5_types  # noqa: F401

logger = get_logger(__name__)

mcp = FastMCP("apex-mt5")

# Maximum number of candles we will ever return in one call, to keep payloads
# (and Claude's context) sane.
MAX_CANDLES = 1000

# Human-friendly timeframe names. The values are the *attribute names* on the
# ``MetaTrader5`` module; we resolve them to the real integer constants lazily
# once the package has been imported (see :func:`resolve_timeframe`).
_TIMEFRAME_ATTRS: dict[str, str] = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
    "W1": "TIMEFRAME_W1",
    "MN1": "TIMEFRAME_MN1",
}


class MT5Error(RuntimeError):
    """Raised for any MetaTrader 5 connection / initialisation problem."""


class MT5Connection:
    """Idempotent connection manager around the ``MetaTrader5`` package.

    Usage::

        mt5 = MT5_CONN.ensure()   # returns the live ``MetaTrader5`` module
        rates = mt5.copy_rates_from_pos(...)

    The first :meth:`ensure` call lazily imports the package and runs
    ``mt5.initialize(...)``. Subsequent calls are cheap no-ops while the
    connection stays alive.
    """

    def __init__(self) -> None:
        self._mt5: Any | None = None
        self._initialized: bool = False

    # ------------------------------------------------------------------ #
    # Lazy import
    # ------------------------------------------------------------------ #
    def _import(self) -> Any:
        """Import and cache the ``MetaTrader5`` module, raising a friendly error
        if it is not installed (e.g. on the Linux build host)."""
        if self._mt5 is not None:
            return self._mt5
        try:
            import MetaTrader5 as mt5  # type: ignore[import-not-found]
        except Exception as exc:  # ImportError + any platform-specific failure
            raise MT5Error(
                "The 'MetaTrader5' package is not available. It is Windows-only; "
                "install it (`pip install MetaTrader5`) on a Windows host that "
                "has a running MetaTrader 5 terminal. "
                f"(import error: {exc})"
            ) from exc
        self._mt5 = mt5
        return mt5

    # ------------------------------------------------------------------ #
    # Initialisation
    # ------------------------------------------------------------------ #
    def ensure(self) -> Any:
        """Ensure MT5 is imported and initialised; return the ``MetaTrader5``
        module. Idempotent — safe to call before every tool invocation."""
        mt5 = self._import()
        if self._initialized:
            return mt5

        # Build kwargs only for settings that were actually provided. If no
        # path/credentials are configured we call ``initialize()`` with no
        # args, which attaches to an already-running terminal.
        kwargs: dict[str, Any] = {}
        if settings.mt5_terminal_path:
            kwargs["path"] = settings.mt5_terminal_path
        if settings.mt5_login:
            try:
                kwargs["login"] = int(settings.mt5_login)
            except ValueError as exc:
                raise MT5Error(
                    f"MT5_LOGIN must be an integer, got {settings.mt5_login!r}."
                ) from exc
        if settings.mt5_password:
            kwargs["password"] = settings.mt5_password
        if settings.mt5_server:
            kwargs["server"] = settings.mt5_server

        logger.info(
            "Initialising MetaTrader5 (path=%s, login=%s, server=%s)",
            settings.mt5_terminal_path or "<attach>",
            settings.mt5_login or "<none>",
            settings.mt5_server or "<none>",
        )

        ok = mt5.initialize(**kwargs)
        if not ok:
            err = mt5.last_error()
            raise MT5Error(
                "mt5.initialize() failed. Make sure the MetaTrader 5 terminal is "
                "installed and (ideally) already running, and that any configured "
                f"credentials are correct. last_error={err}"
            )
        self._initialized = True
        logger.info("MetaTrader5 initialised successfully.")
        return mt5

    # ------------------------------------------------------------------ #
    # Teardown
    # ------------------------------------------------------------------ #
    def shutdown(self) -> None:
        """Shut down the MT5 connection if it was initialised. Safe to call
        multiple times."""
        if self._mt5 is not None and self._initialized:
            try:
                self._mt5.shutdown()
            except Exception:  # pragma: no cover - defensive
                logger.exception("Error during mt5.shutdown()")
            finally:
                self._initialized = False
        logger.info("MetaTrader5 connection shut down.")


# Module-level singleton used by every tool.
MT5_CONN = MT5Connection()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def resolve_timeframe(mt5: Any, timeframe: str) -> int:
    """Map a human timeframe string (e.g. ``"H1"``) to the MT5 integer constant.

    Raises :class:`ValueError` (with the list of valid options) on bad input.
    """
    key = timeframe.strip().upper()
    attr = _TIMEFRAME_ATTRS.get(key)
    if attr is None:
        valid = ", ".join(_TIMEFRAME_ATTRS)
        raise ValueError(f"Invalid timeframe {timeframe!r}. Valid options: {valid}.")
    return int(getattr(mt5, attr))


def _to_native(value: Any) -> Any:
    """Convert a numpy / structured-array scalar to a native Python type."""
    # numpy scalars expose ``.item()``; native types do not.
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:  # pragma: no cover - defensive
            return value
    return value


def _epoch_to_utc(seconds: Any) -> str:
    """Convert epoch seconds (from MT5 ``time`` fields) to a readable UTC string."""
    try:
        ts = float(_to_native(seconds))
    except (TypeError, ValueError):
        return str(seconds)
    return _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _fmt(value: Any, digits: int = 5) -> str:
    """Format a numeric value for display, falling back to str()."""
    native = _to_native(value)
    if isinstance(native, float):
        return f"{native:.{digits}f}"
    return str(native)


def _parse_iso(value: str) -> _dt.datetime:
    """Parse an ISO-8601 date/datetime string into a tz-aware UTC datetime."""
    text = value.strip()
    # ``datetime.fromisoformat`` in 3.10 doesn't accept a trailing 'Z'.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = _dt.datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt.astimezone(_dt.timezone.utc)


# Position type code -> human label (mt5.ORDER_TYPE_BUY == 0, SELL == 1).
_POSITION_TYPES = {0: "BUY", 1: "SELL"}


def _rates_to_table(rates: Any) -> str:
    """Render an MT5 rates structured array as a markdown OHLCV table."""
    rows: list[dict[str, Any]] = []
    for r in rates:
        rows.append(
            {
                "time": _epoch_to_utc(r["time"]),
                "open": _fmt(r["open"]),
                "high": _fmt(r["high"]),
                "low": _fmt(r["low"]),
                "close": _fmt(r["close"]),
                "tick_volume": int(_to_native(r["tick_volume"])),
            }
        )
    return markdown_table(
        rows, ["time", "open", "high", "low", "close", "tick_volume"]
    )


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def get_candles(symbol: str, timeframe: str = "H1", count: int = 100) -> str:
    """Fetch the last `count` OHLCV candles for a symbol from MetaTrader 5.

    This is the headline market-data tool. Example: to get gold's last 100
    hourly candles call ``get_candles("XAUUSD", "H1", 100)``.

    Args:
        symbol: The market symbol exactly as it appears in the terminal
            (e.g. "XAUUSD", "EURUSD", "US500"). Case-sensitive on some brokers.
        timeframe: One of M1, M5, M15, M30, H1, H4, D1, W1, MN1. Defaults to H1.
        count: Number of most-recent candles to return (1..1000). Defaults to 100.

    Returns:
        A markdown table (time, open, high, low, close, tick_volume) plus a
        one-line summary, or a friendly error message.
    """
    try:
        mt5 = MT5_CONN.ensure()
    except MT5Error as exc:
        return f"MT5 unavailable: {exc}"

    try:
        tf = resolve_timeframe(mt5, timeframe)
    except ValueError as exc:
        return str(exc)

    count = max(1, min(int(count), MAX_CANDLES))

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None or len(rates) == 0:
        return (
            f"No candle data returned for symbol '{symbol}' ({timeframe}). "
            f"Check the symbol name (it may need to be selected in Market Watch). "
            f"last_error={mt5.last_error()}"
        )

    table = _rates_to_table(rates)
    first_time = _epoch_to_utc(rates[0]["time"])
    last_time = _epoch_to_utc(rates[-1]["time"])
    last_close = _fmt(rates[-1]["close"])
    summary = (
        f"**{symbol} {timeframe.upper()}** — {len(rates)} candles, "
        f"{first_time} → {last_time} UTC, last close {last_close}"
    )
    return f"{summary}\n\n{table}"


@mcp.tool()
def get_candles_range(symbol: str, timeframe: str, date_from: str, date_to: str) -> str:
    """Fetch OHLCV candles for a symbol between two ISO dates.

    Example: ``get_candles_range("EURUSD", "H1", "2024-01-01", "2024-01-08")``.

    Args:
        symbol: Market symbol (e.g. "XAUUSD").
        timeframe: One of M1, M5, M15, M30, H1, H4, D1, W1, MN1.
        date_from: Start datetime, ISO-8601 (e.g. "2024-01-01" or
            "2024-01-01T00:00:00Z"). Interpreted as UTC if no offset given.
        date_to: End datetime, ISO-8601 (inclusive of the window).

    Returns:
        A markdown OHLCV table plus a one-line summary, or a friendly error.
    """
    try:
        mt5 = MT5_CONN.ensure()
    except MT5Error as exc:
        return f"MT5 unavailable: {exc}"

    try:
        tf = resolve_timeframe(mt5, timeframe)
    except ValueError as exc:
        return str(exc)

    try:
        dt_from = _parse_iso(date_from)
        dt_to = _parse_iso(date_to)
    except ValueError as exc:
        return f"Invalid date: {exc}. Use ISO-8601, e.g. '2024-01-01'."
    if dt_from > dt_to:
        return f"date_from ({date_from}) must be before date_to ({date_to})."

    rates = mt5.copy_rates_range(symbol, tf, dt_from, dt_to)
    if rates is None or len(rates) == 0:
        return (
            f"No candle data for '{symbol}' ({timeframe}) between {date_from} and "
            f"{date_to}. last_error={mt5.last_error()}"
        )

    table = _rates_to_table(rates)
    first_time = _epoch_to_utc(rates[0]["time"])
    last_time = _epoch_to_utc(rates[-1]["time"])
    summary = (
        f"**{symbol} {timeframe.upper()}** — {len(rates)} candles, "
        f"{first_time} → {last_time} UTC"
    )
    return f"{summary}\n\n{table}"


@mcp.tool()
def list_symbols(filter: str = "", limit: int = 50) -> str:
    """List symbols available in the MetaTrader 5 terminal.

    Args:
        filter: Optional case-insensitive substring to filter by name
            (e.g. "USD", "XAU"). Empty returns the first symbols.
        limit: Maximum number of rows to return (1..500). Defaults to 50.

    Returns:
        A markdown table (name, description, path) plus a count summary, or a
        friendly error message.
    """
    try:
        mt5 = MT5_CONN.ensure()
    except MT5Error as exc:
        return f"MT5 unavailable: {exc}"

    symbols = mt5.symbols_get()
    if symbols is None:
        return f"Could not retrieve symbols. last_error={mt5.last_error()}"

    needle = filter.strip().lower()
    if needle:
        symbols = [s for s in symbols if needle in s.name.lower()]

    total = len(symbols)
    limit = max(1, min(int(limit), 500))
    shown = symbols[:limit]

    rows = [
        {
            "name": s.name,
            "description": getattr(s, "description", "") or "",
            "path": getattr(s, "path", "") or "",
        }
        for s in shown
    ]
    table = markdown_table(rows, ["name", "description", "path"])
    suffix = f" (showing {len(shown)} of {total})" if total > len(shown) else f" ({total})"
    header = f"Symbols matching '{filter}'" if needle else "Symbols"
    return f"**{header}**{suffix}\n\n{table}"


@mcp.tool()
def get_symbol_info(symbol: str) -> str:
    """Get key trading metadata for a symbol from MetaTrader 5.

    Args:
        symbol: Market symbol (e.g. "XAUUSD").

    Returns:
        A markdown table of key fields (bid, ask, spread, digits, point,
        trade_contract_size, volume_min, volume_max), or a friendly error.
    """
    try:
        mt5 = MT5_CONN.ensure()
    except MT5Error as exc:
        return f"MT5 unavailable: {exc}"

    info = mt5.symbol_info(symbol)
    if info is None:
        return (
            f"Symbol '{symbol}' not found. It may need to be enabled in Market "
            f"Watch. last_error={mt5.last_error()}"
        )

    rows = [
        {"field": "bid", "value": _to_native(info.bid)},
        {"field": "ask", "value": _to_native(info.ask)},
        {"field": "spread", "value": _to_native(info.spread)},
        {"field": "digits", "value": _to_native(info.digits)},
        {"field": "point", "value": _to_native(info.point)},
        {"field": "trade_contract_size", "value": _to_native(info.trade_contract_size)},
        {"field": "volume_min", "value": _to_native(info.volume_min)},
        {"field": "volume_max", "value": _to_native(info.volume_max)},
    ]
    table = markdown_table(rows, ["field", "value"])
    return f"**{symbol}** symbol info\n\n{table}"


@mcp.tool()
def get_tick(symbol: str) -> str:
    """Get the latest tick (current price) for a symbol from MetaTrader 5.

    Args:
        symbol: Market symbol (e.g. "XAUUSD").

    Returns:
        A markdown table with bid, ask, last and tick time (UTC), or a friendly
        error message.
    """
    try:
        mt5 = MT5_CONN.ensure()
    except MT5Error as exc:
        return f"MT5 unavailable: {exc}"

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return (
            f"No tick for '{symbol}'. Check the symbol name / Market Watch. "
            f"last_error={mt5.last_error()}"
        )

    rows = [
        {"field": "bid", "value": _to_native(tick.bid)},
        {"field": "ask", "value": _to_native(tick.ask)},
        {"field": "last", "value": _to_native(tick.last)},
        {"field": "time (UTC)", "value": _epoch_to_utc(tick.time)},
    ]
    table = markdown_table(rows, ["field", "value"])
    return f"**{symbol}** latest tick\n\n{table}"


@mcp.tool()
def get_account_info() -> str:
    """Get the connected MetaTrader 5 trading account summary.

    Note: this exposes your own local account data (balance/equity/etc.).

    Returns:
        A markdown table (login, balance, equity, margin, free margin, currency,
        leverage), or a friendly error message.
    """
    try:
        mt5 = MT5_CONN.ensure()
    except MT5Error as exc:
        return f"MT5 unavailable: {exc}"

    acct = mt5.account_info()
    if acct is None:
        return f"No account info available. last_error={mt5.last_error()}"

    rows = [
        {"field": "login", "value": _to_native(acct.login)},
        {"field": "balance", "value": _to_native(acct.balance)},
        {"field": "equity", "value": _to_native(acct.equity)},
        {"field": "margin", "value": _to_native(acct.margin)},
        {"field": "free_margin", "value": _to_native(acct.margin_free)},
        {"field": "currency", "value": _to_native(acct.currency)},
        {"field": "leverage", "value": _to_native(acct.leverage)},
    ]
    table = markdown_table(rows, ["field", "value"])
    return f"**Account {_to_native(acct.login)}**\n\n{table}"


@mcp.tool()
def get_positions() -> str:
    """List currently open positions on the MetaTrader 5 account.

    Returns:
        A markdown table (symbol, type, volume, price_open, price_current,
        profit), a message if there are no open positions, or a friendly error.
    """
    try:
        mt5 = MT5_CONN.ensure()
    except MT5Error as exc:
        return f"MT5 unavailable: {exc}"

    positions = mt5.positions_get()
    if positions is None:
        return f"Could not retrieve positions. last_error={mt5.last_error()}"
    if len(positions) == 0:
        return "No open positions."

    rows = [
        {
            "symbol": p.symbol,
            "type": _POSITION_TYPES.get(_to_native(p.type), str(_to_native(p.type))),
            "volume": _to_native(p.volume),
            "price_open": _to_native(p.price_open),
            "price_current": _to_native(p.price_current),
            "profit": _to_native(p.profit),
        }
        for p in positions
    ]
    table = markdown_table(
        rows,
        ["symbol", "type", "volume", "price_open", "price_current", "profit"],
    )
    return f"**Open positions** ({len(positions)})\n\n{table}"


@mcp.tool()
def mt5_status() -> str:
    """Report MetaTrader 5 connection, terminal and version info.

    Useful for debugging setup (is the package installed? is the terminal
    running? which build / account is connected?).

    Returns:
        A markdown summary of connection state, or a friendly error message.
    """
    try:
        mt5 = MT5_CONN.ensure()
    except MT5Error as exc:
        return f"MT5 unavailable: {exc}"

    rows: list[dict[str, Any]] = [{"field": "initialized", "value": True}]

    version = mt5.version()
    if version is not None:
        # version() returns (terminal_version, build, release_date_str).
        try:
            rows.append({"field": "version", "value": _to_native(version[0])})
            rows.append({"field": "build", "value": _to_native(version[1])})
            rows.append({"field": "release_date", "value": _to_native(version[2])})
        except (IndexError, TypeError):
            rows.append({"field": "version", "value": str(version)})

    term = mt5.terminal_info()
    if term is not None:
        rows.append({"field": "terminal_name", "value": getattr(term, "name", "")})
        rows.append({"field": "terminal_company", "value": getattr(term, "company", "")})
        rows.append({"field": "connected", "value": _to_native(getattr(term, "connected", ""))})
        rows.append({"field": "trade_allowed", "value": _to_native(getattr(term, "trade_allowed", ""))})
        rows.append({"field": "terminal_path", "value": getattr(term, "path", "")})

    acct = mt5.account_info()
    if acct is not None:
        rows.append({"field": "account_login", "value": _to_native(acct.login)})
        rows.append({"field": "account_server", "value": _to_native(acct.server)})

    table = markdown_table(rows, ["field", "value"])
    return f"**MT5 status**\n\n{table}"


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #
def main() -> None:
    """Run the MT5 MCP server over stdio."""
    try:
        mcp.run()
    finally:
        MT5_CONN.shutdown()


if __name__ == "__main__":
    main()
