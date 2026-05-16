"""HTML 图表报告生成模块 — ECharts K线图 + 均线 + 成交量"""
import json
import os
import pandas as pd
from collections import defaultdict


def export_html(results: list[dict], dfs: dict, passed: list[dict],
                screen_date: str, export_dir: str = "") -> str:
    """生成 HTML 图表报告，返回文件路径"""
    if not export_dir:
        export_dir = os.path.join(os.getcwd(), "data", "export")
    os.makedirs(export_dir, exist_ok=True)
    html = _build_html(results, dfs, passed, screen_date)
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
        }
    except Exception:
        return None


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
        key = (
            r.get("uptrend_stage", "") not in ("early", "mid"),
            not r.get("vol_shrinking", False),
            r.get("adj_days", 0) > 5,
            bool(r.get("broke_fib_618", False)),
        )
        groups[make_cat_name(key)].append(r)

    # 按失败维度数量排序
    def sort_key(item):
        name = item[0]
        fail_count = name.count("+") + 1
        if name == "未分类":
            fail_count = 0
        return (fail_count, name)

    return dict(sorted(groups.items(), key=sort_key))


def _build_html(results: list[dict], dfs: dict, passed: list[dict],
                screen_date: str) -> str:
    """组装完整 HTML 文档"""

    # ── 准备数据 ──────────────────────────────────────────
    excluded = [r for r in results if not r["meets_criteria"]]
    passed_sorted = sorted(passed, key=lambda x: x["score"], reverse=True)
    excluded_groups = _group_excluded(excluded)

    # 入选股票图表数据
    passed_charts = {}
    for r in passed_sorted:
        code = r["symbol"]
        if code in dfs:
            cd = _extract_chart_data(dfs[code], r)
            if cd:
                passed_charts[code] = cd

    # 未达标股票图表数据（按分组）
    excluded_charts: dict[str, list[dict]] = {}
    for cat_name, stocks in excluded_groups.items():
        excluded_charts[cat_name] = []
        for r in stocks:
            code = r["symbol"]
            if code in dfs:
                cd = _extract_chart_data(dfs[code], r)
                if cd:
                    excluded_charts[cat_name].append(cd)

    # 汇总 JSON
    all_chart_data: dict[str, dict] = {}
    all_chart_data.update(passed_charts)
    for charts in excluded_charts.values():
        for cd in charts:
            all_chart_data[cd["symbol"]] = cd

    json_data = json.dumps(all_chart_data, ensure_ascii=False)

    # 中文数字
    cn_num = ["一","二","三","四","五","六","七","八","九","十",
              "十一","十二","十三","十四","十五"]

    # ── 构建入选 HTML ─────────────────────────────────────
    passed_html = ""
    for i, r in enumerate(passed_sorted):
        code = r["symbol"]
        name = r.get("name", "")[:6]
        score = r["score"]
        stage = r["uptrend_stage"]
        adj_days = r["adj_days"]
        vol_ratio = r["adj_vol_ratio"]
        buy = r["buy_price"]
        protect = r["protect_price"]
        chart_id = f"chart_p_{code}"
        passed_html += f'''
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
            <span class="expand-icon">▸</span>
          </div>
          <div class="card-body">
            <div id="{chart_id}" class="chart-container"></div>
          </div>
        </div>'''

    # ── 构建未达标 HTML ───────────────────────────────────
    excluded_html = ""
    group_idx = 0
    for cat_name, charts in excluded_charts.items():
        group_idx += 1
        cn = cn_num[group_idx - 1] if group_idx - 1 < len(cn_num) else str(group_idx)
        excluded_html += f'''
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
            excluded_html += f'''
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
                <span class="expand-icon">▸</span>
              </div>
              <div class="card-body">
                <div id="{chart_id}" class="chart-container"></div>
              </div>
            </div>'''
        excluded_html += '''
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

.tabs {{ display: flex; gap: 8px; margin-bottom: 16px; }}
.tab-btn {{ padding: 10px 24px; border: none; border-radius: 20px; font-size: 15px; cursor: pointer; font-weight: 600; transition: all 0.2s; }}
.tab-btn.pass {{ background: #eafaf1; color: #27ae60; }}
.tab-btn.pass.active {{ background: #27ae60; color: white; }}
.tab-btn.fail {{ background: #fdedec; color: #e74c3c; }}
.tab-btn.fail.active {{ background: #e74c3c; color: white; }}
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}

.stock-card {{ background: white; border-radius: 8px; margin-bottom: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.05); overflow: hidden; transition: box-shadow 0.2s; }}
.stock-card:hover {{ box-shadow: 0 2px 12px rgba(0,0,0,0.1); }}
.stock-card.passed {{ border-left: 4px solid #27ae60; }}
.stock-card.excluded {{ border-left: 4px solid #e74c3c; }}

.card-header {{ display: flex; align-items: center; padding: 12px 16px; cursor: pointer; user-select: none; transition: background 0.15s; gap: 16px; }}
.card-header:hover {{ background: #f8f9fa; }}
.passed .card-header:hover {{ background: #f0faf3; }}
.excluded .card-header:hover {{ background: #fef5f5; }}

.card-left {{ display: flex; align-items: center; gap: 10px; min-width: 240px; }}
.rank {{ font-weight: 700; font-size: 16px; color: #7f8c8d; width: 32px; }}
.symbol {{ font-weight: 700; font-size: 14px; color: #2c3e50; }}
.name {{ font-size: 13px; color: #7f8c8d; }}
.score-badge {{ background: #27ae60; color: white; padding: 2px 10px; border-radius: 12px; font-size: 13px; font-weight: 600; }}

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

.footer {{ text-align: center; padding: 30px 0 10px; font-size: 12px; color: #bdc3c7; }}
.footer a {{ color: #bdc3c7; }}
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
    <div class="num">{len(passed_sorted)}</div>
    <div class="label">✅ 入选</div>
  </div>
  <div class="summary-card fail">
    <div class="num">{len(excluded)}</div>
    <div class="label">❌ 未达标</div>
  </div>
</div>

<div class="tabs">
  <button class="tab-btn pass active" onclick="switchTab('passed')">✅ 入选 ({len(passed_sorted)})</button>
  <button class="tab-btn fail" onclick="switchTab('excluded')">❌ 未达标 ({len(excluded)})</button>
</div>

<div id="tab-passed" class="tab-content active">
{passed_html if passed_html else '<div style="padding:20px;text-align:center;color:#bdc3c7;">无入选标的</div>'}
</div>

<div id="tab-excluded" class="tab-content">
{excluded_html if excluded_html else '<div style="padding:20px;text-align:center;color:#bdc3c7;">无未达标标的</div>'}
</div>

<div class="footer">
  免责声明：本报告仅供参考，不构成投资建议<br>
  Generated by quant screener · {screen_date}
</div>

</div>

<script>
const ALL_DATA = {json_data};
window._charts = {{}};

function switchTab(tab) {{
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    if (tab === 'passed') {{
        document.querySelector('.tab-btn.pass').classList.add('active');
        document.getElementById('tab-passed').classList.add('active');
    }} else {{
        document.querySelector('.tab-btn.fail').classList.add('active');
        document.getElementById('tab-excluded').classList.add('active');
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
    // containerId format: "chart_p_CODE" or "chart_e_CODE"
    const symbol = containerId.replace('chart_p_', '').replace('chart_e_', '');
    const data = ALL_DATA[symbol];
    if (!data) return;

    const dom = document.getElementById(containerId);
    if (!dom) return;
    const chart = echarts.init(dom);
    chart.setOption(buildOption(data));
    window._charts[containerId] = chart;
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
window.addEventListener('resize', function() {{
    Object.values(window._charts).forEach(function(c) {{ c.resize(); }});
}});
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
