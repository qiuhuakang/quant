"""选股筛选主模块 — 每日全流程"""
import time
import pandas as pd

from src.storage import (
    init_db, insert_two_board, delete_two_board, query_candidates,
    save_screen_results
)
from src.data_fetcher import (
    fetch_limit_up_pool, fetch_trading_calendar,
    get_n_trading_days_ago
)
from src.concurrency import fetch_all_candidates
from src.indicator import analyze_one_stock
from src.scorer import calc_score
from src.reporter import print_report, export_csv


def cold_start(trade_dates: list[str], end_date: str):
    """冷启动：回补近15个交易日的2连板记录，排除中途连板数>2的"""
    window_start = get_n_trading_days_ago(trade_dates, end_date, 15)
    start_idx = trade_dates.index(window_start)
    end_idx = trade_dates.index(end_date)
    date_range = trade_dates[start_idx:end_idx + 1]

    print(f"[冷启动] 回补 {window_start} ~ {end_date} 涨停数据 "
          f"({len(date_range)} 个交易日，从新到旧扫描)...")

    # 从新到旧遍历：连板数>2的加入排除名单，连板数==2且不在排除名单的才记录
    exclude_codes: set[str] = set()
    date_pools: dict[str, pd.DataFrame] = {}
    skipped_total = 0
    for d in reversed(date_range):
        zt = fetch_limit_up_pool(d)
        if zt is None:
            continue
        date_pools[d] = zt
        # 连板数>2：加入排除名单（不会在更早日期被记录）
        gt2 = zt[zt["连板数"] > 2]
        for _, row in gt2.iterrows():
            exclude_codes.add(row["代码"])

    # 从旧到新插入（只插入连板数==2且不在排除名单的）
    total = 0
    for d in date_range:
        zt = date_pools.get(d)
        if zt is None:
            continue
        two = zt[(zt["连板数"] == 2) & (~zt["代码"].isin(exclude_codes))]
        for _, row in two.iterrows():
            insert_two_board(row["代码"], d, row["名称"])
        total += len(two)
        skipped = len(zt[zt["连板数"] == 2]) - len(two)
        skipped_total += skipped
        skipped_str = f", 跳过{skipped}只(后续连板>2)" if skipped > 0 else ""
        print(f"  {d}: 连板数==2 {len(two)}只{skipped_str}")
    print(f"[冷启动] 完成, 共记录 {total} 条2连板事件, 过滤 {skipped_total} 只(后续突破2板)")


def run_daily_screen(screen_date: str | None = None,
                     calendar_days: int = 200,
                     max_workers: int = 8,
                     max_per_second: int = 10,
                     cold_start_first: bool = False) -> list[dict]:
    """执行一次完整选股流程"""
    t0 = time.time()

    # ── 初始化 ──────────────────────────────────────────────
    init_db()
    trade_dates = fetch_trading_calendar()

    # 取最近的已过去交易日
    from datetime import date as dt_date
    today_str = dt_date.today().strftime("%Y-%m-%d")
    if screen_date:
        today = screen_date
    else:
        today = max(d for d in trade_dates if d <= today_str)

    # 如果今天是非交易日，取最近交易日
    if today not in trade_dates:
        today = max(d for d in trade_dates if d < today)

    print(f"{'=' * 60}")
    print(f"  二板涨停 N 型战法 — 选股")
    print(f"  选股日期: {today}")
    print(f"{'=' * 60}")

    # ── 冷启动 ──────────────────────────────────────────────
    if cold_start_first:
        cold_start(trade_dates, today)

    # ── Step 1: 涨停池 → 写入 two_board_record ──────────────
    print(f"\n[Step 1] 获取当日涨停池...")
    zt = fetch_limit_up_pool(today)
    if zt is None:
        print("[ERROR] 无法获取涨停池，退出")
        return []

    # 当日连板数>2的从候选池删除（之前可能在2板时被记录了）
    gt2_codes = set(zt[zt["连板数"] > 2]["代码"].tolist())
    if gt2_codes:
        for code in gt2_codes:
            delete_two_board(code)
        print(f"  连板数>2: {len(gt2_codes)} 只 → 已从候选池清除")

    new_two = zt[zt["连板数"] == 2]
    for _, row in new_two.iterrows():
        insert_two_board(row["代码"], today, row["名称"])
    print(f"  当日涨停 {len(zt)} 只, 连板数==2: {len(new_two)} 只 → 已写入")

    # ── Step 2: 查询候选池 ──────────────────────────────────
    window_start = get_n_trading_days_ago(trade_dates, today, 15)
    candidates = query_candidates(window_start, today)
    print(f"\n[Step 2] 候选池: {window_start} ~ {today} "
          f"共 {len(candidates)} 只完成2连板")

    if not candidates:
        print("  无候选标的，退出")
        return []

    # ── Step 3: 并发获取日线 ─────────────────────────────────
    codes = list({c["symbol"] for c in candidates})
    print(f"\n[Step 3] 获取日线数据...")
    dfs = fetch_all_candidates(
        codes, max_workers=max_workers,
        max_per_second=max_per_second,
        calendar_days=calendar_days
    )

    # ── Step 4: 量化分析 ────────────────────────────────────
    print(f"\n[Step 4] 量化条件分析...")
    results = []
    for code in codes:
        if code not in dfs:
            continue
        df = dfs[code]
        # 找到候选对应的名称
        name = next((c["name"] for c in candidates if c["symbol"] == code),
                    code)

        analysis = analyze_one_stock(code, df)
        if analysis is None:
            continue

        analysis["name"] = name
        analysis["score"] = calc_score(analysis)
        analysis["screen_date"] = today
        results.append(analysis)

    print(f"  通过连板检测: {len(results)} 只")

    # ── Step 5: 过滤 + 排序 + 存储 ────────────────────────────
    passed = [r for r in results if r["meets_criteria"]]
    excluded = [r for r in results if not r["meets_criteria"]]

    if excluded:
        print(f"\n  基础条件未达标 ({len(excluded)} 只，不纳入结果):")
        for r in excluded:
            reasons = []
            if r["adj_days"] > 5:
                reasons.append(f"调整{r['adj_days']}天>5")
            if r["adj_vol_ratio"] >= 1.0:
                reasons.append(f"量比{r['adj_vol_ratio']}≥1.0，未缩量")
            if r["uptrend_stage"] not in ("early", "mid"):
                reasons.append(f"阶段={r['uptrend_stage']}")
            if r["adj_min_close"] < r["fib_618"]:
                reasons.append("破618")
            print(f"    {r['symbol']} {r.get('name','')}: {', '.join(reasons)}")

    passed.sort(key=lambda x: x["score"], reverse=True)
    save_screen_results(today, passed)

    elapsed = time.time() - t0
    print(f"\n  总耗时: {elapsed:.1f}s, 通过基础条件: {len(passed)} 只, "
          f"观察中: {len(excluded)} 只")

    return passed


def run_analysis_mode(code: str, calendar_days: int = 200):
    """单只股票分析模式（调试用）"""
    init_db()
    from src.data_fetcher import fetch_daily_kline

    print(f"\n{'=' * 60}")
    print(f"  单股分析: {code}")
    print(f"{'=' * 60}")

    df = fetch_daily_kline(code, calendar_days=calendar_days)
    if df is None:
        print("  获取日线失败")
        return

    print(f"  获取 {len(df)} 条日线数据")
    result = analyze_one_stock(code, df)

    if result is None:
        print("  未检测到连续2板")
        return

    result["name"] = code
    result["score"] = calc_score(result)

    # 打印详情
    for k, v in result.items():
        print(f"  {k}: {v}")
