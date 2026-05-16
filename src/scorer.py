"""综合评分模块 — 满分100"""
import math


def calc_score(result: dict) -> float:
    """
    综合评分 = 基础条件分(70) + 优选加分(30)，满分100

    result 为 indicator.analyze_one_stock 的返回值
    """
    score = 0.0

    # ─── 基础条件 (0-70分) ────────────────────────────────
    # 调整天数 (越短越好, 1天=15, 2天=12.5, 3天=10, 4天=7.5, 5天=5)
    adj_days = result["adj_days"]
    score += max(0, 15 - (adj_days - 1) * 2.5)

    # 回调量比 (越小越好, 0.2→20分, 1.0→5分)
    vol_ratio = result["adj_vol_ratio"]
    score += max(5, 20 - (vol_ratio - 0.2) * 18.75)

    # 拉升阶段 (初期=20, 中期=15, 其他=0)
    stage_score = {"early": 20, "mid": 15}
    score += stage_score.get(result["uptrend_stage"], 0)

    # 未破黄金分割 (15分)
    fib_618 = result["fib_618"]
    adj_min = result["adj_min_close"]
    score += 15 if adj_min > fib_618 else 5

    # ─── 优选条件 (0-30分) ────────────────────────────────
    # 阶梯量 (+10)
    if result.get("is_ladder_vol", False):
        score += 10

    # 阳线占比 (+8)
    score += min(8, result.get("adj_yang_ratio", 0) * 8)

    # 涨停板上方调整 (+6)
    if result.get("is_above_board", False):
        score += 6

    # 夹板/突破 (+6)
    if result.get("is_sandwich", False):
        score += 6

    return round(min(score, 100.0), 1)
