from __future__ import annotations
"""主入口 — 二板涨停 N 型战法选股系统"""
import sys
import os

# 强制 UTF-8 输出，解决 Windows 中文乱码
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.screener import run_daily_screen, run_analysis_mode
from src.reporter import print_report, export_csv


def main():
    import argparse
    parser = argparse.ArgumentParser(description="二板涨停 N 型战法选股系统")
    parser.add_argument("--date", type=str, default=None,
                        help="选股日期 (YYYY-MM-DD), 默认今天")
    parser.add_argument("--cold-start", action="store_true",
                        help="首次运行，回补近15交易日2连板记录")
    parser.add_argument("--analyze", type=str, default=None,
                        help="单只股票分析模式 (代码)")
    parser.add_argument("--workers", type=int, default=8,
                        help="并发线程数 (默认8)")
    parser.add_argument("--rate", type=int, default=10,
                        help="每秒最大请求数 (默认10)")
    parser.add_argument("--days", type=int, default=200,
                        help="日线拉取日历日范围 (默认200)")
    args = parser.parse_args()

    # 单股分析模式
    if args.analyze:
        run_analysis_mode(args.analyze, calendar_days=args.days)
        return

    from datetime import date as dt_date
    screen_date = args.date or dt_date.today().strftime("%Y-%m-%d")

    results = run_daily_screen(
        screen_date=screen_date,
        calendar_days=args.days,
        max_workers=args.workers,
        max_per_second=args.rate,
        cold_start_first=args.cold_start
    )

    if results:
        # 用实际选股日期（可能被修正为最近交易日）
        actual_date = results[0].get("screen_date", screen_date)
        print_report(results, actual_date)
        export_csv(results, actual_date)
    else:
        print(f"\n  无符合条件的标的。")


if __name__ == "__main__":
    main()
