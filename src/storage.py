"""数据持久化模块 — SQLite 建表 + CRUD"""
import sqlite3
import os
from datetime import datetime


DB_PATH = "D:/quant/db/main.db"


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化所有表"""
    conn = get_conn()
    conn.executescript("""
        -- 2连板事件记录表
        CREATE TABLE IF NOT EXISTS two_board_record (
            symbol         TEXT NOT NULL,
            two_board_date TEXT NOT NULL,
            name           TEXT,
            PRIMARY KEY (symbol, two_board_date)
        );

        -- 日线数据缓存表
        CREATE TABLE IF NOT EXISTS stock_daily (
            symbol      TEXT NOT NULL,
            trade_date  TEXT NOT NULL,
            open        REAL,
            high        REAL,
            low         REAL,
            close       REAL,
            volume      REAL,
            amount      REAL,
            turnover    REAL,
            pct_chg     REAL,
            amplitude   REAL,
            update_time TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(symbol, trade_date)
        );
        CREATE INDEX IF NOT EXISTS idx_daily_symbol ON stock_daily(symbol);
        CREATE INDEX IF NOT EXISTS idx_daily_date ON stock_daily(trade_date);

        -- 选股结果表
        CREATE TABLE IF NOT EXISTS screen_result (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            screen_date     TEXT NOT NULL,
            symbol          TEXT NOT NULL,
            name            TEXT,
            score           REAL,
            rank            INTEGER,
            lu_date_start   TEXT,
            lu_date_end     TEXT,
            lu_high         REAL,
            lu_low          REAL,
            fib_618         REAL,
            adj_days        INTEGER,
            adj_vol_ratio   REAL,
            adj_yang_ratio  REAL,
            adj_min_close   REAL,
            is_ladder_vol   INTEGER DEFAULT 0,
            uptrend_stage   TEXT,
            is_sandwich     INTEGER DEFAULT 0,
            is_above_board  INTEGER DEFAULT 0,
            buy_price       REAL,
            protect_price   REAL,
            protect_type    TEXT,
            sell_price_3pct REAL,
            sell_price_5pct REAL,
            meets_criteria  INTEGER DEFAULT 0,
            meets_preferred INTEGER DEFAULT 0,
            create_time     TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_screen_date ON screen_result(screen_date);
    """)
    conn.commit()
    conn.close()


# ─── two_board_record 操作 ─────────────────────────────────

def insert_two_board(symbol: str, date_str: str, name: str):
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO two_board_record VALUES (?, ?, ?)",
                 (symbol, date_str, name))
    conn.commit()
    conn.close()


def delete_two_board(symbol: str):
    conn = get_conn()
    conn.execute("DELETE FROM two_board_record WHERE symbol=?", (symbol,))
    conn.commit()
    conn.close()


def query_candidates(window_start: str, today_str: str) -> list[dict]:
    """查询近N个交易日内完成2连板的股票"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT symbol, name, two_board_date FROM two_board_record "
        "WHERE two_board_date >= ? AND two_board_date <= ? "
        "ORDER BY two_board_date DESC",
        (window_start, today_str)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── stock_daily 缓存操作 ──────────────────────────────────

def read_daily_cache(symbol: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM stock_daily WHERE symbol=? ORDER BY trade_date",
        (symbol,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_last_cached_date(symbol: str) -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT MAX(trade_date) as d FROM stock_daily WHERE symbol=?",
        (symbol,)
    ).fetchone()
    conn.close()
    return row["d"] if row else None


def upsert_daily_rows(symbol: str, rows: list[dict]):
    """增量写入日线数据（INSERT OR IGNORE）"""
    conn = get_conn()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for r in rows:
        conn.execute("""
            INSERT OR IGNORE INTO stock_daily
            (symbol, trade_date, open, high, low, close, volume, amount,
             turnover, pct_chg, amplitude, update_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol, r.get("trade_date"), r.get("open"), r.get("high"),
            r.get("low"), r.get("close"), r.get("volume"), r.get("amount"),
            r.get("turnover"), r.get("pct_chg"), r.get("amplitude"), now
        ))
    conn.commit()
    conn.close()


# ─── screen_result 操作 ────────────────────────────────────

def save_screen_results(screen_date: str, results: list[dict]):
    conn = get_conn()
    for i, r in enumerate(results):
        conn.execute("""
            INSERT INTO screen_result
            (screen_date, symbol, name, score, rank, lu_date_start, lu_date_end,
             lu_high, lu_low, fib_618, adj_days, adj_vol_ratio, adj_yang_ratio,
             adj_min_close, is_ladder_vol, uptrend_stage, is_sandwich,
             is_above_board, buy_price, protect_price, protect_type,
             sell_price_3pct, sell_price_5pct, meets_criteria, meets_preferred)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            screen_date, r["symbol"], r["name"], r["score"], i + 1,
            r.get("lu_date_start"), r.get("lu_date_end"),
            r.get("lu_high"), r.get("lu_low"), r.get("fib_618"),
            r.get("adj_days"), r.get("adj_vol_ratio"), r.get("adj_yang_ratio"),
            r.get("adj_min_close"), int(r.get("is_ladder_vol", False)),
            r.get("uptrend_stage"), int(r.get("is_sandwich", False)),
            int(r.get("is_above_board", False)), r.get("buy_price"),
            r.get("protect_price"), r.get("protect_type"),
            r.get("sell_price_3pct"), r.get("sell_price_5pct"),
            int(r.get("meets_criteria", False)),
            int(r.get("meets_preferred", 0))
        ))
    conn.commit()
    conn.close()
