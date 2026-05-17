"""选股筛选主模块 — 每日全流程"""
import time
import pandas as pd

from src.storage import (
    init_db, insert_two_board, delete_two_board, query_candidates,
    insert_multi_board, delete_multi_board, query_multi_board_candidates,
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
from src.html_reporter import export_html


def cold_start(trade_dates: list[str], end_date: str):
    """冷启动：回补近15个交易日的2连板+多连板记录"""
    window_start = get_n_trading_days_ago(trade_dates, end_date, 15)
    start_idx = trade_dates.index(window_start)
    end_idx = trade_dates.index(end_date)
    date_range = trade_dates[start_idx:end_idx + 1]

    print(f"[冷启动] 回补 {window_start} ~ {end_date} 涨停数据 "
          f"({len(date_range)} 个交易日，从新到旧扫描)...")

    # 从新到旧遍历：连板数>2的加入排除名单，连板数==2且不在排除名单的才记录
    # 同时记录连板数>=3到 multi_board_record
    exclude_codes: set[str] = set()
    date_pools: dict[str, pd.DataFrame] = {}
    skipped_total = 0
    multi_total = 0
    for d in reversed(date_range):
        zt = fetch_limit_up_pool(d)
        if zt is None:
            continue
        date_pools[d] = zt
        # 连板数>=3：记录到多连板表，同时加入2板排除名单
        ge3 = zt[zt["连板数"] >= 3]
        for _, row in ge3.iterrows():
            exclude_codes.add(row["代码"])
            insert_multi_board(row["代码"], d, int(row["连板数"]), row["名称"])
        multi_total += len(ge3)

    # 从旧到新插入2连板记录
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
        print(f"  {d}: 2连板 {len(two)}只{skipped_str}")
    print(f"[冷启动] 完成, 2连板 {total} 条(过滤 {skipped_total}), "
          f"多连板 {multi_total} 条")


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

    # 当日连板数>2的从2板候选池删除（已升级为多连板）
    gt2_codes = set(zt[zt["连板数"] > 2]["代码"].tolist())
    if gt2_codes:
        for code in gt2_codes:
            delete_two_board(code)
        print(f"  连板数>2: {len(gt2_codes)} 只 → 已从2板候选池清除")

    # 当日连板数>=3 → 写入多连板记录表
    ge3 = zt[zt["连板数"] >= 3]
    for _, row in ge3.iterrows():
        insert_multi_board(row["代码"], today, int(row["连板数"]), row["名称"])
    if len(ge3) > 0:
        print(f"  连板数>=3: {len(ge3)} 只 → 已写入多连板记录")

    new_two = zt[zt["连板数"] == 2]
    for _, row in new_two.iterrows():
        insert_two_board(row["代码"], today, row["名称"])
    print(f"  当日涨停 {len(zt)} 只, 连板数==2: {len(new_two)} 只 → 已写入")

    # ── Step 2: 查询候选池 ──────────────────────────────────
    window_start = get_n_trading_days_ago(trade_dates, today, 15)
    candidates = query_candidates(window_start, today)
    print(f"\n[Step 2] 2连板候选: {window_start} ~ {today} "
          f"共 {len(candidates)} 只")

    # 查询多连板候选
    multi_candidates = query_multi_board_candidates(window_start, today)
    print(f"  多连板候选: {window_start} ~ {today} "
          f"共 {len(multi_candidates)} 只")

    # 合并候选，多连板优先（同一symbol在两表时取multi）
    two_board_symbols = {c["symbol"] for c in candidates}
    multi_symbols = {c["symbol"] for c in multi_candidates}
    overlap = two_board_symbols & multi_symbols
    if overlap:
        candidates = [c for c in candidates if c["symbol"] not in overlap]
        print(f"  去重: {len(overlap)} 只从2板升级为多连板")

    if not candidates and not multi_candidates:
        print("  无候选标的，退出")
        return []

    # ── Step 3: 并发获取日线 ─────────────────────────────────
    codes = list({c["symbol"] for c in candidates})
    multi_codes = list({c["symbol"] for c in multi_candidates})
    all_codes = list(set(codes + multi_codes))

    # 构建 board 信息查找表
    board_info: dict[str, tuple[str, int]] = {}
    for c in candidates:
        board_info[c["symbol"]] = ("2", 2)
    for mc in multi_candidates:
        board_info[mc["symbol"]] = ("multi", mc.get("board_count", 3))

    print(f"\n[Step 3] 获取日线数据 (2板 {len(codes)} + 多连板 {len(multi_codes)}"
          f" = {len(all_codes)} 只)...")
    dfs = fetch_all_candidates(
        all_codes, max_workers=max_workers,
        max_per_second=max_per_second,
        calendar_days=calendar_days
    )

    # ── Step 4: 量化分析 ────────────────────────────────────
    print(f"\n[Step 4] 量化条件分析...")
    results = []
    for code in all_codes:
        if code not in dfs:
            continue
        df = dfs[code]
        # 找到候选对应的名称（优先 multi_candidates）
        name = next((c["name"] for c in multi_candidates if c["symbol"] == code), None)
        if name is None:
            name = next((c["name"] for c in candidates if c["symbol"] == code), code)

        analysis = analyze_one_stock(code, df)
        if analysis is None:
            continue

        bt, bc = board_info.get(code, ("2", 2))
        analysis["name"] = name
        analysis["board_type"] = bt
        analysis["board_count"] = bc
        analysis["score"] = calc_score(analysis)
        analysis["screen_date"] = today
        results.append(analysis)

    print(f"  通过连板检测: {len(results)} 只")

    # ── Step 5: 过滤 + 排序 + 存储 ────────────────────────────
    passed = [r for r in results if r["meets_criteria"]]
    excluded = [r for r in results if not r["meets_criteria"]]

    if excluded:
        print(f"\n  基础条件未达标 ({len(excluded)} 只，不纳入结果):")
        print(f"  {'─' * 85}")

        # 补充字段（兼容旧缓存数据）
        for r in excluded:
            r.setdefault("ma60", 0)
            r.setdefault("ma120", 0)
            if "vol_shrinking" not in r:
                r["vol_shrinking"] = r.get("adj_vol_ratio", 1.0) < 1.0
            if "broke_fib_618" not in r:
                # meets_basic 用的是最后一天是否破618，非最低价
                r["broke_fib_618"] = r.get("adj_min_close", 0) < r.get("fib_618", 0)

        # 按原因组合分类（4维度：阶段 / 量比 / 调整天数 / 破618）
        from collections import defaultdict

        fail_labels = [
            "阶段不符",
            "量比≥1.0、未缩量",
            "调整天数＞5",
            "破618",
        ]

        def get_fail_key(r):
            return (
                r["uptrend_stage"] not in ("early", "mid"),
                not r["vol_shrinking"],           # 用 bool() 避免 numpy.bool_ is False 的坑
                r["adj_days"] > 5,
                bool(r["broke_fib_618"]),
            )

        def make_cat_name(key):
            parts = [fail_labels[i] for i, v in enumerate(key) if v]
            if len(parts) == 1:
                return f"仅{parts[0]}"
            return " + ".join(parts)

        class_groups: dict[str, list[dict]] = defaultdict(list)
        for r in excluded:
            key = get_fail_key(r)
            class_groups[make_cat_name(key)].append(r)

        # 按失败维度数量排序，同类按名称排
        cn_num = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,
                  "九":9,"十":10,"十一":11,"十二":12,"十三":13,"十四":14,"十五":15}
        cn_labels = list(cn_num.keys())
        sorted_cats = sorted(class_groups.items(),
                             key=lambda kv: (sum(get_fail_key(kv[1][0])), kv[0]))

        # 分类汇总
        print(f"\n  【分类汇总】")
        for i, (cat_name, stocks) in enumerate(sorted_cats):
            num_label = cn_labels[i] if i < len(cn_labels) else str(i+1)
            names = "，".join(
                f"{r['symbol']} {r.get('name','')[:4]}"
                for r in stocks
            )
            print(f"\n  {num_label}、{cat_name}（{len(stocks)}只）")
            print(f"  {names}")

        # 详细列表（含MA60/MA120）
        print(f"\n  {'─' * 85}")
        print(f"  【详细列表】")
        print(f"  {'代码':<10} {'名称':<8} {'阶段':<10} {'MA60':<10} {'MA120':<10} {'量比':<8} {'调整天':<7} {'破618':<6}")
        print(f"  {'─' * 10} {'─' * 8} {'─' * 10} {'─' * 10} {'─' * 10} {'─' * 8} {'─' * 7} {'─' * 6}")
        for r in sorted(excluded, key=lambda x: x["symbol"]):
            print(f"  {r['symbol']:<10} {r.get('name','')[:8]:<8} {r['uptrend_stage']:<10} "
                  f"{r['ma60']:<10.2f} {r['ma120']:<10.2f} "
                  f"{r['adj_vol_ratio']:<8} {r['adj_days']:<7} "
                  f"{'Y' if r['broke_fib_618'] else 'N':<6}")

    # ── HTML 图表报告 ──────────────────────────────────────
    multi_results = [r for r in results if r.get("board_type") == "multi"]
    try:
        html_path = export_html(results, dfs, passed, today,
                                multi_results=multi_results)
        print(f"\n  HTML 图表报告已导出: {html_path}")
    except Exception as e:
        print(f"\n  [WARN] HTML 报告生成失败: {e}")

    passed.sort(key=lambda x: x["score"], reverse=True)
    save_screen_results(today, passed)

    elapsed = time.time() - t0
    multi_passed = sum(1 for r in passed if r.get("board_type") == "multi")
    print(f"\n  总耗时: {elapsed:.1f}s, 通过: {len(passed)} 只 "
          f"(2板 {len(passed) - multi_passed} + 多板 {multi_passed}), "
          f"未达标: {len(excluded)} 只")

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
