# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project overview

A quantitative stock screening system implementing the **二板涨停 N 型战法** (Two-Board Limit-Up N-Pattern Strategy) for A-share market. It identifies stocks that had 2 consecutive limit-up days, then entered a consolidation/retracement phase meeting specific technical criteria (volume shrinking, golden fib support, trend stage, etc.).

## Commands

```bash
# Daily screen (default date = today)
python main.py

# Screen for a specific date with cold start (backfill 15 trading days of 2-board history)
python main.py --date 2026-05-13 --cold-start

# Single stock analysis mode
python main.py --analyze 000839

# Tune concurrency
python main.py --workers 4 --rate 5 --days 200

# Headless daily runner (for cron / Task Scheduler)
python run_daily.py

# Standalone one-shot script (no dependency on src/ modules)
python independent_screen.py

# Install dependencies
pip install -r requirements.txt
```

## Architecture

**Entry points:**
- `main.py` — CLI with argparse. Dispatches to `run_daily_screen()` or `run_analysis_mode()`.
- `run_daily.py` — headless script for cron/Windows Task Scheduler. Same pipeline, no args.
- `independent_screen.py` — fully self-contained copy of the algorithm (no imports from `src/`). Useful for debugging or one-off runs without touching the module code.

**Pipeline** (`src/screener.py` → `run_daily_screen`):
1. **Init** — `init_db()` creates SQLite tables, `fetch_trading_calendar()` loads all trading days.
2. **Cold start** (optional) — scans the last 15 trading days for 2-board and multi-board events, filtering out stocks that later became 3+ boards.
3. **Step 1** — Fetch today's limit-up pool via akshare. Record 2-board hits into `two_board_record`, remove any that graduated to 3+ boards. Record 3+ board events into `multi_board_record`.
4. **Step 2** — Query candidate pool from the past 15 trading days from both `two_board_record` and `multi_board_record`. Multi-board candidates take priority on overlap (same symbol in both → kept only in multi-board pool).
5. **Step 3** — Concurrently fetch daily kline data for all candidates via `ThreadPoolExecutor` + `RateLimiter` (akshare rate limiting).
6. **Step 4** — Run `analyze_one_stock()` on each candidate, then `calc_score()`.
7. **Step 5** — Filter by `meets_criteria`, sort by score descending, save to DB, generate console/CSV/HTML reports.

**Module responsibilities:**
- `src/data_fetcher.py` — akshare wrappers. `fetch_limit_up_pool()` (Eastmoney), `fetch_daily_kline()` (Sina source, qfq-adjusted), `fetch_trading_calendar()`. Symbol prefix mapping: 0/3→sz, 6→sh, 4/8/9→北交所(skipped — Sina doesn't support them).
- `src/indicator.py` — `analyze_one_stock()` is the core analysis chain: find consecutive boards → golden fib (0.618) → consolidation phase → volume shrinking → ladder volume → yang line ratio → uptrend stage (early/mid/late based on MA60>MA120 and 20-day rise %) → sandwich/breakout zone detection.
- `src/scorer.py` — Weighted scoring out of 100. Basic (70pts): adj_days, vol_ratio, stage, fib support. Preferred (30pts): ladder vol, yang ratio, above-board adjustment, sandwich pattern.
- `src/storage.py` — SQLite at `<project_root>/db/main.db` (path relative to the file's location, auto-created on first run). Tables: `two_board_record`, `multi_board_record`, `stock_daily` (kline cache), `screen_result`. Uses `INSERT OR IGNORE` for idempotent writes. Includes ALTER TABLE migrations for backward compatibility.
- `src/concurrency.py` — `RateLimiter` (Semaphore-based, min interval enforcement) + `fetch_one_with_retry` (exponential backoff, 3 retries) + `fetch_all_candidates` (ThreadPoolExecutor).
- `src/reporter.py` — Console table output (rank, score, buy/sell points) + CSV export to `data/export/`.
- `src/html_reporter.py` — ECharts-based interactive HTML report with candlestick charts, MA60/MA120 overlays, fib/buy/protect marker lines, grouped excluded stocks by failure reason.

## Configuration

`config/settings.yaml` — reference document for all tunable parameters (lookback windows, volume shrink threshold, fib level, limit-up thresholds, buy/sell ratios, concurrency, risk limits). This file is **not loaded at runtime**; parameters are passed via CLI args to `main.py` with defaults baked into the script. The CI workflow in `.github/workflows/daily-screen.yml` overrides these defaults explicitly.

## Data sources

Uses **akshare** exclusively. Kline data from Sina (`stock_zh_a_daily`), limit-up pool from Eastmoney (`stock_zt_pool_em`). Free-tier rate limits apply — the `RateLimiter` defaults to 10 req/s. 北交所 (Beijing Stock Exchange) stocks are skipped because Sina doesn't support them.

## CI/CD

`.github/workflows/daily-screen.yml` — runs weekdays at 18:00 Beijing time (UTC 10:00). Executes `python main.py --cold-start --workers 4 --rate 5 --days 200`, then deploys results to GitHub Pages (`data/export/` → `_site/`).

## Windows notes

`main.py` and `run_daily.py` force UTF-8 stdout/stderr for Chinese character support. The DB and export paths are relative to the project root (`db/`, `data/export/`), not hardcoded absolute paths.
