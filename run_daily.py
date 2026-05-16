"""每日盘后自动执行 — Windows Task Scheduler / cron 触发"""
import sys
import os

# 强制 UTF-8 输出，解决 Windows 中文乱码
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.screener import run_daily_screen
from src.reporter import print_report, export_csv


def main():
    results = run_daily_screen(
        screen_date=None,   # 自动取最近交易日
        calendar_days=200,
        max_workers=8,
        max_per_second=10,
        cold_start_first=False
    )

    if results:
        # 从结果中取实际选股日期
        screen_date = results[0].get("screen_date") if results else None
        print_report(results, screen_date)
        export_csv(results, screen_date)
    else:
        print("今日无符合条件的标的。")

    print("盘后选股完成。")


if __name__ == "__main__":
    main()
