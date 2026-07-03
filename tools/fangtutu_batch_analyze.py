from __future__ import annotations
#!/usr/bin/env python3
"""
方土土批量分析脚本
每晚9点对两板入选和多板入选的股票进行方土土框架分析，
筛选偏多标的，更新HTML报告。
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

import pandas as pd

# 将项目根加入 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.storage import (
    get_conn, init_db, save_fangtutu_result, query_fangtutu_bullish,
)
from src.html_reporter import export_html
from src.indicator import analyze_one_stock
from src.data_fetcher import fetch_daily_kline, fetch_limit_up_pool, fetch_trading_calendar


def get_latest_screen_date() -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT MAX(screen_date) as d FROM screen_result"
    ).fetchone()
    conn.close()
    return row["d"] if row else None


def get_candidates(screen_date: str) -> list[dict]:
    """获取当天入选的股票（两板+多板，达标+放宽条件）"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM screen_result
        WHERE screen_date = ? AND board_type = '2'
        ORDER BY score DESC
    """, (screen_date,)).fetchall()
    two_board = [dict(r) for r in rows]

    rows = conn.execute("""
        SELECT * FROM screen_result
        WHERE screen_date = ? AND board_type = 'multi'
        ORDER BY score DESC
    """, (screen_date,)).fetchall()
    multi_board = [dict(r) for r in rows]
    conn.close()

    # 入选定义：meets_criteria 或 属于放宽条件（仅阶段/量比不符）
    def is_admitted(r):
        if r["meets_criteria"]:
            return True
        stage_bad = r.get("uptrend_stage", "") not in ("early", "mid")
        vol_bad = (r.get("adj_vol_ratio") or 0) >= 1.0
        adj_bad = (r.get("adj_days") or 0) > 5
        fib_bad = bool(r.get("broke_fib_618", False))
        key = (stage_bad, vol_bad, adj_bad, fib_bad)
        allowed = {
            (True, False, False, False),
            (False, True, False, False),
            (True, True, False, False),
        }
        return key in allowed

    two_admitted = [r for r in two_board if is_admitted(r)]
    multi_admitted = [r for r in multi_board if is_admitted(r)]

    return two_admitted, multi_admitted


def build_stock_data_string(stocks: list[dict], label: str) -> str:
    """构建每只股票的技术数据摘要"""
    lines = [f"\n### {label}（{len(stocks)}只）\n"]
    for i, r in enumerate(stocks):
        code = r["symbol"]
        name = r.get("name", "")
        score = r.get("score", 0)
        bc = r.get("board_count", 2)
        stage = r.get("uptrend_stage", "")
        adj_days = r.get("adj_days", 0)
        vol_ratio = r.get("adj_vol_ratio", 0)
        buy = r.get("buy_price", 0)
        protect = r.get("protect_price", 0)
        fib = r.get("fib_618", 0)
        lu_high = r.get("lu_high", 0)
        lu_low = r.get("lu_low", 0)
        lu_start = r.get("lu_date_start", "")
        lu_end = r.get("lu_date_end", "")

        lines.append(
            f"#{i + 1} {code} {name} | 连板{bc} | "
            f"得分{score} | 阶段{stage} | 调整{adj_days}天 | 量比{vol_ratio} | "
            f"买点{buy} | 保护{protect} | Fib618={fib} | "
            f"连板区{lu_start}~{lu_end} 高{lu_high}低{lu_low}"
        )
    return "\n".join(lines)


def build_batch_prompt(two_stocks: list[dict], multi_stocks: list[dict],
                       fangtutu_context: dict, screen_date: str) -> str:
    """构建批量分析 prompt"""
    all_stocks = two_stocks + multi_stocks
    if not all_stocks:
        return ""

    stock_data = ""
    if two_stocks:
        stock_data += build_stock_data_string(two_stocks, "两板入选")
    if multi_stocks:
        stock_data += build_stock_data_string(multi_stocks, "多板入选")

    manual = fangtutu_context.get("manual_summary", "")
    snippets = fangtutu_context.get("snippets", [])
    guidance = fangtutu_context.get("answer_guidance", [])

    snippets_text = "\n".join(
        f"- [{s['source']}] {s['summary'][:200]}" for s in snippets[:6]
    )
    guidance_text = "\n".join(f"- {g}" for g in guidance)

    prompt = f"""你是 A 股「二板涨停 N 型战法」选股系统的分析助手。请对以下每只入选股票，按照方土土（Al Brooks）价格行为框架进行技术分析。

## 方土土核心原则

{manual}

## 关键知识点

{snippets_text}

## 分析指引

{guidance_text}

## 待分析股票（选股日期 {screen_date}）
{stock_data}

## 分析要求

对每只股票，按以下结构输出：

结论：从「偏多」「偏空」「震荡」「观察」中选一个，说明成立条件。
价格行为：趋势判断、震荡区间、突破/失败突破、EMA20位置、信号K、关键支撑阻力。
方土土依据：引用的框架原则。
交易计划：走强看什么，走弱看什么，无效条件。
风险控制：止损位、仓位建议。

## 输出格式

必须输出纯 JSON，键为股票代码，值为分析对象：

```json
{{
  "600001": {{
    "conclusion": "偏多",
    "price_action": "MA60>MA120多头排列，回踩Fib618不破，近3日缩量企稳...",
    "fangtutu_basis": "来源：突破确认+信号K。缩量回踩618是典型的trend continuation setup...",
    "trade_plan": "走强看放量站上MA20；走弱看跌破保护价；无效条件：跌破连板区低点",
    "risk_control": "止损放在保护价下方2%，宽止损轻仓，单票不超过总仓位5%"
  }},
  "000839": {{ ... }}
}}
```

只输出 JSON，不要其他内容。"""
    return prompt


def parse_batch_response(text: str) -> dict[str, dict]:
    """解析 Claude 返回的批量分析 JSON"""
    # 提取 JSON 块
    text = text.strip()
    # 尝试提取 ```json ... ``` 块
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        text = text[start:end].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 宽松解析：尝试找到外层的 {
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start >= 0 and brace_end > brace_start:
            try:
                return json.loads(text[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                pass
        print(f"[WARN] 无法解析 Claude 返回的 JSON")
        return {}


def call_claude_api(prompt: str, max_tokens: int = 8000) -> str:
    """调用 Claude API（通过 Anthropic SDK）"""
    from anthropic import Anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY 未设置")

    client = Anthropic(api_key=api_key, base_url=base_url)

    start = time.time()
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = time.time() - start
    print(f"[INFO] API 调用完成，耗时 {elapsed:.1f}s")

    # 提取文本内容（跳过 thinking blocks）
    for block in msg.content:
        if hasattr(block, 'text'):
            return block.text
    raise RuntimeError("API 响应中没有文本内容")


def call_claude_cli(prompt: str) -> str:
    """通过 claude CLI 调用（备选方案）"""
    import subprocess
    import tempfile

    # 写 prompt 到临时文件
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(prompt)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["claude", "-p", "--print", "--input-file", tmp_path],
            capture_output=True, text=True, timeout=600,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        return result.stdout
    finally:
        os.unlink(tmp_path)


def main():
    parser = argparse.ArgumentParser(description="方土土批量分析")
    parser.add_argument("--date", default=None, help="选股日期，默认取最新")
    parser.add_argument("--use-cli", action="store_true", help="使用 claude CLI 而非 API")
    parser.add_argument("--dry-run", action="store_true", help="干跑模式：不调API，用假数据测试HTML注入")
    args = parser.parse_args()

    # 初始化
    init_db()
    screen_date = args.date or get_latest_screen_date()
    if not screen_date:
        print("[ERROR] 未找到选股结果，请先运行 main.py")
        sys.exit(1)

    print(f"[INFO] 分析日期: {screen_date}")

    # 获取方土土知识库上下文
    from tools.fangtutu_context import get_context
    fangtutu_ctx = get_context("分析这批股票的当前技术形态，判断偏多、偏空还是震荡")

    # 获取入选股票
    two_stocks, multi_stocks = get_candidates(screen_date)
    all_stocks = two_stocks + multi_stocks
    print(f"[INFO] 两板入选: {len(two_stocks)}只, 多板入选: {len(multi_stocks)}只, 合计: {len(all_stocks)}只")

    if not all_stocks:
        print("[INFO] 今日无入选标的，跳过分析")
        regenerate_html(screen_date)
        return

    if args.dry_run:
        print("[DRY-RUN] 使用模拟数据测试 HTML 注入")
        # 模拟分析结果
        mock_results = {}
        for s in all_stocks:
            mock_results[s["symbol"]] = {
                "conclusion": "偏多",
                "price_action": f"模拟价格行为分析：MA60>MA120多头排列，近5日缩量调整，回踩Fib支撑不破。",
                "fangtutu_basis": "模拟依据：突破确认+信号K。调整缩量不破618是典型的趋势延续结构。",
                "trade_plan": f"走强看放量站上MA20；走弱看跌破最近低点；无效条件：跌破连板区低点。",
                "risk_control": f"止损放在保护价下方2%，宽止损轻仓。",
            }
        # 保存到 DB
        for symbol, analysis in mock_results.items():
            conclusion = analysis["conclusion"]
            detail = json.dumps(analysis, ensure_ascii=False)
            save_fangtutu_result(screen_date, symbol, conclusion, detail)

        regenerate_html(screen_date)
        print("[DRY-RUN] 完成，已更新 HTML")
        return

    # 分批调用 API（每批 25 只）
    BATCH_SIZE = 25
    all_results = {}
    # 合并所有股票并按两板/多板交替排列
    all_stocks_combined = list(two_stocks) + list(multi_stocks)

    for batch_start in range(0, len(all_stocks_combined), BATCH_SIZE):
        batch = all_stocks_combined[batch_start:batch_start + BATCH_SIZE]
        # 按 board_type 拆分本批
        batch_two = [s for s in batch if s.get("board_type") != "multi"]
        batch_multi = [s for s in batch if s.get("board_type") == "multi"]
        print(f"[INFO] 批次 {batch_start // BATCH_SIZE + 1}: 两板{len(batch_two)}只 + 多板{len(batch_multi)}只")

        prompt = build_batch_prompt(batch_two, batch_multi, fangtutu_ctx, screen_date)
        if args.use_cli:
            raw = call_claude_cli(prompt)
        else:
            raw = call_claude_api(prompt)

        batch_results = parse_batch_response(raw)
        print(f"[INFO] 批次解析: {len(batch_results)} 只")
        all_results.update(batch_results)

    print(f"[INFO] 总共解析到 {len(all_results)} 只股票的分析结果")

    # 保存到 DB（全部结论，不限偏多）
    for symbol, analysis in all_results.items():
        conclusion = analysis.get("conclusion", "观察")
        detail = json.dumps(analysis, ensure_ascii=False)
        save_fangtutu_result(screen_date, symbol, conclusion, detail)

    # 重新生成 HTML
    regenerate_html(screen_date)

    print("[DONE] 分析完成")


def regenerate_html(screen_date: str):
    """重建 HTML 报告并注入方土土分析"""
    import re

    # 查 DB 获取方土土偏多结果
    bullish_rows = query_fangtutu_bullish(screen_date)

    # 拆分为两板和多板的偏多结果
    two_bullish = []
    multi_bullish = []
    for r in bullish_rows:
        detail = {}
        if r.get("fangtutu_detail"):
            try:
                detail = json.loads(r["fangtutu_detail"])
            except json.JSONDecodeError:
                pass
        entry = {
            "symbol": r["symbol"],
            "name": r.get("name", ""),
            "score": r.get("score", 0),
            "board_count": r.get("board_count", 2),
            "board_type": r.get("board_type", "2"),
            "conclusion": r.get("fangtutu_conclusion", ""),
            "price_action": detail.get("price_action", ""),
            "fangtutu_basis": detail.get("fangtutu_basis", ""),
            "trade_plan": detail.get("trade_plan", ""),
            "risk_control": detail.get("risk_control", ""),
        }
        if r.get("board_type") == "multi":
            multi_bullish.append(entry)
        else:
            two_bullish.append(entry)

    # 读取原始 HTML 并注入方土土板块
    export_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "data", "export")
    html_path = os.path.join(export_dir, f"screen_result_{screen_date}.html")

    if os.path.exists(html_path):
        html = open(html_path, encoding="utf-8").read()

        # 幂等：移除旧版注入的方土土内容（兼容旧格式）
        # 1. 移除旧版 <!-- FANGTUTU_START -->...<!-- FANGTUTU_END --> 块及其后的多余 </div>
        html = re.sub(
            r'\n?<!-- FANGTUTU_START -->.*?<!-- FANGTUTU_END -->\s*</div>',
            '', html, flags=re.DOTALL
        )
        # 2. 移除旧版注入的 CSS
        html = re.sub(
            r'\n?/\* ── 方土土偏多分析板块.*?\*/\s*\.fangtutu-section[^}]*\}[\s\S]*?\.fangtutu-value\s*\{[^}]*\}',
            '', html
        )
        # 3. 移除旧版注入的 JS（toggleFangtutu* 函数）
        html = re.sub(
            r'\n?\s*function toggleFangtutuSection[\s\S]*?}\s*\n\s*function toggleFangtutuCard[\s\S]*?}\s*',
            '', html
        )

        # 构建新的方土土内容并注入到 tab-fangtutu 内
        total = len(two_bullish) + len(multi_bullish)
        fangtutu_content = build_fangtutu_tab_content(two_bullish, multi_bullish)
        # 替换 tab-fangtutu 内的全部内容（兼容首次运行的 placeholder 和重复运行的已有内容）
        html = re.sub(
            r'(<div id="tab-fangtutu"\s+class="tab-content">)[\s\S]*?(?=\s*</div>\s*\n\s*<div class="footer">)',
            rf'\1\n{fangtutu_content}',
            html
        )

        # 更新 tab 按钮上的数量
        html = re.sub(
            r'(<button class="tab-btn fangtutu"[^>]*>方土土分析) \([\d]+\)',
            rf'\1 ({total})',
            html
        )

        # 写回文件
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        # 同时写 latest
        latest_path = os.path.join(export_dir, "screen_result_latest.html")
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[INFO] HTML 已更新: {html_path}")


def build_fangtutu_tab_content(two_bullish: list[dict], multi_bullish: list[dict]) -> str:
    """构建方土土分析 tab 的完整内容（两板 + 多板两个可折叠板块）"""
    sections = []
    for label, stocks in [("两板", two_bullish), ("多板", multi_bullish)]:
        sections.append(build_fangtutu_section(stocks, label))
    return "\n".join(sections)


def build_fangtutu_section(bullish_stocks: list[dict], label: str) -> str:
    """构建方土土偏多分析板块 HTML（可折叠子板块）"""
    if not bullish_stocks:
        return f'''        <div class="fangtutu-section">
          <div class="fangtutu-header">
            <span class="fangtutu-title">方土土偏多分析 · {label}入选</span>
            <span class="fangtutu-empty">今日暂无偏多标的</span>
          </div>
        </div>'''

    cards = ""
    for i, s in enumerate(bullish_stocks):
        code = s["symbol"]
        name = s.get("name", "")[:8]
        score = s.get("score", 0)
        bc = s.get("board_count", 2)
        conclusion = s.get("conclusion", "")
        price_action = s.get("price_action", "")
        fangtutu_basis = s.get("fangtutu_basis", "")
        trade_plan = s.get("trade_plan", "")
        risk_control = s.get("risk_control", "")

        # 结论 badge 颜色（前缀匹配）
        cc = "#7f8c8d"
        for prefix, color in [("偏多", "#27ae60"), ("偏空", "#e74c3c"), ("震荡", "#95a5a6"), ("观察", "#f39c12")]:
            if conclusion.startswith(prefix):
                cc = color
                break

        cards += f'''
        <div class="fangtutu-card stock-card" data-symbol="{code}" data-tab="fangtutu">
          <div class="fangtutu-card-header" onclick="toggleFangtutuCard(this)">
            <div class="fangtutu-card-left">
              <span class="rank">#{i + 1}</span>
              <span class="symbol">{code}</span>
              <span class="name">{name}</span>
              <span class="board-badge">连板{bc}</span>
              <span class="score-badge">{score}分</span>
            </div>
            <span class="fangtutu-conclusion" style="background:{cc}">{conclusion}</span>
            <span class="expand-icon">▸</span>
          </div>
          <div class="fangtutu-card-body">
            <div class="fangtutu-item">
              <div class="fangtutu-label">结论</div>
              <div class="fangtutu-value">{conclusion}</div>
            </div>
            <div class="fangtutu-item">
              <div class="fangtutu-label">价格行为</div>
              <div class="fangtutu-value">{price_action}</div>
            </div>
            <div class="fangtutu-item">
              <div class="fangtutu-label">方土土依据</div>
              <div class="fangtutu-value">{fangtutu_basis}</div>
            </div>
            <div class="fangtutu-item">
              <div class="fangtutu-label">交易计划</div>
              <div class="fangtutu-value">{trade_plan}</div>
            </div>
            <div class="fangtutu-item">
              <div class="fangtutu-label">风险控制</div>
              <div class="fangtutu-value">{risk_control}</div>
            </div>
          </div>
        </div>'''

    return f'''        <div class="fangtutu-section">
          <div class="fangtutu-header" onclick="toggleFangtutuSection(this)">
            <span class="fangtutu-title">方土土偏多分析 · {label}入选</span>
            <span class="fangtutu-count">{len(bullish_stocks)}只</span>
            <span class="expand-icon">▸</span>
          </div>
          <div class="fangtutu-body">{cards}
          </div>
        </div>'''


if __name__ == "__main__":
    main()
