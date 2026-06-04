#!/usr/bin/env python3.8
"""Unified HTTP + WebSocket server — serves HTML reports AND Claude chat on one port.

Run:  python3.8 chat_server.py [--port 8080]
Stop: Ctrl+C

Replaces both:
  - python3 -m http.server 8080       (static files)
  - standalone WebSocket server        (Claude chat)
"""

import asyncio
import json
import os
import subprocess
import sys
import mimetypes
from pathlib import Path

import aiohttp.web
import aiohttp.web_ws

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(PROJECT_DIR, "data", "export")

SYSTEM_CONTEXT = (
    "你正在和用户讨论量化选股报告。当前项目是一个 A 股「二板涨停 N 型战法」选股系统，"
    "代码在 /home/admin/claude/quant。HTML 报告在 data/export/ 目录下。"
    "用户可能会问选股结果、技术指标含义、K 线图解读等问题。请用中文简洁回答。"
)

# Pre-compute for index page
CN_NUM = ["一","二","三","四","五","六","七","八","九","十",
          "十一","十二","十三","十四","十五"]

MIME_MAP = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".csv": "text/csv",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".txt": "text/plain",
}


def build_prompt(text: str, is_first: bool) -> str:
    if is_first:
        return f"{SYSTEM_CONTEXT}\n\n---\n\n用户: {text}"
    return text


async def stream_claude(ws: aiohttp.web_ws.WebSocketResponse,
                         text: str, is_first: bool):
    """Run claude --print and get plain text result, send to WebSocket."""
    cmd = ["claude", "--print"]
    if not is_first:
        cmd.append("-c")
    cmd.append(build_prompt(text, is_first))

    env = os.environ.copy()

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=PROJECT_DIR,
        env=env,
    )

    try:
        stdout, stderr_data = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace").strip()

        if proc.returncode == 0 and output:
            await ws.send_json({"type": "text", "text": output})
            await ws.send_json({"type": "done", "stop_reason": "completed", "is_error": False})
        else:
            err_text = stderr_data.decode("utf-8", errors="replace")[:500] if stderr_data else "unknown error"
            await ws.send_json({"type": "error", "text": err_text})

        if stderr_data:
            print(f"[claude stderr] {stderr_data.decode('utf-8', errors='replace')[:500]}")
    except Exception as e:
        await ws.send_json({"type": "error", "text": str(e)})


# ═══════════════════════════════════════════════════════════
#  HTTP handlers
# ═══════════════════════════════════════════════════════════

async def handle_static(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Serve static files from data/export/ with UTF-8 encoding."""
    rel = request.match_info.get("path", "screen_result_latest.html")
    # Security: prevent path traversal
    filepath = os.path.normpath(os.path.join(EXPORT_DIR, rel))
    if not filepath.startswith(os.path.normpath(EXPORT_DIR)):
        raise aiohttp.web.HTTPForbidden()

    if not os.path.isfile(filepath):
        raise aiohttp.web.HTTPNotFound()

    ext = os.path.splitext(filepath)[1].lower()
    content_type = MIME_MAP.get(ext, "application/octet-stream")

    if ext in (".html", ".css", ".js", ".json", ".csv", ".txt"):
        with open(filepath, "r", encoding="utf-8") as f:
            body = f.read()
        return aiohttp.web.Response(text=body, content_type=content_type, charset="utf-8")
    else:
        return aiohttp.web.FileResponse(filepath)


async def handle_index(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Serve index page listing available reports."""
    files = []
    if os.path.isdir(EXPORT_DIR):
        for f in sorted(os.listdir(EXPORT_DIR), reverse=True):
            if f.endswith(".html") and f != "screen_result_latest.html":
                fp = os.path.join(EXPORT_DIR, f)
                size_kb = os.path.getsize(fp) // 1024
                mtime = os.path.getmtime(fp)
                files.append((f, size_kb, mtime))

    rows = ""
    for fname, size, _mtime in files:
        rows += f'<tr><td><a href="/{fname}">{fname}</a></td><td>{size} KB</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Quant Reports</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background: #f5f6fa; color: #2c3e50; }}
.container {{ max-width: 800px; margin: 40px auto; padding: 20px; }}
.header {{ background: linear-gradient(135deg, #1a1a2e, #16213e); color: white; padding: 24px 32px; border-radius: 12px; margin-bottom: 20px; }}
.header h1 {{ font-size: 22px; }}
.header p {{ font-size: 13px; color: #a0aec0; margin-top: 4px; }}
.card {{ background: white; border-radius: 10px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ text-align: left; padding: 10px 12px; font-size: 13px; color: #7f8c8d; border-bottom: 2px solid #eee; }}
td {{ padding: 12px; font-size: 14px; border-bottom: 1px solid #f5f5f5; }}
a {{ color: #2980b9; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
tr:hover {{ background: #f8f9fa; }}
.footer {{ text-align: center; padding: 20px; font-size: 12px; color: #bdc3c7; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
  <h1>量化选股报告</h1>
  <p>二板涨停 N 型战法 · 每日筛选结果</p>
</div>
<div class="card">
  <table>
    <thead><tr><th>报告文件</th><th>大小</th></tr></thead>
    <tbody>{rows if rows else '<tr><td colspan="2" style="color:#bdc3c7;">暂无报告</td></tr>'}</tbody>
  </table>
</div>
<div class="footer">
  免责声明：本报告仅供参考，不构成投资建议
</div>
</div>
</body>
</html>"""
    return aiohttp.web.Response(text=html, content_type="text/html", charset="utf-8")


async def handle_ws(request: aiohttp.web.Request) -> aiohttp.web.WebSocketResponse:
    """WebSocket handler — one Claude conversation per connection."""
    ws = aiohttp.web.WebSocketResponse()
    await ws.prepare(request)

    print(f"[connect] {request.remote}")
    is_first = True

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "text": "Invalid JSON"})
                    continue

                text = (data.get("text") or "").strip()
                if not text:
                    continue

                await stream_claude(ws, text, is_first)
                is_first = False
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print(f"[ws error] {ws.exception()}")
    except Exception as e:
        print(f"[disconnect] {request.remote}: {e}")
    finally:
        print(f"[closed] {request.remote}")

    return ws


# ═══════════════════════════════════════════════════════════
#  App factory
# ═══════════════════════════════════════════════════════════

def create_app() -> aiohttp.web.Application:
    app = aiohttp.web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/ws", handle_ws)
    # Static files: /screen_result_2026-06-03.html etc.
    app.router.add_get("/{path:.*\\.html}", handle_static)
    app.router.add_get("/{path:.*\\.csv}", handle_static)
    app.router.add_get("/{path:.*\\.json}", handle_static)
    app.router.add_get("/{path:.*\\.txt}", handle_static)
    app.router.add_get("/{path:.*\\.css}", handle_static)
    app.router.add_get("/{path:.*\\.js}", handle_static)
    return app


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Unified HTTP+WS server for quant reports + Claude chat")
    parser.add_argument("--port", type=int, default=8080, help="Listen port (default 8080)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Listen host")
    args = parser.parse_args()

    print(f"Unified server: http://{args.host}:{args.port}")
    print(f"  Static files: {EXPORT_DIR}")
    print(f"  Chat WS:      ws://{args.host}:{args.port}/ws")
    print(f"  Project:      {PROJECT_DIR}")

    app = create_app()
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, args.host, args.port)
    await site.start()
    print("Ready. Press Ctrl+C to stop.")
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
