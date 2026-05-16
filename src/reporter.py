"""结果输出模块 — 控制台 + CSV 导出"""
import os
import csv
from datetime import datetime


def print_report(results: list[dict], screen_date: str):
    """控制台格式化输出选股结果"""
    if not results:
        print("\n  无符合条件的标的")
        return

    print(f"\n{'=' * 90}")
    print(f"  选股结果报告  |  {screen_date}")
    print(f"  入选标的: {len(results)} 只")
    print(f"{'=' * 90}")

    # 主表
    print(f"\n{'排名':<5} {'代码':<10} {'名称':<10} {'评分':<6} "
          f"{'连板日':<12} {'调整天':<7} {'量比':<7} {'阳线%':<7} "
          f"{'买入价':<8} {'保护位':<8}")
    print("-" * 90)

    for i, r in enumerate(results):
        print(f"{i+1:<5} {r['symbol']:<10} {r.get('name','')[:8]:<10} "
              f"{r['score']:<6} "
              f"{r.get('lu_date_end','')[:10]:<12} "
              f"{r.get('adj_days',''):<7} "
              f"{r.get('adj_vol_ratio',''):<7} "
              f"{r.get('adj_yang_ratio',''):<7} "
              f"{r.get('buy_price',''):<8} "
              f"{r.get('protect_price',''):<8}")

    # 优选条件
    print(f"\n{'=' * 90}")
    print(f"  优选条件满足情况")
    print(f"{'代码':<10} {'阶梯量':<8} {'阳线占比':<9} "
          f"{'板上调整':<10} {'夹板/突破':<10} {'优选合计':<9}")
    print("-" * 60)

    for r in results:
        preferred = r.get("meets_preferred", 0)
        print(f"{r['symbol']:<10} "
              f"{'Y' if r.get('is_ladder_vol') else 'N':<8} "
              f"{r.get('adj_yang_ratio',''):<9} "
              f"{'Y' if r.get('is_above_board') else 'N':<10} "
              f"{'Y' if r.get('is_sandwich') else 'N':<10} "
              f"{preferred}/4")

    # 买卖点
    print(f"\n{'=' * 90}")
    print(f"  买卖点详情")
    print(f"{'代码':<10} {'买入价':<8} {'保护位':<8} {'保护类型':<12} "
          f"{'3%减仓':<8} {'5%止盈':<8}")
    print("-" * 60)

    for r in results:
        print(f"{r['symbol']:<10} "
              f"{r.get('buy_price',''):<8} "
              f"{r.get('protect_price',''):<8} "
              f"{r.get('protect_type',''):<12} "
              f"{r.get('sell_price_3pct',''):<8} "
              f"{r.get('sell_price_5pct',''):<8}")

    print(f"\n{'=' * 90}")
    print(f"  免责声明：本报告仅供参考，不构成投资建议。")
    print(f"{'=' * 90}")


def export_csv(results: list[dict], screen_date: str,
               export_dir: str = "D:/quant/data/export/"):
    """导出 CSV 文件"""
    os.makedirs(export_dir, exist_ok=True)
    path = os.path.join(export_dir, f"screen_result_{screen_date}.csv")
    latest_path = os.path.join(export_dir, "screen_result_latest.csv")

    if not results:
        return

    fieldnames = [
        "rank", "symbol", "name", "score",
        "lu_date_start", "lu_date_end", "lu_high", "lu_low", "fib_618",
        "adj_days", "adj_vol_ratio", "adj_yang_ratio", "adj_min_close",
        "is_ladder_vol", "uptrend_stage", "is_sandwich", "is_above_board",
        "buy_price", "protect_price", "protect_type",
        "sell_price_3pct", "sell_price_5pct",
        "meets_criteria", "meets_preferred"
    ]

    rows = []
    for i, r in enumerate(results):
        row = {k: r.get(k, "") for k in fieldnames}
        row["rank"] = i + 1
        rows.append(row)

    for fpath in (path, latest_path):
        with open(fpath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print(f"  CSV 已导出: {path}")
    print(f"  CSV 已导出: {latest_path}")
