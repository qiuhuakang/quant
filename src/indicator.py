"""指标计算模块 — 黄金分割、缩量、阶梯量、阳线、阶段判定"""
import pandas as pd
import numpy as np


def find_consecutive_boards(df: pd.DataFrame) -> dict | None:
    """
    在日线数据中定位最近一次连续2个涨停的位置。

    涨停判定: pct_chg >= 9.8 且收盘 ≈ 最高（实体版非一字板）

    返回: {"start_idx": int, "end_idx": int, "start_date": str, "end_date": str}
          或 None
    """
    if df is None or len(df) < 2:
        return None

    df = df.reset_index(drop=True)
    # 涨停标记: 涨跌幅>=9.8 且收盘接近最高（排除尾盘炸板）
    limit_flags = (
        (df["pct_chg"] >= 9.8) &
        (df["close"] >= df["high"] * 0.98)
    )

    # 从最新往旧找，取最近的连板事件
    for i in range(len(limit_flags) - 2, -1, -1):
        if limit_flags.iloc[i] and limit_flags.iloc[i + 1]:
            return {
                "start_idx": i,
                "end_idx": i + 1,
                "start_date": str(df.iloc[i]["trade_date"]),
                "end_date": str(df.iloc[i + 1]["trade_date"])
            }

    return None


def calc_golden_fib(df: pd.DataFrame, lu_start_idx: int,
                    lu_end_idx: int) -> dict:
    """计算连续2板区域的黄金分割位"""
    segment = df.iloc[lu_start_idx:lu_end_idx + 1]
    seg_high = segment["high"].max()
    seg_low = segment["low"].min()
    range_val = seg_high - seg_low

    return {
        "high": round(seg_high, 2),
        "low": round(seg_low, 2),
        "fib_618": round(seg_low + range_val * 0.618, 2),
        "fib_500": round(seg_low + range_val * 0.500, 2),
        "range": round(range_val, 2)
    }


def calc_consolidation(df: pd.DataFrame, lu_end_idx: int) -> dict | None:
    """
    从最后一个涨停次日开始计算调整数据
    返回调整天数和调整期数据
    """
    adj_start = lu_end_idx + 1
    if adj_start >= len(df):
        return None

    adj_df = df.iloc[adj_start:].copy().reset_index(drop=True)
    adj_days = len(adj_df)

    return {
        "adj_days": adj_days,
        "adj_data": adj_df,
        "meets_criteria": adj_days <= 5
    }


def is_volume_shrinking(df: pd.DataFrame, lu_start_idx: int,
                        lu_end_idx: int, adj_df: pd.DataFrame,
                        threshold: float = 1.0) -> tuple[bool, float]:
    """回调缩量判定: 回调均量 / 涨停期间均量 < threshold（默认1.0，即小于即可）"""
    lu_vol = df.iloc[lu_start_idx:lu_end_idx + 1]["volume"].mean()
    if lu_vol == 0:
        return False, 1.0
    adj_vol = adj_df["volume"].mean() if len(adj_df) > 0 else lu_vol
    ratio = adj_vol / lu_vol
    return ratio < threshold, round(ratio, 3)


def is_ladder_volume(volumes: pd.Series) -> bool:
    """判定回调期间成交量是否呈阶梯状递减（3日均值60%+时段递减）"""
    if len(volumes) < 3:
        return False

    ma_vol = volumes.rolling(3).mean().dropna()
    if len(ma_vol) < 2:
        return False

    dec_cnt = sum(
        ma_vol.iloc[i] < ma_vol.iloc[i - 1] * 0.95
        for i in range(1, len(ma_vol))
    )
    return dec_cnt >= len(ma_vol) * 0.6


def count_yang_lines(adj_df: pd.DataFrame) -> dict:
    """统计回调期间阳线（含假阳线）"""
    if len(adj_df) == 0:
        return {"false_yang": 0, "true_yang": 0, "yang_ratio": 0.0,
                "preferred": False}

    # 假阳线：收盘 > 开盘（但相对前日下跌）
    false_yang = int(((adj_df["close"] > adj_df["open"]) &
                      (adj_df["close"] < adj_df["close"].shift(1))).sum())
    # 真阳线：收盘 > 前日收盘
    true_yang = int((adj_df["close"] > adj_df["close"].shift(1)).sum())

    total = len(adj_df)
    yang_ratio = round((false_yang + true_yang) / total, 3) if total > 0 else 0.0

    return {
        "false_yang": false_yang,
        "true_yang": true_yang,
        "yang_ratio": yang_ratio,
        "preferred": yang_ratio >= 0.5
    }


def judge_uptrend_stage(df: pd.DataFrame, lu_start_idx: int) -> dict:
    """判断拉升阶段（初期/中期/末期）"""
    pre_data = df.iloc[max(0, lu_start_idx - 20):lu_start_idx]
    if len(pre_data) < 10:
        return {"trend": "unknown", "stage": "unknown", "meets_criteria": False,
                "rise_20d_pct": 0.0}

    start_price = pre_data["close"].iloc[0]
    end_price = pre_data["close"].iloc[-1]
    rise_pct = round((end_price - start_price) / start_price * 100, 2) \
        if start_price > 0 else 0.0

    # MA60/MA120
    lookback_60 = df.iloc[max(0, lu_start_idx - 60):lu_start_idx]
    lookback_120 = df.iloc[max(0, lu_start_idx - 120):lu_start_idx]
    ma60 = lookback_60["close"].mean() if len(lookback_60) > 0 else 0
    ma120 = lookback_120["close"].mean() if len(lookback_120) > 0 else 0
    current_price = df.iloc[lu_start_idx]["close"]

    if ma60 > ma120 and current_price > ma60:
        trend = "uptrend"
        if rise_pct < 25:
            stage = "early"
        elif rise_pct < 50:
            stage = "mid"
        else:
            stage = "late"
    else:
        trend = "not_uptrend"
        stage = "unqualified"

    return {
        "trend": trend,
        "stage": stage,
        "rise_20d_pct": rise_pct,
        "price_vs_ma60": round(current_price / ma60, 3) if ma60 > 0 else 0,
        "meets_criteria": stage in ("early", "mid")
    }


def judge_sandwich_zone(adj_df: pd.DataFrame, fib_result: dict,
                        second_board_close: float) -> dict:
    """判断夹板震荡区（优选条件）"""
    if len(adj_df) == 0:
        return {"is_sandwich": False, "is_breakout": False,
                "is_above_board": False, "preferred": False}

    adj_high = adj_df["high"].max()
    adj_low = adj_df["low"].min()

    is_above_board = adj_low >= second_board_close * 0.98
    is_sandwich = is_above_board and (adj_high <= fib_result["high"] * 1.02)
    is_breakout = adj_low > fib_result["high"]

    return {
        "is_sandwich": is_sandwich,
        "is_breakout": is_breakout,
        "is_above_board": is_above_board,
        "preferred": is_sandwich or is_breakout
    }


def get_protection_price(buy_price: float, second_board_close: float,
                         fib_618: float) -> tuple[float, str]:
    """根据买入位置确定保护位"""
    if buy_price > second_board_close:
        return second_board_close, "board_above"
    else:
        return fib_618, "board_inside"


def analyze_one_stock(code: str, df: pd.DataFrame) -> dict | None:
    """
    对单只股票执行完整量化分析链。

    返回: 分析结果 dict，或 None（不满足连板条件）
    """
    # Step 1: 连板检测
    boards = find_consecutive_boards(df)
    if boards is None:
        return None

    lu_start, lu_end = boards["start_idx"], boards["end_idx"]

    # Step 2: 黄金分割
    fib = calc_golden_fib(df, lu_start, lu_end)

    # Step 3: 调整周期
    adj = calc_consolidation(df, lu_end)
    if adj is None or adj["adj_days"] == 0:
        return None  # 刚涨停完还没调整

    adj_df = adj["adj_data"]

    # Step 4: 缩量判定
    vol_shrinking, vol_ratio = is_volume_shrinking(df, lu_start, lu_end, adj_df)

    # Step 5: 阶梯量（优选）
    ladder = is_ladder_volume(adj_df["volume"])

    # Step 6: 阳线计数（优选）
    yang = count_yang_lines(adj_df)

    # Step 7: 拉升阶段
    stage = judge_uptrend_stage(df, lu_start)

    # Step 8: 夹板/突破（优选）
    second_board_close = df.iloc[lu_end]["close"]
    sandwich = judge_sandwich_zone(adj_df, fib, second_board_close)

    # Step 9: 买点（今日收盘价）
    buy_price = round(df.iloc[-1]["close"], 2)
    protect_price, protect_type = get_protection_price(
        buy_price, second_board_close, fib["fib_618"]
    )

    # 基础条件判定
    meets_basic = all([
        vol_shrinking,                            # 缩量
        adj["adj_days"] <= 5,                     # 调整≤5天
        stage["meets_criteria"],                  # 拉升初期/中期
        adj_df["close"].iloc[-1] >= fib["fib_618"]  # 不破黄金分割
    ])

    # 优选条件计数
    preferred_count = sum([
        ladder, yang["preferred"],
        sandwich["is_above_board"], sandwich["preferred"]
    ])

    return {
        "symbol": code,
        "lu_date_start": boards["start_date"],
        "lu_date_end": boards["end_date"],
        "lu_high": fib["high"],
        "lu_low": fib["low"],
        "fib_618": fib["fib_618"],
        "adj_days": adj["adj_days"],
        "adj_vol_ratio": vol_ratio,
        "adj_yang_ratio": yang["yang_ratio"],
        "adj_min_close": round(adj_df["close"].min(), 2),
        "is_ladder_vol": ladder,
        "uptrend_stage": stage["stage"],
        "is_sandwich": sandwich["is_sandwich"],
        "is_above_board": sandwich["is_above_board"],
        "buy_price": buy_price,
        "protect_price": round(protect_price, 2),
        "protect_type": protect_type,
        "sell_price_3pct": round(buy_price * 1.03, 2),
        "sell_price_5pct": round(buy_price * 1.05, 2),
        "meets_criteria": meets_basic,
        "meets_preferred": preferred_count,
    }
