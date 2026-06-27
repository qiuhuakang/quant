from __future__ import annotations
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
    """回调缩量判定: 二板后首日成交量 / 第二板成交量 < threshold。"""
    if len(adj_df) == 0:
        return False, 1.0

    second_board_vol = df.iloc[lu_end_idx]["volume"]
    if second_board_vol == 0:
        return False, 1.0

    first_adj_vol = adj_df["volume"].iloc[0]
    ratio = first_adj_vol / second_board_vol
    return bool(ratio < threshold), round(float(ratio), 3)


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


def _empty_doji_result() -> dict:
    return {
        "doji_type": "none",
        "doji_label": "",
        "doji_day": 0,
        "doji_volume_state": "",
        "doji_note": "",
        "doji_body_ratio": 0.0,
        "doji_lower_upper_ratio": 0.0,
        "doji_fib_distance_pct": 0.0,
    }


def _doji_metrics(row: pd.Series, fib_618: float = 0.0) -> dict:
    open_ = float(row.get("open", 0) or 0)
    high = float(row.get("high", 0) or 0)
    low = float(row.get("low", 0) or 0)
    close = float(row.get("close", 0) or 0)

    candle_range = high - low
    body = abs(close - open_)
    upper_shadow = high - max(open_, close)
    lower_shadow = min(open_, close) - low
    body_ratio = body / candle_range if candle_range > 0 else 1.0
    amplitude = candle_range / close if close > 0 else 0.0
    body_close_ratio = body / close if close > 0 else 1.0
    lower_upper_ratio = (
        lower_shadow / upper_shadow
        if upper_shadow > 0
        else (99.0 if lower_shadow > 0 else 0.0)
    )
    fib_distance_pct = (
        abs(low - fib_618) / fib_618 * 100
        if fib_618 > 0
        else 0.0
    )

    return {
        "body_ratio": body_ratio,
        "amplitude": amplitude,
        "body_close_ratio": body_close_ratio,
        "upper_shadow": upper_shadow,
        "lower_shadow": lower_shadow,
        "lower_upper_ratio": lower_upper_ratio,
        "fib_distance_pct": fib_distance_pct,
        "is_doji": (
            candle_range > 0
            and body_ratio <= 0.15
            and body_close_ratio <= 0.01
            and amplitude >= 0.015
        ),
        "is_long_lower": (
            candle_range > 0
            and lower_shadow / candle_range >= 0.35
            and lower_shadow >= upper_shadow * 1.5
        ),
        "is_near_fib": fib_618 > 0 and fib_distance_pct <= 2.0,
    }


def _third_day_volume_state(adj_df: pd.DataFrame) -> str:
    if len(adj_df) < 3:
        return ""
    v1, v2, v3 = [float(v) for v in adj_df["volume"].iloc[:3]]
    if v1 > v2 > v3:
        return "连续缩量"
    if v3 > v2:
        return "扩量"
    return "持平"


def _build_doji_result(
    doji_type: str,
    label: str,
    day: int,
    metrics: dict,
    note: str,
    volume_state: str = "",
) -> dict:
    result = _empty_doji_result()
    result.update({
        "doji_type": doji_type,
        "doji_label": label,
        "doji_day": day,
        "doji_volume_state": volume_state,
        "doji_note": note,
        "doji_body_ratio": round(float(metrics["body_ratio"]), 3),
        "doji_lower_upper_ratio": round(float(metrics["lower_upper_ratio"]), 2),
        "doji_fib_distance_pct": round(float(metrics["fib_distance_pct"]), 2),
    })
    return result


def classify_doji_pattern(
    adj_df: pd.DataFrame,
    fib_result: dict,
    second_board_vol: float,
) -> dict:
    """识别二板后调整期的十字星分类和附加量能状态。"""
    if adj_df is None or len(adj_df) == 0:
        return _empty_doji_result()

    fib_618 = float(fib_result.get("fib_618", 0) or 0)
    metrics_by_idx = [
        _doji_metrics(row, fib_618)
        for _, row in adj_df.reset_index(drop=True).iterrows()
    ]

    first_metrics = metrics_by_idx[0]
    first_volume = float(adj_df["volume"].iloc[0])
    if (
        first_metrics["is_doji"]
        and second_board_vol > 0
        and first_volume < second_board_vol
    ):
        ratio = round(first_volume / second_board_vol, 3)
        return _build_doji_result(
            "first_day_shrink_doji",
            "二板后第一天缩量十字星",
            1,
            first_metrics,
            f"首日量/第二板量 {ratio}，二板后分歧未放大。",
        )

    if len(metrics_by_idx) >= 3 and metrics_by_idx[2]["is_doji"]:
        volume_state = _third_day_volume_state(adj_df)
        return _build_doji_result(
            "third_day_doji",
            "二板后第三天十字星",
            3,
            metrics_by_idx[2],
            "分类只看第三天十字星，量能状态单独展示。",
            volume_state,
        )

    for idx, metrics in enumerate(metrics_by_idx):
        if metrics["is_doji"] and metrics["is_near_fib"] and metrics["is_long_lower"]:
            return _build_doji_result(
                "fib_lower_shadow_doji",
                "回踩0.618附近长下影十字星",
                idx + 1,
                metrics,
                f"距0.618约{round(float(metrics['fib_distance_pct']), 2)}%，关键位有承接。",
            )

    for idx, metrics in enumerate(metrics_by_idx):
        if metrics["is_doji"]:
            return _build_doji_result(
                "normal_doji",
                "普通十字星",
                idx + 1,
                metrics,
                "实体较小但不在首日、第三天或0.618特殊位置，仅提示分歧。",
            )

    return _empty_doji_result()


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
    """判断当前拉升阶段（初期/中期/末期），基于最新交易日数据"""
    last_idx = len(df) - 1

    # 20日涨幅（不含当日）
    pre_data = df.iloc[max(0, last_idx - 20):last_idx]
    if len(pre_data) < 10:
        return {"trend": "unknown", "stage": "unknown", "meets_criteria": False,
                "rise_20d_pct": 0.0, "ma60": 0, "ma120": 0,
                "price_vs_ma60": 0}

    start_price = pre_data["close"].iloc[0]
    end_price = pre_data["close"].iloc[-1]
    rise_pct = round((end_price - start_price) / start_price * 100, 2) \
        if start_price > 0 else 0.0

    # MA60/MA120（标准SMA，基于最新交易日）
    lookback_60 = df.iloc[max(0, last_idx - 59):last_idx + 1]
    lookback_120 = df.iloc[max(0, last_idx - 119):last_idx + 1]
    ma60 = lookback_60["close"].mean() if len(lookback_60) > 0 else 0
    ma120 = lookback_120["close"].mean() if len(lookback_120) > 0 else 0
    current_price = df.iloc[last_idx]["close"]

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
        "ma60": round(ma60, 2),
        "ma120": round(ma120, 2),
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

    # Step 5.5: 十字星分类（提示信息，不改变基础入选条件）
    doji = classify_doji_pattern(adj_df, fib, df.iloc[lu_end]["volume"])

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
        "ma60": stage["ma60"],
        "ma120": stage["ma120"],
        "vol_shrinking": vol_shrinking,
        "doji_type": doji["doji_type"],
        "doji_label": doji["doji_label"],
        "doji_day": doji["doji_day"],
        "doji_volume_state": doji["doji_volume_state"],
        "doji_note": doji["doji_note"],
        "doji_body_ratio": doji["doji_body_ratio"],
        "doji_lower_upper_ratio": doji["doji_lower_upper_ratio"],
        "doji_fib_distance_pct": doji["doji_fib_distance_pct"],
        "broke_fib_618": adj_df["close"].iloc[-1] < fib["fib_618"],
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
