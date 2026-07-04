from __future__ import annotations
"""HTML 图表报告生成模块 — ECharts K线图 + 均线 + 成交量"""
import json
import os
import pandas as pd
from collections import defaultdict
from html import escape


_DOJI_CLASS_MAP = {
    "first_day_shrink_doji": "first-shrink",
    "third_day_doji": "third-day",
    "fib_lower_shadow_doji": "fib-lower",
    "normal_doji": "normal",
}

def _render_doji_row(item: dict) -> str:
    """Render the optional doji classification tag for a stock card header."""
    label = str(item.get("doji_label") or "")
    if not label:
        return ""

    doji_type = str(item.get("doji_type") or "")
    tag_class = _DOJI_CLASS_MAP.get(doji_type, "normal")
    return f'<span class="doji-tag {tag_class}">{escape(label)}</span>'


def export_html(results: list[dict], dfs: dict, passed: list[dict],
                screen_date: str, multi_results: list[dict] | None = None,
                export_dir: str = "") -> str:
    """生成 HTML 图表报告，返回文件路径"""
    if not export_dir:
        export_dir = os.path.join(os.getcwd(), "data", "export")
    os.makedirs(export_dir, exist_ok=True)
    html = _build_html(results, dfs, passed, screen_date, multi_results)
    path = os.path.join(export_dir, f"screen_result_{screen_date}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    # 同时写一份 latest
    latest = os.path.join(export_dir, "screen_result_latest.html")
    with open(latest, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def _extract_chart_data(df: pd.DataFrame, analysis: dict) -> dict | None:
    """从一支股票的 DataFrame 和 analysis dict 提取图表所需数据"""
    try:
        df = df.sort_values("trade_date", ascending=True).reset_index(drop=True)
        dates = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d").tolist()

        ohlc = []
        for _, row in df.iterrows():
            ohlc.append([
                float(row["open"]),
                float(row["close"]),
                float(row["low"]),
                float(row["high"]),
            ])

        volumes = [float(v) for v in df["volume"].tolist()]

        # 滚动均线（用 float 转换，NaN → None → JSON null）
        close_series = df["close"].astype(float)
        ma60 = close_series.rolling(60).mean()
        ma120 = close_series.rolling(120).mean()

        def to_list(s: pd.Series) -> list:
            return [None if pd.isna(x) else round(float(x), 2) for x in s.tolist()]

        ma60_list = to_list(ma60)
        ma120_list = to_list(ma120)

        # 连板区域索引
        lu_start = analysis.get("lu_date_start", "")
        lu_end = analysis.get("lu_date_end", "")
        lu_start_idx = dates.index(lu_start) if lu_start in dates else None
        lu_end_idx = dates.index(lu_end) if lu_end in dates else None

        return {
            "symbol": analysis.get("symbol", ""),
            "name": analysis.get("name", ""),
            "dates": dates,
            "ohlc": ohlc,
            "volumes": volumes,
            "ma60": ma60_list,
            "ma120": ma120_list,
            "lu_start_idx": lu_start_idx,
            "lu_end_idx": lu_end_idx,
            "lu_start_date": lu_start,
            "lu_end_date": lu_end,
            "fib_618": analysis.get("fib_618", 0),
            "buy_price": analysis.get("buy_price", 0),
            "protect_price": analysis.get("protect_price", 0),
            "lu_high": analysis.get("lu_high", 0),
            "lu_low": analysis.get("lu_low", 0),
            "adj_days": analysis.get("adj_days", 0),
            "adj_vol_ratio": analysis.get("adj_vol_ratio", 0),
            "adj_yang_ratio": analysis.get("adj_yang_ratio", 0),
            "uptrend_stage": analysis.get("uptrend_stage", ""),
            "score": analysis.get("score", 0),
            "meets_criteria": analysis.get("meets_criteria", False),
            "doji_type": analysis.get("doji_type", "none"),
            "doji_label": analysis.get("doji_label", ""),
            "doji_day": analysis.get("doji_day", 0),
            "doji_volume_state": analysis.get("doji_volume_state", ""),
            "doji_note": analysis.get("doji_note", ""),
            "doji_body_ratio": analysis.get("doji_body_ratio", 0),
            "doji_lower_upper_ratio": analysis.get("doji_lower_upper_ratio", 0),
            "doji_fib_distance_pct": analysis.get("doji_fib_distance_pct", 0),
        }
    except Exception:
        return None


def _fail_key(r: dict) -> tuple:
    """返回一支股票的 4 维不达标元组"""
    return (
        r.get("uptrend_stage", "") not in ("early", "mid"),
        not r.get("vol_shrinking", False),
        r.get("adj_days", 0) > 5,
        bool(r.get("broke_fib_618", False)),
    )


def _split_relaxed(results: list[dict]) -> tuple[list[dict], list[dict]]:
    """将未达标结果分为放宽条件入选和剩余未达标"""
    allowed_keys = {
        (True, False, False, False),   # 仅阶段不符
        (False, True, False, False),   # 仅量比≥1.0、未缩量
        (True, True, False, False),    # 阶段不符 + 量比≥1.0、未缩量
    }
    relaxed, remaining = [], []
    for r in results:
        if _fail_key(r) in allowed_keys:
            relaxed.append(r)
        else:
            remaining.append(r)
    return relaxed, remaining


def _group_excluded(results: list[dict]) -> dict[str, list[dict]]:
    """按 4 维度不达标原因分组"""
    fail_labels = [
        "阶段不符",
        "量比≥1.0、未缩量",
        "调整天数＞5",
        "破618",
    ]

    def make_cat_name(key):
        parts = [fail_labels[i] for i, v in enumerate(key) if v]
        if not parts:
            return "未分类"
        if len(parts) == 1:
            return f"仅{parts[0]}"
        return " + ".join(parts)

    groups: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        groups[make_cat_name(_fail_key(r))].append(r)

    # 按失败维度数量排序
    def sort_key(item):
        name = item[0]
        fail_count = name.count("+") + 1
        if name == "未分类":
            fail_count = 0
        return (fail_count, name)

    return dict(sorted(groups.items(), key=sort_key))


def _build_html(results: list[dict], dfs: dict, passed: list[dict],
                screen_date: str, multi_results: list[dict] | None = None) -> str:
    """组装完整 HTML 文档"""

    # ── 准备数据：按 board_type 拆分 ──────────────────────
    excluded = [r for r in results if not r["meets_criteria"]]
    passed_sorted = sorted(passed, key=lambda x: x["score"], reverse=True)

    # 2板
    passed_two = [r for r in passed_sorted if r.get("board_type") != "multi"]
    excluded_two_all = [r for r in excluded if r.get("board_type") != "multi"]
    relaxed_two, excluded_two = _split_relaxed(excluded_two_all)
    relaxed_two_groups = _group_excluded(relaxed_two)
    excluded_two_groups = _group_excluded(excluded_two)

    # 多板
    multi_results = multi_results or []
    multi_passed = sorted(
        [r for r in multi_results if r["meets_criteria"]],
        key=lambda x: x["score"], reverse=True
    )
    multi_excluded_all = [r for r in multi_results if not r["meets_criteria"]]
    relaxed_multi, multi_excluded = _split_relaxed(multi_excluded_all)
    relaxed_multi_groups = _group_excluded(relaxed_multi)
    multi_excluded_groups = _group_excluded(multi_excluded)

    def _build_charts(stock_list):
        """从结果列表提取图表数据 dict"""
        charts = {}
        for r in stock_list:
            code = r["symbol"]
            if code in dfs:
                cd = _extract_chart_data(dfs[code], r)
                if cd:
                    charts[code] = cd
        return charts

    def _build_group_charts(groups: dict) -> dict[str, list[dict]]:
        """从分组结果提取图表数据"""
        result: dict[str, list[dict]] = {}
        for cat_name, stocks in groups.items():
            result[cat_name] = []
            for r in stocks:
                code = r["symbol"]
                if code in dfs:
                    cd = _extract_chart_data(dfs[code], r)
                    if cd:
                        result[cat_name].append(cd)
        return result

    passed_two_charts = _build_charts(passed_two)
    relaxed_two_charts = _build_group_charts(relaxed_two_groups)
    excluded_two_charts = _build_group_charts(excluded_two_groups)
    multi_passed_charts = _build_charts(multi_passed)
    relaxed_multi_charts = _build_group_charts(relaxed_multi_groups)
    multi_excluded_charts = _build_group_charts(multi_excluded_groups)

    # 汇总 JSON
    all_chart_data: dict[str, dict] = {}
    for charts in [passed_two_charts, multi_passed_charts]:
        all_chart_data.update(charts)
    for charts_dict in [relaxed_two_charts, excluded_two_charts,
                         relaxed_multi_charts, multi_excluded_charts]:
        for charts in charts_dict.values():
            for cd in charts:
                all_chart_data[cd["symbol"]] = cd

    json_data = json.dumps(all_chart_data, ensure_ascii=False)

    # 中文数字
    cn_num = ["一","二","三","四","五","六","七","八","九","十",
              "十一","十二","十三","十四","十五"]

    # ── 构建 2板入选 HTML ────────────────────────────────
    passed_two_html = ""
    for i, r in enumerate(passed_two):
        code = r["symbol"]
        name = r.get("name", "")[:6]
        score = r["score"]
        stage = r["uptrend_stage"]
        adj_days = r["adj_days"]
        vol_ratio = r["adj_vol_ratio"]
        buy = r["buy_price"]
        protect = r["protect_price"]
        chart_id = f"chart_p_{code}"
        doji_html = _render_doji_row(r)
        passed_two_html += f'''
        <div class="stock-card passed" data-symbol="{code}" data-chart="{chart_id}">
          <div class="card-header" onclick="toggleCard(this)">
            <div class="card-left">
              <span class="rank">#{i + 1}</span>
              <span class="symbol">{code}</span>
              <span class="name">{name}</span>
              <span class="score-badge">{score}分</span>
            </div>
            <div class="card-meta">
              <span>阶段: <b>{stage}</b></span>
              <span>调整: {adj_days}天</span>
              <span>量比: {vol_ratio}</span>
              <span>买入: ¥{buy}</span>
              <span>保护: ¥{protect}</span>
            </div>
            {doji_html}
            <span class="expand-icon">▸</span>
          </div>
          <div class="card-body">
            <div id="{chart_id}" class="chart-container"></div>
          </div>
        </div>'''

    # ── 构建 2板放宽条件入选 HTML ──────────────────────────
    relaxed_two_html = ""
    group_idx = 0
    for cat_name, charts in relaxed_two_charts.items():
        group_idx += 1
        cn = cn_num[group_idx - 1] if group_idx - 1 < len(cn_num) else str(group_idx)
        relaxed_two_html += f'''
        <div class="relaxed-group">
          <div class="group-header relaxed-header" onclick="toggleGroup(this)">
            <span class="group-title">{cn}、{cat_name}</span>
            <span class="group-count">{len(charts)}只</span>
            <span class="expand-icon">▸</span>
          </div>
          <div class="group-body">'''
        for cd in charts:
            code = cd["symbol"]
            name = cd["name"][:6]
            stage = cd["uptrend_stage"]
            adj_days = cd["adj_days"]
            vol_ratio = cd["adj_vol_ratio"]
            chart_id = f"chart_r_{code}"
            doji_html = _render_doji_row(cd)
            score = cd["score"]
            relaxed_two_html += f'''
            <div class="stock-card relaxed" data-symbol="{code}" data-chart="{chart_id}">
              <div class="card-header" onclick="event.stopPropagation(); toggleCard(this)">
                <div class="card-left">
                  <span class="symbol">{code}</span>
                  <span class="name">{name}</span>
                  <span class="score-badge">{score}分</span>
                </div>
                <div class="card-meta">
                  <span>阶段: <b>{stage}</b></span>
                  <span>调整: {adj_days}天</span>
                  <span>量比: {vol_ratio}</span>
                  <span>MA60: {cd["ma60"][-1] if cd["ma60"][-1] else "-"}</span>
                  <span>MA120: {cd["ma120"][-1] if cd["ma120"][-1] else "-"}</span>
                </div>
                {doji_html}
                <span class="expand-icon">▸</span>
              </div>
              <div class="card-body">
                <div id="{chart_id}" class="chart-container"></div>
              </div>
            </div>'''
        relaxed_two_html += '''
          </div>
        </div>'''

    # ── 构建 2板未达标 HTML ────────────────────────────────
    excluded_two_html = ""
    group_idx = 0
    for cat_name, charts in excluded_two_charts.items():
        group_idx += 1
        cn = cn_num[group_idx - 1] if group_idx - 1 < len(cn_num) else str(group_idx)
        excluded_two_html += f'''
        <div class="excluded-group">
          <div class="group-header" onclick="toggleGroup(this)">
            <span class="group-title">{cn}、{cat_name}</span>
            <span class="group-count">{len(charts)}只</span>
            <span class="expand-icon">▸</span>
          </div>
          <div class="group-body">'''
        for cd in charts:
            code = cd["symbol"]
            name = cd["name"][:6]
            stage = cd["uptrend_stage"]
            adj_days = cd["adj_days"]
            vol_ratio = cd["adj_vol_ratio"]
            chart_id = f"chart_e_{code}"
            doji_html = _render_doji_row(cd)
            excluded_two_html += f'''
            <div class="stock-card excluded" data-symbol="{code}" data-chart="{chart_id}">
              <div class="card-header" onclick="event.stopPropagation(); toggleCard(this)">
                <div class="card-left">
                  <span class="symbol">{code}</span>
                  <span class="name">{name}</span>
                </div>
                <div class="card-meta">
                  <span>阶段: <b>{stage}</b></span>
                  <span>调整: {adj_days}天</span>
                  <span>量比: {vol_ratio}</span>
                  <span>MA60: {cd["ma60"][-1] if cd["ma60"][-1] else "-"}</span>
                  <span>MA120: {cd["ma120"][-1] if cd["ma120"][-1] else "-"}</span>
                </div>
                {doji_html}
                <span class="expand-icon">▸</span>
              </div>
              <div class="card-body">
                <div id="{chart_id}" class="chart-container"></div>
              </div>
            </div>'''
        excluded_two_html += '''
          </div>
        </div>'''

    # ── 构建多板入选 HTML ────────────────────────────────
    multi_passed_html = ""
    for i, r in enumerate(multi_passed):
        code = r["symbol"]
        name = r.get("name", "")[:6]
        score = r["score"]
        stage = r["uptrend_stage"]
        bc = r.get("board_count", 3)
        adj_days = r["adj_days"]
        vol_ratio = r["adj_vol_ratio"]
        buy = r["buy_price"]
        protect = r["protect_price"]
        chart_id = f"chart_mp_{code}"
        doji_html = _render_doji_row(r)
        multi_passed_html += f'''
        <div class="stock-card multi" data-symbol="{code}" data-chart="{chart_id}">
          <div class="card-header" onclick="toggleCard(this)">
            <div class="card-left">
              <span class="rank">#{i + 1}</span>
              <span class="symbol">{code}</span>
              <span class="name">{name}</span>
              <span class="score-badge">{score}分</span>
            </div>
            <div class="card-meta">
              <span>阶段: <b>{stage}</b></span>
              <span>调整: {adj_days}天</span>
              <span>量比: {vol_ratio}</span>
              <span>买入: ¥{buy}</span>
              <span>保护: ¥{protect}</span>
            </div>
            {doji_html}
            <span class="expand-icon">▸</span>
          </div>
          <div class="card-body">
            <div id="{chart_id}" class="chart-container"></div>
          </div>
        </div>'''

    # ── 构建多板放宽条件入选 HTML ──────────────────────────
    relaxed_multi_html = ""
    group_idx = 0
    for cat_name, charts in relaxed_multi_charts.items():
        group_idx += 1
        cn = cn_num[group_idx - 1] if group_idx - 1 < len(cn_num) else str(group_idx)
        relaxed_multi_html += f'''
        <div class="relaxed-group multi-relaxed-group">
          <div class="group-header relaxed-header" onclick="toggleGroup(this)">
            <span class="group-title">{cn}、{cat_name}</span>
            <span class="group-count">{len(charts)}只</span>
            <span class="expand-icon">▸</span>
          </div>
          <div class="group-body">'''
        for cd in charts:
            code = cd["symbol"]
            name = cd["name"][:6]
            stage = cd["uptrend_stage"]
            adj_days = cd["adj_days"]
            vol_ratio = cd["adj_vol_ratio"]
            score = cd["score"]
            chart_id = f"chart_mr_{code}"
            doji_html = _render_doji_row(cd)
            relaxed_multi_html += f'''
            <div class="stock-card multi-relaxed" data-symbol="{code}" data-chart="{chart_id}">
              <div class="card-header" onclick="event.stopPropagation(); toggleCard(this)">
                <div class="card-left">
                  <span class="symbol">{code}</span>
                  <span class="name">{name}</span>
                  <span class="score-badge">{score}分</span>
                </div>
                <div class="card-meta">
                  <span>阶段: <b>{stage}</b></span>
                  <span>调整: {adj_days}天</span>
                  <span>量比: {vol_ratio}</span>
                  <span>MA60: {cd["ma60"][-1] if cd["ma60"][-1] else "-"}</span>
                  <span>MA120: {cd["ma120"][-1] if cd["ma120"][-1] else "-"}</span>
                </div>
                {doji_html}
                <span class="expand-icon">▸</span>
              </div>
              <div class="card-body">
                <div id="{chart_id}" class="chart-container"></div>
              </div>
            </div>'''
        relaxed_multi_html += '''
          </div>
        </div>'''

    # ── 构建多板未达标 HTML ────────────────────────────────
    multi_excluded_html = ""
    group_idx = 0
    for cat_name, charts in multi_excluded_charts.items():
        group_idx += 1
        cn = cn_num[group_idx - 1] if group_idx - 1 < len(cn_num) else str(group_idx)
        multi_excluded_html += f'''
        <div class="excluded-group multi-group">
          <div class="group-header" onclick="toggleGroup(this)">
            <span class="group-title">{cn}、{cat_name}</span>
            <span class="group-count">{len(charts)}只</span>
            <span class="expand-icon">▸</span>
          </div>
          <div class="group-body">'''
        for cd in charts:
            code = cd["symbol"]
            name = cd["name"][:6]
            stage = cd["uptrend_stage"]
            adj_days = cd["adj_days"]
            vol_ratio = cd["adj_vol_ratio"]
            chart_id = f"chart_me_{code}"
            doji_html = _render_doji_row(cd)
            multi_excluded_html += f'''
            <div class="stock-card multi-excluded" data-symbol="{code}" data-chart="{chart_id}">
              <div class="card-header" onclick="event.stopPropagation(); toggleCard(this)">
                <div class="card-left">
                  <span class="symbol">{code}</span>
                  <span class="name">{name}</span>
                </div>
                <div class="card-meta">
                  <span>阶段: <b>{stage}</b></span>
                  <span>调整: {adj_days}天</span>
                  <span>量比: {vol_ratio}</span>
                  <span>MA60: {cd["ma60"][-1] if cd["ma60"][-1] else "-"}</span>
                  <span>MA120: {cd["ma120"][-1] if cd["ma120"][-1] else "-"}</span>
                </div>
                {doji_html}
                <span class="expand-icon">▸</span>
              </div>
              <div class="card-body">
                <div id="{chart_id}" class="chart-container"></div>
              </div>
            </div>'''
        multi_excluded_html += '''
          </div>
        </div>'''

    # ── 完整 HTML ────────────────────────────────────────
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>选股报告 - {screen_date}</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background: #f5f6fa; color: #2c3e50; padding-bottom: 40px; }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
.header {{ background: linear-gradient(135deg, #1a1a2e, #16213e); color: white; padding: 24px 32px; border-radius: 12px; margin-bottom: 20px; }}
.header h1 {{ font-size: 24px; margin-bottom: 6px; }}
.header .date {{ font-size: 14px; color: #a0aec0; }}
.summary {{ display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }}
.summary-card {{ flex: 1; min-width: 120px; background: white; border-radius: 10px; padding: 16px 20px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
.summary-card .num {{ font-size: 32px; font-weight: 700; }}
.summary-card .label {{ font-size: 13px; color: #7f8c8d; margin-top: 4px; }}
.summary-card.pass .num {{ color: #27ae60; }}
.summary-card.fail .num {{ color: #e74c3c; }}
.summary-card.total .num {{ color: #2c3e50; }}
.summary-card.multi .num {{ color: #8e44ad; }}

.tabs-wrapper {{ display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }}
.tabs {{ display: flex; gap: 8px; flex: 1; }}
.tab-btn {{ padding: 10px 24px; border: none; border-radius: 20px; font-size: 15px; cursor: pointer; font-weight: 600; transition: all 0.2s; white-space: nowrap; }}
.tab-btn.pass {{ background: #eafaf1; color: #27ae60; }}
.tab-btn.pass.active {{ background: #27ae60; color: white; }}
.tab-btn.fail {{ background: #fdedec; color: #e74c3c; }}
.tab-btn.fail.active {{ background: #e74c3c; color: white; }}
.tab-btn.multi {{ background: #f3eef8; color: #8e44ad; }}
.tab-btn.multi.active {{ background: #8e44ad; color: white; }}
.tab-btn.doji {{ background: #fff4df; color: #b45309; }}
.tab-btn.doji.active {{ background: #b45309; color: white; }}
.tab-btn.hold {{ background: #f5f6fa; color: #2c3e50; }}
.tab-btn.hold.active {{ background: #2c3e50; color: white; }}
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}

.search-box {{ position: relative; width: 220px; flex-shrink: 0; }}
.search-input {{ width: 100%; padding: 8px 14px 8px 34px; border: 1px solid #ddd; border-radius: 20px; font-size: 14px; outline: none; font-family: inherit; transition: border-color 0.2s; background: white; }}
.search-input:focus {{ border-color: #1a1a2e; box-shadow: 0 0 0 2px rgba(26,26,46,0.1); }}
.search-input::placeholder {{ color: #bdc3c7; }}
.search-icon {{ position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: #bdc3c7; font-size: 14px; pointer-events: none; }}
.search-dropdown {{ display: none; position: absolute; top: 100%; left: 0; right: 0; margin-top: 4px; background: white; border-radius: 10px; box-shadow: 0 4px 20px rgba(0,0,0,0.15); max-height: 320px; overflow-y: auto; z-index: 100; }}
.search-dropdown.open {{ display: block; }}
.search-item {{ display: flex; align-items: center; padding: 10px 14px; cursor: pointer; gap: 10px; font-size: 13px; transition: background 0.15s; border-bottom: 1px solid #f0f0f0; }}
.search-item:last-child {{ border-bottom: none; }}
.search-item:hover {{ background: #f5f6fa; }}
.search-item .s-symbol {{ font-weight: 700; color: #2c3e50; min-width: 55px; }}
.search-item .s-name {{ color: #7f8c8d; flex: 1; }}
.search-item .s-tab {{ font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600; white-space: nowrap; }}
.search-item .s-tab.pass {{ background: #eafaf1; color: #27ae60; }}
.search-item .s-tab.fail {{ background: #fdedec; color: #e74c3c; }}
.search-item .s-tab.multi {{ background: #f3eef8; color: #8e44ad; }}
.search-item .s-tab.me {{ background: #ffeaea; color: #c0392b; }}
.search-item .s-tab.doji {{ background: #fff4df; color: #b45309; }}
.search-no-result {{ padding: 16px; text-align: center; color: #bdc3c7; font-size: 13px; }}
.search-clear {{ display: none; position: absolute; right: 10px; top: 50%; transform: translateY(-50%); background: none; border: none; color: #bdc3c7; cursor: pointer; font-size: 16px; padding: 0; line-height: 1; }}
.search-clear.visible {{ display: block; }}
.search-clear:hover {{ color: #555; }}

.stock-card.highlight {{ animation: highlightPulse 1.5s ease-in-out; }}
@keyframes highlightPulse {{ 0% {{ box-shadow: 0 0 0 0 rgba(41,128,185,0.5); }} 50% {{ box-shadow: 0 0 0 8px rgba(41,128,185,0); }} 100% {{ box-shadow: 0 1px 4px rgba(0,0,0,0.05); }} }}

.stock-card {{ background: white; border-radius: 8px; margin-bottom: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.05); overflow: hidden; transition: box-shadow 0.2s; }}
.stock-card:hover {{ box-shadow: 0 2px 12px rgba(0,0,0,0.1); }}
.stock-card.passed {{ border-left: 4px solid #27ae60; }}
.stock-card.excluded {{ border-left: 4px solid #e74c3c; }}
.stock-card.multi {{ border-left: 4px solid #8e44ad; }}
.stock-card.multi-excluded {{ border-left: 4px solid #c0392b; }}

.card-header {{ display: flex; align-items: center; padding: 12px 16px; cursor: pointer; user-select: none; transition: background 0.15s; gap: 16px; }}
.card-header:hover {{ background: #f8f9fa; }}
.passed .card-header:hover {{ background: #f0faf3; }}
.excluded .card-header:hover {{ background: #fef5f5; }}

.card-left {{ display: flex; align-items: center; gap: 10px; min-width: 240px; }}
.rank {{ font-weight: 700; font-size: 16px; color: #7f8c8d; width: 32px; }}
.symbol {{ font-weight: 700; font-size: 14px; color: #2c3e50; }}
.name {{ font-size: 13px; color: #7f8c8d; }}
.score-badge {{ background: #27ae60; color: white; padding: 2px 10px; border-radius: 12px; font-size: 13px; font-weight: 600; }}
.board-badge {{ background: #8e44ad; color: white; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }}

.card-meta {{ display: flex; gap: 16px; flex: 1; font-size: 13px; color: #555; flex-wrap: wrap; }}
.card-meta b {{ color: #2c3e50; }}

.expand-icon {{ font-size: 14px; color: #bdc3c7; transition: transform 0.2s; width: 20px; text-align: center; }}
.card-header.expanded .expand-icon {{ transform: rotate(90deg); }}

.card-body {{ display: none; padding: 0 8px 8px; }}
.card-body.open {{ display: block; }}

.chart-container {{ width: 100%; height: 520px; }}

.excluded-group {{ margin-bottom: 8px; }}
.group-header {{ display: flex; align-items: center; padding: 10px 16px; background: white; border-radius: 8px; cursor: pointer; user-select: none; border-left: 4px solid #e74c3c; margin-bottom: 4px; }}
.group-header:hover {{ background: #fef5f5; }}
.group-title {{ font-weight: 600; font-size: 14px; color: #2c3e50; flex: 1; }}
.group-count {{ font-size: 13px; color: #e74c3c; font-weight: 600; margin-right: 12px; }}
.group-header .expand-icon {{ font-size: 14px; color: #bdc3c7; transition: transform 0.2s; }}
.group-header.expanded .expand-icon {{ transform: rotate(90deg); }}
.group-body {{ display: none; }}
.group-body.open {{ display: block; }}
.multi-group .group-header {{ border-left-color: #8e44ad; }}
.multi-group .group-header:hover {{ background: #f9f5fc; }}

.relaxed-group {{ margin-bottom: 8px; }}
.relaxed-group .group-header {{ border-left-color: #2980b9; }}
.relaxed-group .group-header:hover {{ background: #eaf2f8; }}
.stock-card.relaxed {{ border-left: 4px solid #2980b9; }}
.stock-card.multi-relaxed {{ border-left: 4px solid #7d3c98; }}
.card-header > .doji-tag {{ margin-left: auto; }}
.doji-tag {{ display: inline-flex; align-items: center; min-height: 22px; padding: 2px 7px; border-radius: 5px; font-size: 12px; line-height: 1.3; font-weight: 700; white-space: nowrap; border: 1px solid transparent; }}
.doji-tag.first-shrink {{ color: #1f8f4d; background: #e8f7ee; border-color: #bfe8cf; }}
.doji-tag.third-day {{ color: #2563eb; background: #e8f0ff; border-color: #c7d7ff; }}
.doji-tag.fib-lower {{ color: #b45309; background: #fff4df; border-color: #ffd69a; }}
.doji-tag.normal {{ color: #52616f; background: #edf1f5; border-color: #d7dee6; }}
.doji-tab-toolbar {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; background: white; border-left: 4px solid #b45309; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.05); }}
.doji-tab-title {{ font-size: 14px; font-weight: 700; color: #2c3e50; white-space: nowrap; }}
.doji-tab-title b {{ color: #b45309; font-size: 18px; }}
.doji-source-chips {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }}
.doji-source-chip {{ display: inline-flex; align-items: center; height: 24px; padding: 0 9px; border-radius: 12px; font-size: 12px; font-weight: 700; border: 1px solid transparent; }}
.doji-source-chip.two-pass, .doji-source-badge.two-pass {{ color: #1f8f4d; background: #eafaf1; border-color: #c9efd7; }}
.doji-source-chip.two-relaxed, .doji-source-badge.two-relaxed {{ color: #1d6fa5; background: #eaf2f8; border-color: #cfe3f1; }}
.doji-source-chip.three-pass, .doji-source-badge.three-pass {{ color: #7d3c98; background: #f3eef8; border-color: #e2d3ee; }}
.doji-source-chip.three-relaxed, .doji-source-badge.three-relaxed {{ color: #6c3483; background: #f0e6f5; border-color: #dbc7e7; }}
.doji-tab-list {{ display: grid; gap: 8px; }}
.doji-list-card {{ background: white; border-left: 4px solid #b45309; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.05); overflow: hidden; transition: box-shadow 0.2s, transform 0.2s; }}
.doji-list-card:hover {{ box-shadow: 0 2px 12px rgba(0,0,0,0.1); transform: translateY(-1px); }}
.doji-list-card.two-pass {{ border-left-color: #27ae60; }}
.doji-list-card.two-relaxed {{ border-left-color: #2980b9; }}
.doji-list-card.three-pass {{ border-left-color: #8e44ad; }}
.doji-list-card.three-relaxed {{ border-left-color: #7d3c98; }}
.doji-list-card .card-header {{ cursor: pointer; }}
.doji-list-card .card-header > .doji-tag {{ margin-left: 0; }}
.doji-list-card .card-left {{ min-width: 260px; }}
.stock-card .symbol, .doji-list-card .symbol, .hold-list-card .symbol {{ color: #1f2d3d; font-size: 15px; font-weight: 900; letter-spacing: 0; }}
.stock-card .name, .doji-list-card .name, .hold-list-card .name {{ color: #2c3e50; font-size: 14px; font-weight: 800; }}
.doji-source-badge {{ display: inline-flex; align-items: center; min-height: 22px; padding: 2px 8px; border-radius: 5px; font-size: 12px; line-height: 1.3; font-weight: 700; white-space: nowrap; border: 1px solid transparent; }}
.doji-empty {{ background: white; border-radius: 8px; padding: 24px 16px; color: #95a5a6; text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,0.05); }}
.hold-tab-toolbar {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; background: white; border-left: 4px solid #27ae60; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.05); }}
.hold-tab-title {{ font-size: 14px; font-weight: 700; color: #2c3e50; white-space: nowrap; }}
.hold-tab-title b {{ color: #27ae60; font-size: 18px; }}
.hold-tab-note {{ font-size: 12px; color: #7f8c8d; line-height: 1.5; text-align: right; }}
.hold-tab-list {{ display: grid; gap: 8px; }}
.hold-list-card {{ background: white; border-left: 4px solid #27ae60; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.05); overflow: hidden; transition: box-shadow 0.2s; }}
.hold-list-card:hover {{ box-shadow: 0 2px 12px rgba(0,0,0,0.1); }}
.hold-list-card .card-header {{ cursor: pointer; }}
.hold-list-card .card-header:hover {{ background: #f8f9fa; }}
.hold-list-card .card-left {{ min-width: 240px; }}
.hold-badge, .hold-source-badge {{ display: inline-flex; align-items: center; min-height: 22px; padding: 2px 8px; border-radius: 5px; font-size: 12px; line-height: 1.3; font-weight: 700; white-space: nowrap; color: #52616f; background: #edf1f5; border: 1px solid #d7dee6; }}
.hold-metric b {{ color: #2c3e50; }}
.hold-empty {{ background: white; border-radius: 8px; padding: 24px 16px; color: #95a5a6; text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,0.05); }}
.multi-relaxed-group .group-header {{ border-left-color: #7d3c98; }}
.multi-relaxed-group .group-header:hover {{ background: #f3eef8; }}

@media (max-width: 768px) {{
  body {{ padding-bottom: 24px; overflow-x: hidden; }}
  .container {{ width: 100%; max-width: 100%; padding: 10px; overflow-x: hidden; }}
  .header {{ padding: 16px 18px; border-radius: 8px; margin-bottom: 12px; }}
  .header h1 {{ font-size: 19px; line-height: 1.35; }}
  .summary {{ gap: 8px; margin-bottom: 12px; }}
  .summary-card {{ min-width: calc(50% - 4px); padding: 12px 10px; border-radius: 8px; }}
  .summary-card .num {{ font-size: 24px; }}
  .tabs-wrapper {{ flex-direction: column; align-items: stretch; }}
  .tabs {{ width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; padding-bottom: 2px; gap: 6px; flex: 0 0 auto; }}
  .tabs::-webkit-scrollbar {{ display: none; }}
  .tab-btn {{ flex: 0 0 auto; padding: 8px 14px; font-size: 13px; border-radius: 16px; }}
  .search-box {{ width: 100%; }}
  .search-input {{ padding-top: 9px; padding-bottom: 9px; }}
  .stock-card, .doji-list-card, .hold-list-card {{ width: 100%; margin-bottom: 8px; border-radius: 8px; }}
  .card-header {{ align-items: flex-start; flex-wrap: wrap; gap: 8px; padding: 11px 12px; }}
  .card-left {{ min-width: 0; width: 100%; flex-wrap: wrap; gap: 8px; }}
  .doji-list-card .card-left {{ min-width: 0; }}
  .hold-list-card .card-left {{ min-width: 0; }}
  .rank {{ width: auto; min-width: 28px; }}
  .card-meta {{ width: 100%; flex: 0 0 100%; gap: 8px 12px; font-size: 12px; }}
  .card-meta span {{ white-space: nowrap; }}
  .card-header > .doji-tag, .doji-list-card .card-header > .doji-tag {{ margin-left: 0; max-width: calc(100% - 34px); white-space: normal; }}
  .doji-source-badge {{ margin-left: 0; }}
  .expand-icon {{ margin-left: auto; }}
  .card-body {{ padding: 0 4px 8px; }}
  .chart-container {{ height: clamp(320px, 70vh, 520px); min-height: 320px; max-width: 100%; }}
  .group-header {{ padding: 10px 12px; }}
  .group-title {{ font-size: 13px; line-height: 1.4; }}
  .doji-tab-toolbar {{ flex-direction: column; align-items: stretch; gap: 10px; padding: 11px 12px; }}
  .hold-tab-toolbar {{ flex-direction: column; align-items: stretch; gap: 10px; padding: 11px 12px; }}
  .doji-tab-title {{ white-space: normal; }}
  .hold-tab-title {{ white-space: normal; }}
  .hold-tab-note {{ text-align: left; }}
  .doji-source-chips {{ justify-content: flex-start; }}
}}

@media (max-width: 420px) {{
  .summary-card {{ min-width: calc(50% - 4px); }}
  .card-meta {{ gap: 6px 10px; }}
  .score-badge, .board-badge {{ font-size: 11px; padding: 2px 7px; }}
  .doji-tag, .doji-source-badge, .hold-badge, .hold-source-badge {{ font-size: 11px; }}
}}

.footer {{ text-align: center; padding: 30px 0 10px; font-size: 12px; color: #bdc3c7; }}
.footer a {{ color: #bdc3c7; }}

/* ── Chat Widget ── */
.chat-toggle {{
  position: fixed; bottom: 24px; right: 24px; z-index: 9999;
  width: 56px; height: 56px; border-radius: 50%; border: none;
  background: linear-gradient(135deg, #1a1a2e, #16213e);
  color: white; font-size: 24px; cursor: pointer;
  box-shadow: 0 4px 16px rgba(0,0,0,0.25); transition: transform 0.2s;
  display: flex; align-items: center; justify-content: center;
}}
.chat-toggle:hover {{ transform: scale(1.08); }}
.chat-toggle .badge {{
  position: absolute; top: -2px; right: -2px;
  width: 14px; height: 14px; border-radius: 50%; background: #e74c3c;
  border: 2px solid white;
}}
.chat-toggle .badge.online {{ background: #27ae60; }}

.chat-panel {{
  position: fixed; bottom: 90px; right: 24px; z-index: 9998;
  width: 420px; max-height: 600px; height: 520px;
  background: white; border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.18);
  display: none; flex-direction: column; overflow: hidden;
  transition: opacity 0.2s;
}}
.chat-panel.open {{ display: flex; }}

.chat-panel-header {{
  background: linear-gradient(135deg, #1a1a2e, #16213e);
  color: white; padding: 14px 18px; font-size: 15px; font-weight: 600;
  display: flex; align-items: center; justify-content: space-between;
}}
.chat-panel-header .status-dot {{
  width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px;
  background: #95a5a6;
}}
.chat-panel-header .status-dot.online {{ background: #27ae60; }}
.chat-panel-header .close-btn {{
  background: none; border: none; color: #a0aec0; font-size: 20px; cursor: pointer;
}}
.chat-panel-header .close-btn:hover {{ color: white; }}

.chat-messages {{
  flex: 1; overflow-y: auto; padding: 16px;
  display: flex; flex-direction: column; gap: 10px;
  background: #f8f9fb;
}}
.chat-messages::-webkit-scrollbar {{ width: 5px; }}
.chat-messages::-webkit-scrollbar-thumb {{ background: #d0d5dd; border-radius: 3px; }}

.chat-bubble {{
  max-width: 85%; padding: 10px 14px; border-radius: 14px;
  font-size: 13.5px; line-height: 1.55; word-break: break-word;
  animation: fadeIn 0.25s;
}}
@keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: translateY(0); }} }}
.chat-bubble.user {{
  align-self: flex-end; background: #1a1a2e; color: white;
  border-bottom-right-radius: 4px;
}}
.chat-bubble.assistant {{
  align-self: flex-start; background: white; color: #2c3e50;
  border-bottom-left-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}}
.chat-bubble.thinking {{
  align-self: flex-start; background: #fff8e1; color: #b7950b;
  font-size: 12px; font-style: italic; padding: 6px 12px; border-radius: 10px;
}}
.chat-bubble.system {{
  align-self: center; background: #ecf0f1; color: #7f8c8d;
  font-size: 11px; padding: 5px 12px; border-radius: 10px;
}}
.chat-bubble pre {{ background: #2c3e50; color: #ecf0f1; padding: 8px 12px; border-radius: 6px; overflow-x: auto; font-size: 12px; margin: 6px 0; }}
.chat-bubble code {{ background: #f0f0f0; padding: 1px 5px; border-radius: 3px; font-size: 12px; }}
.chat-bubble.assistant code {{ background: #e8e8e8; }}

.chat-input-area {{
  display: flex; padding: 10px 14px; gap: 8px; border-top: 1px solid #eee;
  background: white;
}}
.chat-input-area input {{
  flex: 1; border: 1px solid #ddd; border-radius: 20px;
  padding: 10px 16px; font-size: 14px; outline: none;
  font-family: inherit; transition: border-color 0.2s;
}}
.chat-input-area input:focus {{ border-color: #1a1a2e; }}
.chat-input-area button {{
  width: 40px; height: 40px; border-radius: 50%; border: none;
  background: #1a1a2e; color: white; font-size: 18px; cursor: pointer;
  transition: background 0.2s; flex-shrink: 0;
}}
.chat-input-area button:hover {{ background: #2c3e50; }}
.chat-input-area button:disabled {{ background: #bdc3c7; cursor: not-allowed; }}

.chat-panel-footer {{
  text-align: center; padding: 6px; font-size: 11px; color: #bdc3c7;
  background: #f8f9fb; border-top: 1px solid #f0f0f0;
}}

@media (max-width: 480px) {{
  .chat-panel {{ width: calc(100vw - 32px); right: 16px; bottom: 80px; height: 450px; }}
}}
</style>
</head>
<body>
<div class="container">

<div class="header">
  <h1>二板涨停 N 型战法 — 选股报告</h1>
  <div class="date">选股日期: {screen_date}</div>
</div>

<div class="summary">
  <div class="summary-card total">
    <div class="num">{len(results)}</div>
    <div class="label">总分析</div>
  </div>
  <div class="summary-card pass">
    <div class="num">{len(passed_two) + len(relaxed_two)}</div>
    <div class="label">2板入选</div>
  </div>
  <div class="summary-card fail">
    <div class="num">{len(excluded_two)}</div>
    <div class="label">2板未达标</div>
  </div>
  <div class="summary-card pass">
    <div class="num">{len(multi_passed) + len(relaxed_multi)}</div>
    <div class="label">多板入选</div>
  </div>
  <div class="summary-card multi">
    <div class="num">{len(multi_excluded)}</div>
    <div class="label">多板未达标</div>
  </div>
</div>

<div class="tabs-wrapper">
  <div class="tabs">
  <button class="tab-btn doji" onclick="switchTab('doji')">十字星 (<span id="dojiTabCount">0</span>)</button>
  <button class="tab-btn hold" onclick="switchTab('hold-second')">二板后第2天不破 (<span id="holdSecondTabCount">0</span>)</button>
  <button class="tab-btn pass active" onclick="switchTab('passed')">2板入选 ({len(passed_two) + len(relaxed_two)})</button>
  <button class="tab-btn pass" onclick="switchTab('multi-passed')">多板入选 ({len(multi_passed) + len(relaxed_multi)})</button>
  <button class="tab-btn fail" onclick="switchTab('excluded')">2板未达标 ({len(excluded_two)})</button>
  <button class="tab-btn multi" onclick="switchTab('multi-excluded')">多板未达标 ({len(multi_excluded)})</button>
  </div>
  <div class="search-box">
    <span class="search-icon">&#128269;</span>
    <input type="text" class="search-input" placeholder="搜索股票名/代码..." autocomplete="off"
           oninput="searchStock(this.value)" onfocus="searchStock(this.value)" />
    <button class="search-clear" onclick="clearSearch()">&times;</button>
    <div class="search-dropdown" id="searchDropdown"></div>
  </div>
</div>

<div id="tab-passed" class="tab-content active">
{passed_two_html}
{relaxed_two_html}
</div>

<div id="tab-excluded" class="tab-content">
{excluded_two_html if excluded_two_html else '<div style="padding:20px;text-align:center;color:#bdc3c7;">无2板未达标标的</div>'}
</div>

<div id="tab-multi-passed" class="tab-content">
{multi_passed_html}
{relaxed_multi_html}
</div>

<div id="tab-multi-excluded" class="tab-content">
{multi_excluded_html if multi_excluded_html else '<div style="padding:20px;text-align:center;color:#bdc3c7;">无多板未达标标的</div>'}
</div>

<div id="tab-hold-second" class="tab-content">
  <div class="hold-tab-toolbar">
    <div class="hold-tab-title">共 <b id="holdSecondPanelCount">0</b> 只</div>
    <div class="hold-tab-note">二板后第二天收盘价 >= 第二个板收盘价</div>
  </div>
  <div id="holdSecondTabList" class="hold-tab-list"></div>
</div>

<div id="tab-doji" class="tab-content">
  <div class="doji-tab-toolbar">
    <div class="doji-tab-title">共 <b id="dojiPanelCount">0</b> 只</div>
    <div class="doji-source-chips">
      <span class="doji-source-chip two-pass">2板入选</span>
      <span class="doji-source-chip two-relaxed">2板放宽</span>
      <span class="doji-source-chip three-pass">三板入选</span>
      <span class="doji-source-chip three-relaxed">三板放宽</span>
    </div>
  </div>
  <div id="dojiTabList" class="doji-tab-list"></div>
</div>

<div class="footer">
  免责声明：本报告仅供参考，不构成投资建议<br>
  Generated by quant screener · {screen_date}
</div>

</div>

<!-- ═══════════════════════════════════════════════════════ -->
<!--  Chat Widget -->
<!-- ═══════════════════════════════════════════════════════ -->
<button class="chat-toggle" id="chatToggle" title="Claude AI 助手">
  💬
  <span class="badge" id="chatStatusDot"></span>
</button>

<div class="chat-panel" id="chatPanel">
  <div class="chat-panel-header">
    <span><span class="status-dot" id="chatStatusDot2"></span> Claude 助手</span>
    <button class="close-btn" onclick="toggleChat()">✕</button>
  </div>
  <div class="chat-messages" id="chatMessages">
    <div class="chat-bubble system">你好！我是 Claude，可以回答关于这份选股报告的任何问题。比如：选股逻辑、技术指标、个股分析等。</div>
  </div>
  <div class="chat-panel-footer">
    <span>基于 Claude · quant 项目上下文</span>
  </div>
  <div class="chat-input-area">
    <input id="chatInput" type="text" placeholder="输入问题... 比如: 分析一下诺德股份"
           onkeydown="if(event.key==='Enter')sendMessage()" />
    <button id="chatSendBtn" onclick="sendMessage()">➤</button>
  </div>
</div>

<script>
const ALL_DATA = {json_data};
window._charts = {{}};

function switchTab(tab) {{
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    const tabMap = {{
        'doji': {{ btn: 1, content: 'tab-doji' }},
        'hold-second': {{ btn: 2, content: 'tab-hold-second' }},
        'passed': {{ btn: 3, content: 'tab-passed' }},
        'multi-passed': {{ btn: 4, content: 'tab-multi-passed' }},
        'excluded': {{ btn: 5, content: 'tab-excluded' }},
        'multi-excluded': {{ btn: 6, content: 'tab-multi-excluded' }}
    }};
    const target = tabMap[tab];
    if (target) {{
        document.querySelector('.tabs .tab-btn:nth-child(' + target.btn + ')').classList.add('active');
        document.getElementById(target.content).classList.add('active');
        setTimeout(resizeVisibleCharts, 60);
    }}
}}

function toggleCard(header) {{
    const body = header.nextElementSibling;
    const isOpen = body.classList.contains('open');
    if (isOpen) {{
        body.classList.remove('open');
        header.classList.remove('expanded');
    }} else {{
        body.classList.add('open');
        header.classList.add('expanded');
        const chartDiv = body.querySelector('.chart-container');
        if (chartDiv && chartDiv.id) {{
            initChart(chartDiv.id);
            setTimeout(resizeVisibleCharts, 60);
        }}
    }}
}}

function toggleGroup(header) {{
    const body = header.nextElementSibling;
    const isOpen = body.classList.contains('open');
    if (isOpen) {{
        body.classList.remove('open');
        header.classList.remove('expanded');
    }} else {{
        body.classList.add('open');
        header.classList.add('expanded');
    }}
}}

function initChart(containerId) {{
    if (window._charts[containerId]) {{
        window._charts[containerId].resize();
        return;
    }}
    // containerId format: "chart_p_CODE" / "chart_b_CODE" / "chart_e_CODE" / "chart_mp_CODE" / "chart_mb_CODE" / "chart_me_CODE"
    let symbol;
    if (containerId.startsWith('chart_doji_')) {{
        symbol = containerId.replace('chart_doji_', '').split('_')[0];
    }} else if (containerId.startsWith('chart_hold_')) {{
        symbol = containerId.replace('chart_hold_', '').split('_')[0];
    }} else {{
        symbol = containerId.replace('chart_p_', '').replace('chart_b_', '').replace('chart_e_', '').replace('chart_mp_', '').replace('chart_mb_', '').replace('chart_me_', '').replace('chart_r_', '').replace('chart_mr_', '');
    }}
    const data = ALL_DATA[symbol];
    if (!data) return;

    const dom = document.getElementById(containerId);
    if (!dom) return;
    const chart = echarts.init(dom);
    chart.setOption(buildOption(data));
    window._charts[containerId] = chart;
}}

function resizeVisibleCharts() {{
    Object.values(window._charts).forEach(function(c) {{
        if (!c || !c.getDom) return;
        const dom = c.getDom();
        if (dom && dom.offsetParent !== null) {{
            c.resize();
        }}
    }});
}}

function buildOption(data) {{
    const upColor = '#ef5350';
    const downColor = '#26a69a';

    // 标记区域
    let markAreaData = [];
    if (data.lu_start_idx != null && data.lu_end_idx != null) {{
        markAreaData = [[
            {{ xAxis: data.dates[data.lu_start_idx] }},
            {{ xAxis: data.dates[data.lu_end_idx] }}
        ]];
    }}

    // 标记线
    let markLines = [];
    if (data.fib_618 > 0) {{
        markLines.push({{
            yAxis: data.fib_618,
            name: 'Fib 0.618',
            lineStyle: {{ color: '#e74c3c', type: 'dashed', width: 1.5 }},
            label: {{ formatter: 'Fib 0.618\\n{{c}}', fontSize: 11 }}
        }});
    }}
    if (data.buy_price > 0) {{
        markLines.push({{
            yAxis: data.buy_price,
            name: '买入',
            lineStyle: {{ color: '#27ae60', width: 1.5 }},
            label: {{ formatter: '买入 ¥{{c}}', fontSize: 11 }}
        }});
    }}
    if (data.protect_price > 0) {{
        markLines.push({{
            yAxis: data.protect_price,
            name: '保护',
            lineStyle: {{ color: '#e67e22', type: 'dotted', width: 1.5 }},
            label: {{ formatter: '保护 ¥{{c}}', fontSize: 11 }}
        }});
    }}

    return {{
        title: {{
            text: data.symbol + ' ' + data.name,
            left: 'center',
            top: 4,
            textStyle: {{ fontSize: 15, fontWeight: 'bold' }}
        }},
        tooltip: {{
            trigger: 'axis',
            axisPointer: {{ type: 'cross' }},
            formatter: function(params) {{
                let html = '<b>' + params[0].axisValue + '</b><br/>';
                params.forEach(function(p) {{
                    if (p.seriesType === 'candlestick') {{
                        const vals = p.data;
                        if (vals && vals.length >= 4) {{
                            html += '开: ' + vals[0] + '<br/>';
                            html += '收: ' + vals[1] + '<br/>';
                            html += '低: ' + vals[2] + '<br/>';
                            html += '高: ' + vals[3] + '<br/>';
                        }}
                    }} else if (p.seriesName === 'MA60' || p.seriesName === 'MA120') {{
                        if (p.value != null) {{
                            html += p.marker + p.seriesName + ': ' + p.value.toFixed(2) + '<br/>';
                        }}
                    }} else if (p.seriesName === '成交量') {{
                        if (p.value != null) {{
                            html += p.marker + p.seriesName + ': ' + (p.value / 10000).toFixed(0) + '万手<br/>';
                        }}
                    }}
                }});
                return html;
            }}
        }},
        legend: {{
            data: ['K线', 'MA60', 'MA120', '成交量'],
            top: 32,
            left: 'center',
            textStyle: {{ fontSize: 12 }}
        }},
        grid: [
            {{ left: '10%', right: '8%', top: 70, height: '55%' }},
            {{ left: '10%', right: '8%', top: '75%', height: '15%' }}
        ],
        xAxis: [
            {{
                type: 'category',
                data: data.dates,
                gridIndex: 0,
                axisLine: {{ onZero: false }},
                axisLabel: {{ rotate: 30, fontSize: 10 }}
            }},
            {{
                type: 'category',
                data: data.dates,
                gridIndex: 1,
                axisLabel: {{ show: false }},
                axisLine: {{ show: false }},
                axisTick: {{ show: false }}
            }}
        ],
        yAxis: [
            {{
                type: 'value',
                scale: true,
                gridIndex: 0,
                splitNumber: 5,
                axisLabel: {{ formatter: '{{value}}' }}
            }},
            {{
                type: 'value',
                gridIndex: 1,
                axisLabel: {{ formatter: function(v) {{ return (v / 10000).toFixed(0) + '万'; }} }}
            }}
        ],
        dataZoom: [
            {{ type: 'slider', xAxisIndex: [0, 1], bottom: 10, height: 20, start: 50, end: 100 }}
        ],
        series: [
            {{
                type: 'candlestick',
                name: 'K线',
                data: data.ohlc,
                itemStyle: {{
                    color: upColor,
                    color0: downColor,
                    borderColor: upColor,
                    borderColor0: downColor
                }},
                xAxisIndex: 0,
                yAxisIndex: 0,
                markArea: {{
                    silent: true,
                    data: markAreaData,
                    itemStyle: {{ color: 'rgba(255, 215, 0, 0.15)' }},
                    label: {{ show: true, position: 'insideTop', formatter: '连板区', fontSize: 11 }}
                }},
                markLine: {{
                    silent: true,
                    symbol: 'none',
                    data: markLines
                }}
            }},
            {{
                type: 'line',
                name: 'MA60',
                data: data.ma60,
                smooth: true,
                lineStyle: {{ color: '#f39c12', width: 1.2 }},
                symbol: 'none',
                xAxisIndex: 0,
                yAxisIndex: 0
            }},
            {{
                type: 'line',
                name: 'MA120',
                data: data.ma120,
                smooth: true,
                lineStyle: {{ color: '#3498db', width: 1.2 }},
                symbol: 'none',
                xAxisIndex: 0,
                yAxisIndex: 0
            }},
            {{
                type: 'bar',
                name: '成交量',
                data: data.volumes,
                xAxisIndex: 1,
                yAxisIndex: 1,
                itemStyle: {{
                    color: function(params) {{
                        const ohlc = data.ohlc[params.dataIndex];
                        if (!ohlc || ohlc.length < 2) return downColor;
                        return ohlc[1] >= ohlc[0] ? upColor : downColor;
                    }}
                }}
            }}
        ]
    }};
}}

// resize 时刷新所有图表
window.addEventListener('resize', resizeVisibleCharts);

// ── 十字星汇总 Tab ───────────────────────────────────
function getCloseAt(data, index) {{
    if (!data || !data.ohlc || index == null || index < 0 || index >= data.ohlc.length) return null;
    const row = data.ohlc[index];
    if (!row || row.length < 2) return null;
    const close = Number(row[1]);
    return Number.isFinite(close) ? close : null;
}}

function buildHoldSecondTab() {{
    const list = document.getElementById('holdSecondTabList');
    if (!list) return;

    const sources = [
        {{ selector: '#tab-passed > .stock-card.passed', label: '2板入选' }},
        {{ selector: '#tab-passed .stock-card.relaxed', label: '2板放宽' }},
        {{ selector: '#tab-multi-passed > .stock-card.multi', label: '多板入选' }},
        {{ selector: '#tab-multi-passed .stock-card.multi-relaxed', label: '多板放宽' }}
    ];

    const items = [];
    const seen = new Set();
    sources.forEach(function(source) {{
        document.querySelectorAll(source.selector).forEach(function(card) {{
            const symbol = card.getAttribute('data-symbol') || '';
            const chartId = card.getAttribute('data-chart') || '';
            const data = ALL_DATA[symbol];
            if (!data || data.lu_end_idx == null) return;

            const boardIdx = Number(data.lu_end_idx);
            const checkIdx = boardIdx + 2;
            const boardClose = getCloseAt(data, boardIdx);
            const checkClose = getCloseAt(data, checkIdx);
            if (boardClose == null || checkClose == null || checkClose < boardClose) return;

            const key = source.label + ':' + symbol + ':' + chartId;
            if (seen.has(key)) return;
            seen.add(key);

            items.push({{
                card: card,
                source: source,
                symbol: symbol,
                chartId: chartId,
                boardClose: boardClose,
                checkClose: checkClose,
                checkDate: data.dates && data.dates[checkIdx] ? data.dates[checkIdx] : ''
            }});
        }});
    }});

    list.innerHTML = '';
    items.forEach(function(item, index) {{
        const sourceCard = item.card;
        const sourceLeft = sourceCard.querySelector('.card-left');
        const symbol = item.symbol;
        const nameElFromSource = sourceLeft ? sourceLeft.querySelector('.name') : null;
        const name = nameElFromSource ? nameElFromSource.textContent.trim() : '';
        const pct = ((item.checkClose / item.boardClose - 1) * 100).toFixed(2);
        const pctText = (pct >= 0 ? '+' : '') + pct + '%';

        const card = document.createElement('div');
        card.className = 'hold-list-card';

        const header = document.createElement('div');
        header.className = 'card-header';
        header.onclick = function() {{ toggleCard(header); }};

        const left = document.createElement('div');
        left.className = 'card-left';

        const rank = document.createElement('span');
        rank.className = 'rank';
        rank.textContent = '#' + (index + 1);
        left.appendChild(rank);

        const symbolEl = document.createElement('span');
        symbolEl.className = 'symbol';
        symbolEl.textContent = symbol;
        left.appendChild(symbolEl);

        const nameEl = document.createElement('span');
        nameEl.className = 'name';
        nameEl.textContent = name;
        left.appendChild(nameEl);

        if (sourceLeft) {{
            ['score-badge', 'board-badge'].forEach(function(cls) {{
                const badge = sourceLeft.querySelector('.' + cls);
                if (badge) left.appendChild(badge.cloneNode(true));
            }});
        }}

        const meta = document.createElement('div');
        meta.className = 'card-meta';
        meta.insertAdjacentHTML('beforeend',
            '<span class="hold-metric">二板收: <b>¥' + item.boardClose.toFixed(2) + '</b></span>' +
            '<span class="hold-metric">第2天收: <b>¥' + item.checkClose.toFixed(2) + '</b></span>' +
            '<span class="hold-metric">幅度: <b>' + pctText + '</b></span>'
        );

        const sourceBadge = document.createElement('span');
        sourceBadge.className = 'hold-source-badge';
        sourceBadge.textContent = item.source.label;

        const holdBadge = document.createElement('span');
        holdBadge.className = 'hold-badge';
        holdBadge.textContent = '第2天不破';

        header.appendChild(left);
        header.appendChild(meta);
        header.appendChild(sourceBadge);
        header.appendChild(holdBadge);
        const expand = document.createElement('span');
        expand.className = 'expand-icon';
        expand.textContent = '▸';
        header.appendChild(expand);

        const body = document.createElement('div');
        body.className = 'card-body';

        const chart = document.createElement('div');
        chart.id = 'chart_hold_' + symbol + '_' + item.chartId;
        chart.className = 'chart-container';
        body.appendChild(chart);

        card.appendChild(header);
        card.appendChild(body);
        list.appendChild(card);
    }});

    if (items.length === 0) {{
        list.innerHTML = '<div class="hold-empty">暂无数据</div>';
    }}

    const tabCount = document.getElementById('holdSecondTabCount');
    const panelCount = document.getElementById('holdSecondPanelCount');
    if (tabCount) tabCount.textContent = items.length;
    if (panelCount) panelCount.textContent = items.length;
}}

function buildDojiTab() {{
    const list = document.getElementById('dojiTabList');
    if (!list) return;

    const sources = [
        {{ selector: '#tab-passed > .stock-card.passed', tabId: 'tab-passed', label: '2板入选', accent: 'two-pass' }},
        {{ selector: '#tab-passed .stock-card.relaxed', tabId: 'tab-passed', label: '2板放宽', accent: 'two-relaxed' }},
        {{ selector: '#tab-multi-passed > .stock-card.multi', tabId: 'tab-multi-passed', label: '三板入选', accent: 'three-pass' }},
        {{ selector: '#tab-multi-passed .stock-card.multi-relaxed', tabId: 'tab-multi-passed', label: '三板放宽', accent: 'three-relaxed' }}
    ];

    const items = [];
    const seen = new Set();
    sources.forEach(function(source) {{
        document.querySelectorAll(source.selector).forEach(function(card) {{
            const dojiTag = card.querySelector('.doji-tag');
            if (!dojiTag) return;

            const symbol = card.getAttribute('data-symbol') || '';
            const chartId = card.getAttribute('data-chart') || '';
            const key = source.tabId + ':' + symbol + ':' + chartId;
            if (seen.has(key)) return;
            seen.add(key);

            items.push({{ card: card, source: source, symbol: symbol, chartId: chartId, dojiTag: dojiTag }});
        }});
    }});

    list.innerHTML = '';
    items.forEach(function(item, index) {{
        const sourceCard = item.card;
        const sourceLeft = sourceCard.querySelector('.card-left');
        const sourceMeta = sourceCard.querySelector('.card-meta');
        const symbol = item.symbol;
        const nameElFromSource = sourceLeft ? sourceLeft.querySelector('.name') : null;
        const name = nameElFromSource ? nameElFromSource.textContent.trim() : '';

        const card = document.createElement('div');
        card.className = 'doji-list-card ' + item.source.accent;

        const header = document.createElement('div');
        header.className = 'card-header';
        header.onclick = function() {{ toggleCard(header); }};

        const left = document.createElement('div');
        left.className = 'card-left';

        const rank = document.createElement('span');
        rank.className = 'rank';
        rank.textContent = '#' + (index + 1);
        left.appendChild(rank);

        const symbolEl = document.createElement('span');
        symbolEl.className = 'symbol';
        symbolEl.textContent = symbol;
        left.appendChild(symbolEl);

        const nameEl = document.createElement('span');
        nameEl.className = 'name';
        nameEl.textContent = name;
        left.appendChild(nameEl);

        if (sourceLeft) {{
            ['score-badge', 'board-badge'].forEach(function(cls) {{
                const badge = sourceLeft.querySelector('.' + cls);
                if (badge) left.appendChild(badge.cloneNode(true));
            }});
        }}

        const meta = document.createElement('div');
        meta.className = 'card-meta';
        if (sourceMeta) meta.innerHTML = sourceMeta.innerHTML;

        const sourceBadge = document.createElement('span');
        sourceBadge.className = 'doji-source-badge ' + item.source.accent;
        sourceBadge.textContent = item.source.label;

        header.appendChild(left);
        header.appendChild(meta);
        header.appendChild(sourceBadge);
        header.appendChild(item.dojiTag.cloneNode(true));
        const expand = document.createElement('span');
        expand.className = 'expand-icon';
        expand.textContent = '▸';
        header.appendChild(expand);

        const body = document.createElement('div');
        body.className = 'card-body';

        const chart = document.createElement('div');
        const dojiChartId = 'chart_doji_' + symbol + '_' + item.chartId;
        chart.id = dojiChartId;
        chart.className = 'chart-container';
        body.appendChild(chart);

        card.appendChild(header);
        card.appendChild(body);
        list.appendChild(card);
    }});

    if (items.length === 0) {{
        list.innerHTML = '<div class="doji-empty">暂无数据</div>';
    }}

    const tabCount = document.getElementById('dojiTabCount');
    const panelCount = document.getElementById('dojiPanelCount');
    if (tabCount) tabCount.textContent = items.length;
    if (panelCount) panelCount.textContent = items.length;
}}

buildHoldSecondTab();
buildDojiTab();

// ── 搜索功能 ─────────────────────────────────────────
const _stockIndex = {{}};
(function buildIndex() {{
    const cards = document.querySelectorAll('.stock-card');
    const tabNames = {{
        'tab-passed': '2板入选', 'tab-excluded': '2板未达标',
        'tab-multi-passed': '多板入选', 'tab-multi-excluded': '多板未达标'
    }};
    const tabClasses = {{
        'tab-passed': 'pass', 'tab-excluded': 'fail',
        'tab-multi-passed': 'multi', 'tab-multi-excluded': 'me'
    }};
    cards.forEach(function(card) {{
        const symbol = card.getAttribute('data-symbol');
        const nameEl = card.querySelector('.name');
        const name = nameEl ? nameEl.textContent.trim() : '';
        const tabContent = card.closest('.tab-content');
        const tabId = tabContent ? tabContent.id : '';
        _stockIndex[symbol] = {{
            symbol: symbol,
            name: name,
            tabId: tabId,
            tabName: tabNames[tabId] || tabId,
            tabClass: tabClasses[tabId] || '',
            card: card
        }};
    }});
}})();

function searchStock(query) {{
    const dropdown = document.getElementById('searchDropdown');
    const clearBtn = document.querySelector('.search-clear');
    const q = query.trim().toLowerCase();

    if (!q) {{
        dropdown.classList.remove('open');
        dropdown.innerHTML = '';
        if (clearBtn) clearBtn.classList.remove('visible');
        return;
    }}

    if (clearBtn) clearBtn.classList.add('visible');

    const results = [];
    Object.values(_stockIndex).forEach(function(item) {{
        if (item.symbol.toLowerCase().indexOf(q) !== -1 ||
            item.name.toLowerCase().indexOf(q) !== -1) {{
            results.push(item);
        }}
    }});

    // 匹配度排序：完全匹配优先，前缀匹配次之
    results.sort(function(a, b) {{
        const aCode = a.symbol.toLowerCase();
        const bCode = b.symbol.toLowerCase();
        const aName = a.name.toLowerCase();
        const bName = b.name.toLowerCase();
        const aExact = (aCode === q || aName === q) ? 0 : 1;
        const bExact = (bCode === q || bName === q) ? 0 : 1;
        if (aExact !== bExact) return aExact - bExact;
        const aPrefix = (aCode.startsWith(q) || aName.startsWith(q)) ? 0 : 1;
        const bPrefix = (bCode.startsWith(q) || bName.startsWith(q)) ? 0 : 1;
        return aPrefix - bPrefix;
    }});

    if (results.length === 0) {{
        dropdown.innerHTML = '<div class="search-no-result">无匹配结果</div>';
    }} else {{
        dropdown.innerHTML = results.map(function(r, i) {{
            return '<div class="search-item" data-symbol="' + r.symbol + '" data-tab="' + r.tabId +
                   '" onclick="locateStock(\\'' + r.symbol + '\\', \\'' + r.tabId + '\\')">' +
                   '<span class="s-symbol">' + r.symbol + '</span>' +
                   '<span class="s-name">' + r.name + '</span>' +
                   '<span class="s-tab ' + r.tabClass + '">' + r.tabName + '</span>' +
                   '</div>';
        }}).join('');
    }}
    dropdown.classList.add('open');
}}

function locateStock(symbol, tabId) {{
    // 关闭搜索下拉
    const dropdown = document.getElementById('searchDropdown');
    dropdown.classList.remove('open');
    const input = document.querySelector('.search-input');
    if (input) input.blur();

    // 切换到对应 tab
    switchTab(tabId.replace('tab-', ''));

    // 展开对应的 stock card 并滚动到视图
    const item = _stockIndex[symbol];
    if (!item || !item.card) return;

    // 如果卡片在分组内，先展开分组
    const groupBody = item.card.closest('.group-body');
    if (groupBody) {{
        groupBody.classList.add('open');
        const groupHeader = groupBody.previousElementSibling;
        if (groupHeader) groupHeader.classList.add('expanded');
    }}

    // 展开卡片
    const header = item.card.querySelector('.card-header');
    const body = item.card.querySelector('.card-body');
    if (header && body && !body.classList.contains('open')) {{
        body.classList.add('open');
        header.classList.add('expanded');
        const chartDiv = body.querySelector('.chart-container');
        if (chartDiv && chartDiv.id) {{
            initChart(chartDiv.id);
            setTimeout(resizeVisibleCharts, 60);
        }}
    }}

    // 滚动到视图并高亮
    item.card.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
    item.card.classList.add('highlight');
    setTimeout(function() {{ item.card.classList.remove('highlight'); }}, 1600);
}}

function clearSearch() {{
    const input = document.querySelector('.search-input');
    if (input) input.value = '';
    const dropdown = document.getElementById('searchDropdown');
    dropdown.classList.remove('open');
    dropdown.innerHTML = '';
    const clearBtn = document.querySelector('.search-clear');
    if (clearBtn) clearBtn.classList.remove('visible');
    if (input) input.focus();
}}

// 点击页面其他地方关闭搜索下拉
document.addEventListener('click', function(e) {{
    const box = document.querySelector('.search-box');
    const dropdown = document.getElementById('searchDropdown');
    if (box && dropdown && !box.contains(e.target)) {{
        dropdown.classList.remove('open');
    }}
}});
</script>

<script>
// ═══════════════════════════════════════════════════════
//  Chat WebSocket Client
// ═══════════════════════════════════════════════════════
(function() {{
    const WS_HOST = window.location.hostname;
    const WS_PORT = window.location.port || '80';
    const WS_URL = 'ws://' + WS_HOST + ':' + WS_PORT + '/ws';

    let ws = null;
    let connected = false;
    let currentAssistantBubble = null;
    let pendingText = '';

    const toggleBtn = document.getElementById('chatToggle');
    const panel = document.getElementById('chatPanel');
    const messagesEl = document.getElementById('chatMessages');
    const inputEl = document.getElementById('chatInput');
    const sendBtn = document.getElementById('chatSendBtn');
    const dot1 = document.getElementById('chatStatusDot');
    const dot2 = document.getElementById('chatStatusDot2');

    function setStatus(state) {{
        // state: 'offline' | 'connecting' | 'online'
        dot1.className = 'badge' + (state === 'online' ? ' online' : '');
        dot2.className = 'status-dot' + (state === 'online' ? ' online' : '');
        if (state === 'connecting') {{
            dot1.className = 'badge';
        }}
    }}

    function addBubble(text, cls) {{
        const div = document.createElement('div');
        div.className = 'chat-bubble ' + cls;
        div.textContent = text;
        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        return div;
    }}

    function addHtmlBubble(html, cls) {{
        const div = document.createElement('div');
        div.className = 'chat-bubble ' + cls;
        div.innerHTML = html;
        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        return div;
    }}

    function simpleMarkdown(text) {{
        // Convert basic markdown to HTML
        let html = text
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/```(\\w*)\\n([\\s\\S]*?)```/g, '<pre>$2</pre>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\\*\\*(.+?)\\*\\*/g, '<b>$1</b>')
            .replace(/\\*(.+?)\\*/g, '<i>$1</i>')
            .replace(/\\n/g, '<br>');
        return html;
    }}

    function connect() {{
        if (ws && ws.readyState === WebSocket.OPEN) return;
        setStatus('connecting');
        try {{
            ws = new WebSocket(WS_URL);
        }} catch(e) {{
            setStatus('offline');
            return;
        }}

        ws.onopen = function() {{
            connected = true;
            setStatus('online');
            console.log('[chat] connected');
        }};

        ws.onmessage = function(event) {{
            try {{
                const data = JSON.parse(event.data);
                if (data.type === 'text') {{
                    if (!currentAssistantBubble) {{
                        currentAssistantBubble = addHtmlBubble('', 'assistant');
                    }}
                    pendingText += data.text;
                    currentAssistantBubble.innerHTML = simpleMarkdown(pendingText);
                    messagesEl.scrollTop = messagesEl.scrollHeight;
                }} else if (data.type === 'thinking') {{
                    addBubble(data.text, 'thinking');
                }} else if (data.type === 'done') {{
                    currentAssistantBubble = null;
                    pendingText = '';
                    sendBtn.disabled = false;
                    inputEl.disabled = false;
                    inputEl.focus();
                    if (data.is_error) {{
                        addBubble('(Claude 返回错误)', 'system');
                    }}
                }} else if (data.type === 'error') {{
                    addBubble('Error: ' + data.text, 'system');
                    sendBtn.disabled = false;
                    inputEl.disabled = false;
                }}
            }} catch(e) {{}}
        }};

        ws.onclose = function() {{
            connected = false;
            setStatus('offline');
            currentAssistantBubble = null;
            pendingText = '';
            sendBtn.disabled = false;
            inputEl.disabled = false;
        }};

        ws.onerror = function() {{
            connected = false;
            setStatus('offline');
        }};
    }}

    window.sendMessage = function() {{
        const text = inputEl.value.trim();
        if (!text) return;

        if (!connected || !ws || ws.readyState !== WebSocket.OPEN) {{
            addBubble('正在连接 Claude...', 'system');
            connect();
            // Queue the message - try again shortly
            setTimeout(function() {{
                if (connected && ws && ws.readyState === WebSocket.OPEN) {{
                    _doSend(text);
                }} else {{
                    addBubble('无法连接到 Claude 服务。请确保 chat_server.py 正在运行 (端口 ' + WS_PORT + '):<br><code>python3.8 chat_server.py</code>', 'system');
                    setStatus('offline');
                }}
            }}, 1500);
            return;
        }}

        _doSend(text);
    }};

    function _doSend(text) {{
        addBubble(text, 'user');
        inputEl.value = '';
        sendBtn.disabled = true;
        inputEl.disabled = true;
        ws.send(JSON.stringify({{ text: text }}));
    }}

    window.toggleChat = function() {{
        const open = panel.classList.contains('open');
        if (open) {{
            panel.classList.remove('open');
        }} else {{
            panel.classList.add('open');
            inputEl.focus();
            if (!connected) {{
                connect();
            }}
        }}
    }};

    // Toggle button click
    toggleBtn.addEventListener('click', window.toggleChat);

    // Auto-connect after page load (lazy, on first toggle or send)
}})();
</script>
</body>
</html>'''


# 兼容 run_analysis_mode 的单股导出
def export_single_html(code: str, df: pd.DataFrame, analysis: dict,
                       export_dir: str = "") -> str:
    """单股分析 HTML 导出"""
    if not export_dir:
        export_dir = os.path.join(os.getcwd(), "data", "export")
    os.makedirs(export_dir, exist_ok=True)
    cd = _extract_chart_data(df, analysis)
    if cd is None:
        raise ValueError("无法提取图表数据")

    json_data = json.dumps({code: cd}, ensure_ascii=False)

    # 单股 HTML（复用 buildOption）
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{code} 分析</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background: #f5f6fa; color: #2c3e50; }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
.header {{ background: linear-gradient(135deg, #1a1a2e, #16213e); color: white; padding: 20px 28px; border-radius: 12px; margin-bottom: 16px; }}
.header h1 {{ font-size: 20px; }}
.chart-container {{ width: 100%; height: 600px; background: white; border-radius: 8px; padding: 8px; }}
.info-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; margin-top: 16px; }}
.info-item {{ background: white; border-radius: 8px; padding: 12px 16px; }}
.info-item .label {{ font-size: 12px; color: #7f8c8d; }}
.info-item .value {{ font-size: 16px; font-weight: 700; margin-top: 2px; }}
</style>
</head>
<body>
<div class="container">
<div class="header"><h1>{code} {cd["name"]} — 单股分析</h1></div>
<div class="chart-container" id="main-chart"></div>
<div class="info-grid">
  <div class="info-item"><div class="label">阶段</div><div class="value">{cd["uptrend_stage"]}</div></div>
  <div class="info-item"><div class="label">评分</div><div class="value">{cd["score"]}</div></div>
  <div class="info-item"><div class="label">调整天数</div><div class="value">{cd["adj_days"]}天</div></div>
  <div class="info-item"><div class="label">量比</div><div class="value">{cd["adj_vol_ratio"]}</div></div>
  <div class="info-item"><div class="label">阳线占比</div><div class="value">{cd["adj_yang_ratio"]}</div></div>
  <div class="info-item"><div class="label">买入价</div><div class="value">¥{cd["buy_price"]}</div></div>
  <div class="info-item"><div class="label">保护位</div><div class="value">¥{cd["protect_price"]}</div></div>
  <div class="info-item"><div class="label">Fib 0.618</div><div class="value">{cd["fib_618"]}</div></div>
</div>
</div>
<script>
const STOCK_DATA = {json_data};
(function() {{
    const data = STOCK_DATA['{code}'];
    if (!data) return;
    const upColor = '#ef5350', downColor = '#26a69a';
    let markAreaData = [];
    if (data.lu_start_idx != null && data.lu_end_idx != null) {{
        markAreaData = [[
            {{ xAxis: data.dates[data.lu_start_idx] }},
            {{ xAxis: data.dates[data.lu_end_idx] }}
        ]];
    }}
    let markLines = [];
    if (data.fib_618 > 0) markLines.push({{ yAxis: data.fib_618, name: 'Fib 0.618', lineStyle: {{ color: '#e74c3c', type: 'dashed', width: 1.5 }}, label: {{ formatter: 'Fib 0.618\\n{{c}}', fontSize: 11 }} }});
    if (data.buy_price > 0) markLines.push({{ yAxis: data.buy_price, name: '买入', lineStyle: {{ color: '#27ae60', width: 1.5 }}, label: {{ formatter: '买入 ¥{{c}}', fontSize: 11 }} }});
    if (data.protect_price > 0) markLines.push({{ yAxis: data.protect_price, name: '保护', lineStyle: {{ color: '#e67e22', type: 'dotted', width: 1.5 }}, label: {{ formatter: '保护 ¥{{c}}', fontSize: 11 }} }});
    const chart = echarts.init(document.getElementById('main-chart'));
    chart.setOption({{
        title: {{ text: '{code} ' + data.name, left: 'center', top: 4, textStyle: {{ fontSize: 15, fontWeight: 'bold' }} }},
        tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }}, formatter: function(params) {{ let h = '<b>' + params[0].axisValue + '</b><br/>'; params.forEach(function(p) {{ if (p.seriesType === 'candlestick' && p.data && p.data.length>=4) {{ h += '开: ' + p.data[0].toFixed(2) + '<br/>收: ' + p.data[1].toFixed(2) + '<br/>低: ' + p.data[2].toFixed(2) + '<br/>高: ' + p.data[3].toFixed(2) + '<br/>'; }} else if (p.value!=null && (p.seriesName==='MA60'||p.seriesName==='MA120')) {{ h += p.marker + p.seriesName + ': ' + p.value.toFixed(2) + '<br/>'; }} else if (p.seriesName==='成交量' && p.value!=null) {{ h += p.marker + p.seriesName + ': ' + (p.value/10000).toFixed(0) + '万手<br/>'; }} }}); return h; }} }},
        legend: {{ data: ['K线', 'MA60', 'MA120', '成交量'], top: 32, left: 'center', textStyle: {{ fontSize: 12 }} }},
        grid: [{{ left: '10%', right: '8%', top: 70, height: '55%' }}, {{ left: '10%', right: '8%', top: '75%', height: '15%' }}],
        xAxis: [{{ type: 'category', data: data.dates, gridIndex: 0, axisLabel: {{ rotate: 30, fontSize: 10 }} }}, {{ type: 'category', data: data.dates, gridIndex: 1, axisLabel: {{ show: false }} }}],
        yAxis: [{{ type: 'value', scale: true, gridIndex: 0 }}, {{ type: 'value', gridIndex: 1, axisLabel: {{ formatter: function(v){{return (v/10000).toFixed(0)+'万';}} }} }}],
        dataZoom: [{{ type: 'slider', xAxisIndex: [0,1], bottom: 10, height: 20, start: 50, end: 100 }}],
        series: [
            {{ type: 'candlestick', name: 'K线', data: data.ohlc, itemStyle: {{ color: upColor, color0: downColor, borderColor: upColor, borderColor0: downColor }}, xAxisIndex: 0, yAxisIndex: 0, markArea: {{ silent: true, data: markAreaData, itemStyle: {{ color: 'rgba(255,215,0,0.15)' }}, label: {{ show: true, position: 'insideTop', formatter: '连板区', fontSize: 11 }} }}, markLine: {{ silent: true, symbol: 'none', data: markLines }} }},
            {{ type: 'line', name: 'MA60', data: data.ma60, smooth: true, lineStyle: {{ color: '#f39c12', width: 1.2 }}, symbol: 'none', xAxisIndex: 0, yAxisIndex: 0 }},
            {{ type: 'line', name: 'MA120', data: data.ma120, smooth: true, lineStyle: {{ color: '#3498db', width: 1.2 }}, symbol: 'none', xAxisIndex: 0, yAxisIndex: 0 }},
            {{ type: 'bar', name: '成交量', data: data.volumes, xAxisIndex: 1, yAxisIndex: 1, itemStyle: {{ color: function(p){{ const o=data.ohlc[p.dataIndex]; return o&&o[1]>=o[0]?upColor:downColor; }} }} }}
        ]
    }});
    window.addEventListener('resize', function() {{ chart.resize(); }});
}})();
</script>
</body>
</html>'''
    path = os.path.join(export_dir, f"analysis_{code}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
