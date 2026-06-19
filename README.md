# APEX Quant MCP 🛰️📈

A futuristic **MCP (Model Context Protocol) server suite** for the **APEX Quant Forex trading bot**.
It plugs your trading research and live market data straight into Claude — no manual uploads, no copy-paste.

Three servers, one workflow:

| Server | What it does | Headline tool |
| --- | --- | --- |
| 🧠 **`apex-rag`** | RAG over your research docs & CSV data in `J:\APEX_AGI_Forex_Trading_Bot` | `search_documents("...")` |
| 📊 **`apex-mt5`** | Live MetaTrader 5 market data | `get_candles("XAUUSD", "H1", 100)` |
| 📤 **`apex-share`** | Auto-share backtest results to Slack/Drive via Zapier | `share_backtest_results(...)` |

Once installed you can simply ask Claude things like:

> *"XAUUSD H1 last 100 candles கொடு, then compare against my breakout strategy notes."*
> *"Search my research docs for everything about London-session risk."*
> *"Share these backtest results with the team on #apex-signals."*

---

## 🚀 Quick start (Windows)

```powershell
git clone <this-repo> apex-quant-mcp
cd apex-quant-mcp
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

The installer creates a `.venv`, installs dependencies, and seeds a `.env` file.
Then:

1. **Edit `.env`** — set `APEX_DATA_DIR`, optionally MT5 creds, and `ZAPIER_WEBHOOK_URL`.
2. **Register the servers** with Claude Desktop — merge the `mcpServers` block from
   [`claude_desktop_config.example.json`](./claude_desktop_config.example.json) into
   `%APPDATA%\Claude\claude_desktop_config.json` (replace `C:\path\to\apex-quant-mcp`
   with your clone path).
3. **Restart Claude Desktop.** You'll see `apex-rag`, `apex-mt5`, `apex-share` connected. ✅

> Manual install: `python -m venv .venv && .venv\Scripts\pip install -e .`

---

## 🧠 1. `apex-rag` — RAG document ingestion

Reads research docs and CSV data straight from your trading folder. No manual uploads.

- Formats: `.md`, `.txt`, `.pdf`, `.docx`, `.csv` (configurable via `APEX_RAG_EXTENSIONS`).
- Lexical **BM25** retrieval out of the box — no GPU, no API key, fully offline.
- Optional **semantic / hybrid** search: `pip install -e .[semantic]` and set `APEX_RAG_SEMANTIC=1`.
- Sandboxed: every file access is confined to `APEX_DATA_DIR` (path-traversal blocked).
- The index is persisted, so restarts are instant.

**Tools:** `list_documents`, `read_document`, `search_documents`, `query_csv`, `reindex`, `index_status`.

## 📊 2. `apex-mt5` — live MetaTrader 5 data

Lets Claude query your **running MT5 terminal** directly via the official `MetaTrader5` package.

- Leave `MT5_LOGIN`/`MT5_PASSWORD`/`MT5_SERVER` blank to attach to an already-running terminal,
  or fill them in to log in explicitly.
- Timeframes: `M1, M5, M15, M30, H1, H4, D1, W1, MN1`.

**Tools:** `get_candles`, `get_candles_range`, `list_symbols`, `get_symbol_info`,
`get_tick`, `get_account_info`, `get_positions`, `mt5_status`.

> ⚠️ Windows-only (MT5 is Windows-only). The package installs automatically there;
> on other platforms the server still loads but MT5 tools return a friendly notice.

## 📤 3. `apex-share` — backtest sharing via Zapier

Pushes backtest results and report files to your team through a Zapier **Catch Hook** —
no Slack/Drive API keys to manage.

**One-time Zap setup:**

1. Create a Zap → trigger **"Webhooks by Zapier → Catch Hook"**.
2. Copy the hook URL into `.env` as `ZAPIER_WEBHOOK_URL`.
3. Add actions: **Slack → Send Channel Message** (map `slack_text`) and
   **Google Drive → Upload File** (map `content` / `content_b64` + `filename`).

The server sends a clean JSON payload that already contains a preformatted `slack_text`
block, so the Zap just forwards it.

**Tools:** `share_backtest_results`, `share_report_file`, `send_team_message`, `share_status`.

---

## ⚙️ Configuration

All settings live in `.env` (see [`.env.example`](./.env.example)). Key vars:

| Variable | Purpose |
| --- | --- |
| `APEX_DATA_DIR` | Root folder for research docs & CSV data |
| `APEX_RAG_EXTENSIONS` | File types to ingest for RAG |
| `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` | MT5 login (blank = attach to running terminal) |
| `ZAPIER_WEBHOOK_URL` | Zapier Catch Hook for backtest sharing |
| `APEX_LOG_LEVEL` | `INFO` / `DEBUG` / … (logs go to stderr) |

## 🏗️ Architecture

```
apex_mcp/
├── config.py        # central env-driven settings (single source of truth)
├── common.py        # logging, sandboxed path resolution, formatting
├── rag_server.py    # 🧠 apex-rag  (FastMCP)
├── rag/
│   ├── ingest.py    #    document loading + chunking (pdf/docx/csv/txt/md)
│   └── index.py     #    persistent BM25 (+ optional hybrid) index
├── mt5_server.py    # 📊 apex-mt5  (FastMCP, lazy MetaTrader5 import)
└── share_server.py  # 📤 apex-share (FastMCP, Zapier webhook)
```

## ✅ Testing

```bash
python -m pytest -q
```

Smoke tests cover config loading, the path-traversal sandbox, formatting helpers,
and that each server imports and exposes `main()`. Server tests skip gracefully when
optional deps (MT5, etc.) aren't present.

## 🧹 Folder cleanup audit (`tools/`)

Cleaning up old bot copies on your `J:` drive? Run the **read-only** audit first —
it never deletes anything, it just tells you which folder is safe to remove.

```text
tools\run_audit.bat        # double-click (easiest)
# or:  powershell -ExecutionPolicy Bypass -File tools\audit_J_drive.ps1
# add  -Hash  for exact SHA256 content comparison (slower, certain)
```

It reports each `J:` folder's size + file count, checks whether an old folder's
files all exist in your LIVE (`My_Trader`, `APEX_KNOWLEDGE_LAKE`) and BACKUP
folders, lists any **unique** files that would be lost, gives a SAFE / DO-NOT-DELETE
verdict, and saves a timestamped report to `J:\_AUDIT_REPORT_*.txt`.
Always `robocopy` to an external disk and verify before you delete.

## 🔒 Notes on safety

- The RAG server can only read inside `APEX_DATA_DIR`.
- `apex-mt5` exposes your **own local** account/positions data to your own Claude — keep
  credentials in `.env` (git-ignored), never commit them.
- `apex-share` masks webhook URLs in status output and never logs secrets.

---

*Built as a modular MCP suite — run all three servers, or just the ones you need.*
