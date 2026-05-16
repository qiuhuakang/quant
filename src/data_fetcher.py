"""数据获取模块 — akshare 封装"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta


def to_sina_symbol(code: str) -> str:
    """000839 → sz000839, 600000 → sh600000; 北交所返回空"""
    code = str(code).strip()
    if code.startswith(("0", "3")):
        return f"sz{code}"
    elif code.startswith("6"):
        return f"sh{code}"
    elif code.startswith(("4", "8", "9")):
        return ""  # 北交所 Sina 源不支持，跳过
    return code


def fetch_limit_up_pool(trade_date: str) -> pd.DataFrame | None:
    """获取当日涨停股池（含连板数字段）"""
    try:
        df = ak.stock_zt_pool_em(date=trade_date.replace("-", ""))
        if df is None or df.empty:
            return None
        return df
    except Exception as e:
        print(f"  [ERROR] 获取涨停池失败 ({trade_date}): {e}")
        return None


def fetch_daily_kline(code: str, calendar_days: int = 200) -> pd.DataFrame | None:
    """获取个股日线数据（新浪源，限定200日历日）"""
    try:
        sina_sym = to_sina_symbol(code)
        if not sina_sym:
            return None  # 北交所，跳过
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=calendar_days)).strftime("%Y%m%d")

        df = ak.stock_zh_a_daily(symbol=sina_sym,
                                 start_date=start_date,
                                 end_date=end_date,
                                 adjust="qfq")
        if df is None or df.empty:
            return None

        df = df.rename(columns={
            "date": "trade_date", "open": "open", "high": "high",
            "low": "low", "close": "close", "volume": "volume",
            "amount": "amount", "turnover": "turnover"
        })

        # 本地派生涨跌幅/振幅
        df["pct_chg"] = round(df["close"].pct_change() * 100, 2)
        df["change"] = round(df["close"].diff(), 2)
        df["amplitude"] = round(
            (df["high"] - df["low"]) / df["close"].shift(1) * 100, 2
        )
        df = df.reset_index(drop=True)
        return df

    except Exception as e:
        print(f"  [ERROR] 获取日线失败 ({code}): {e}")
        return None


def fetch_trading_calendar() -> list[str]:
    """获取全部交易日历，返回排序后的日期字符串列表"""
    cal = ak.tool_trade_date_hist_sina()
    dates = sorted([
        str(d) if not isinstance(d, str) else d
        for d in cal["trade_date"].tolist()
    ])
    return dates


def get_n_trading_days_ago(trade_dates: list[str], date_str: str, n: int) -> str:
    """返回 date_str 往前 n 个交易日的日期"""
    if date_str in trade_dates:
        idx = trade_dates.index(date_str)
    else:
        idx = max(i for i, d in enumerate(trade_dates) if d < date_str)
    return trade_dates[max(0, idx - min(n, idx))]


def count_trading_days_between(trade_dates: list[str],
                               start: str, end: str) -> int:
    """计算两个日期之间的交易日天数（不含首日）"""
    s_idx = trade_dates.index(start) if start in trade_dates else \
        max(i for i, d in enumerate(trade_dates) if d < start)
    e_idx = trade_dates.index(end) if end in trade_dates else \
        max(i for i, d in enumerate(trade_dates) if d < end)
    return max(0, e_idx - s_idx)
