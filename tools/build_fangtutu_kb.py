from __future__ import annotations

"""Build a portable local Fangtutu transcript knowledge base."""

import argparse
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable


SOURCE_DIRS = (
    Path("价格心理学入门") / "价格心理学入门",
    Path("专题课") / "专题课",
    Path("实战"),
)
DEFAULT_KB_DIR = Path("data") / "knowledge"
DEFAULT_MANUAL_PATH = Path("docs") / "fangtutu" / "distilled_manual.md"
CHUNK_MAX_CHARS = 1200
CHUNK_OVERLAP_CHARS = 160

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "趋势与震荡": ("趋势", "震荡", "交易区间", "trading range", "always in", "单边"),
    "EMA20": ("EMA20", "EMA", "回踩", "反弹到EMA", "均线"),
    "突破确认": ("突破", "follow through", "确认", "失败突破", "breakout", "假突破"),
    "双顶双底": ("双顶", "双底", "double top", "double bottom", "头肩"),
    "楔形": ("歇型", "楔形", "wedge", "三推", "123", "parabolic"),
    "Measure Move": ("measure move", "MM", "目标位", "翻一倍", "盈亏比"),
    "信号K": ("信号K", "signal bar", "大阳线", "大阴线", "收在最高", "收在最低"),
    "仓位管理": ("仓位", "I don't care size", "小仓位", "重仓", "加仓", "宽止损"),
    "风险控制": ("风险", "止损", "保护", "亏损", "爆仓", "无效", "离场"),
    "交易心理": ("情绪", "心态", "耐心", "客观", "随机", "概率", "不要觉得"),
    "实战复盘": ("实战", "实盘", "边做边讲", "Bear Surprise", "Bull Surprise", "鲍威尔", "特殊事件"),
}

MANUAL_TEXT = """# 方土土交易框架蒸馏手册

这份手册是给 agent 使用的稳定背景，不替代原文检索。回答股票、大盘、K线、买卖点、止损、仓位问题时，先使用本手册建立分析框架，再结合检索到的 transcript 片段、实战交易讲解和项目内量化数据。

## 核心交易观

- 市场是概率过程，不要把一次失败解释成市场针对自己。
- 先判断市场环境，再谈形态。趋势、震荡、突破、失败突破对应完全不同的处理方式。
- 赚钱不是最难的，真正难的是避免大亏。风险控制优先于入场冲动。
- 不要重仓。使用亏了也不影响情绪的 `I don't care size`。
- 每笔交易先定义无效条件和止损位置，再考虑仓位和盈利目标。

## 市场状态检查

1. 趋势：是否有连续同向K线、强收盘、有效 follow-through。
2. 震荡：多空双方都不顺，突破容易失败，优先高抛低吸或等待。
3. 突破：必须观察后续确认，单根突破K线不足以证明趋势成立。
4. 失败突破：突破后没有跟随，反向大K线或吞没常提示回到震荡。
5. EMA20：回踩或反弹到 EMA20 附近，经常形成双顶、双底、楔形等决策区。
6. 高潮：连续快速上涨/下跌后，要警惕 buy climax 或 sell climax 后的反转/震荡。

## 常用形态语言

- 信号K：收在高位的大阳线偏多，收在低位的大阴线偏空，但要结合位置。
- Follow-through：突破后下一根或后续K线是否继续支持突破方向。
- 双顶/双底：常出现在震荡区间或 EMA20 附近，是反转或延续的候选结构。
- 楔形/三推：第三次推进后容易反转，但强趋势中的第一次反转常会失败。
- Measure move：可作为目标位参考，但不能死拿，必须根据后续价格行为调整。
- 实战复盘：边交易边观察当下K线，重视突然的 Bull/Bear Surprise、特殊事件、利润保护和震荡化信号。

## 决策顺序

1. 明确标的和周期。
2. 看项目内可验证数据：筛选结果、K线、均线、涨跌幅、量能、支撑/保护位。
3. 判断市场状态：趋势、震荡、突破、失败突破、EMA20附近反应。
4. 用方土土框架解释概率：哪些证据支持多头，哪些证据支持空头。
5. 如果有实战片段，优先吸收其中的盘中处理经验：何时持有、何时保护利润、何时承认震荡。
6. 给条件计划：走强看什么、走弱看什么、无效条件是什么。
7. 最后讲风险：止损、仓位、不要重仓、不要情绪化加仓。

## 风险规则

- 宽止损必须配小仓位。
- 如果还计划加仓，初始仓位必须更小，总风险不能因为加仓失控。
- 不要刚亏损就急着加仓，不要因为想赚回亏损而扩大风险。
- 如果突破没有确认，或强信号K后没有跟随，要降低确定性。
- 回答用户时避免“必须买/一定涨/梭哈”等措辞，只给条件分析。

## 默认回答结构

1. 结论：偏多、偏空、震荡、观察，并说明条件。
2. 价格行为：趋势/震荡/突破/失败突破/EMA20/形态/follow-through。
3. 方土土框架依据：概括相关原则，必要时附来源文件。
4. 交易计划：确认条件、无效条件、观察点。
5. 风险控制：止损、仓位、避免重仓和情绪交易。
"""


def resolve_project_root(project_root: Path | None = None) -> Path:
    if project_root is not None:
        return project_root.expanduser().resolve()
    env_root = os.environ.get("QUANT_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def resolve_kb_dir(project_root: Path, kb_dir: Path | None = None) -> Path:
    if kb_dir is not None:
        return kb_dir.expanduser().resolve()
    env_kb = os.environ.get("FANGTUTU_KB_DIR")
    if env_kb:
        return Path(env_kb).expanduser().resolve()
    return project_root / DEFAULT_KB_DIR


def normalize_text(text: str) -> str:
    text = text.replace("\ufeff", "")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def relpath(path: Path, project_root: Path) -> str:
    return path.resolve().relative_to(project_root.resolve()).as_posix()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def detect_topics(text: str) -> list[str]:
    text_lower = text.lower()
    topics = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword.lower() in text_lower for keyword in keywords):
            topics.append(topic)
    return topics


def iter_transcript_files(project_root: Path) -> Iterable[Path]:
    for source_dir in SOURCE_DIRS:
        full_dir = project_root / source_dir
        if not full_dir.exists():
            continue
        yield from sorted(full_dir.glob("*.txt"))


def read_transcripts(project_root: Path) -> list[dict]:
    transcripts = []
    for path in iter_transcript_files(project_root):
        raw_text = path.read_text(encoding="utf-8", errors="replace")
        text = normalize_text(raw_text)
        if not text:
            continue
        source = relpath(path, project_root)
        transcripts.append(
            {
                "source": source,
                "series": Path(source).parts[0],
                "title": path.stem,
                "byte_length": path.stat().st_size,
                "char_length": len(text),
                "sha256": sha256_text(text),
                "topics": detect_topics(text),
                "text": text,
            }
        )
    return transcripts


def split_text(text: str, max_chars: int = CHUNK_MAX_CHARS) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    sentences = re.split(r"(?<=[。！？!?])\s*", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            for start in range(0, len(sentence), max_chars - CHUNK_OVERLAP_CHARS):
                piece = sentence[start : start + max_chars].strip()
                if piece:
                    chunks.append(piece)
            continue
        if len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current.strip())
            overlap = current[-CHUNK_OVERLAP_CHARS:] if len(current) > CHUNK_OVERLAP_CHARS else current
            current = f"{overlap}{sentence}"
        else:
            current = f"{current}{sentence}"
    if current.strip():
        chunks.append(current.strip())
    return chunks


def summarize(text: str, limit: int = 160) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"


def build_chunks(transcripts: list[dict]) -> list[dict]:
    chunks: list[dict] = []
    next_id = 1
    for transcript in transcripts:
        for chunk_index, chunk_text in enumerate(split_text(transcript["text"]), start=1):
            chunk_topics = detect_topics(chunk_text) or transcript["topics"]
            chunks.append(
                {
                    "id": f"fangtutu-{next_id:05d}",
                    "source": transcript["source"],
                    "series": transcript["series"],
                    "title": transcript["title"],
                    "chunk_index": chunk_index,
                    "sha256": sha256_text(chunk_text),
                    "topics": chunk_topics,
                    "summary": summarize(chunk_text),
                    "text": chunk_text,
                }
            )
            next_id += 1
    return chunks


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_manual(project_root: Path) -> Path:
    manual_path = project_root / DEFAULT_MANUAL_PATH
    manual_path.parent.mkdir(parents=True, exist_ok=True)
    manual_path.write_text(MANUAL_TEXT, encoding="utf-8", newline="\n")
    return manual_path


def build_sqlite_index(index_path: Path, chunks: list[dict]) -> bool:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    if index_path.exists():
        index_path.unlink()

    conn = sqlite3.connect(index_path)
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE fangtutu_chunks USING fts5("
            "id UNINDEXED, source UNINDEXED, title UNINDEXED, topics UNINDEXED, summary, text)"
        )
        conn.executemany(
            "INSERT INTO fangtutu_chunks (id, source, title, topics, summary, text) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    chunk["id"],
                    chunk["source"],
                    chunk["title"],
                    ",".join(chunk["topics"]),
                    chunk["summary"],
                    chunk["text"],
                )
                for chunk in chunks
            ],
        )
        conn.commit()
        return True
    except sqlite3.Error:
        conn.rollback()
        return False
    finally:
        conn.close()


def build_kb(project_root: Path | None = None, kb_dir: Path | None = None) -> dict:
    root = resolve_project_root(project_root)
    target_kb_dir = resolve_kb_dir(root, kb_dir)
    target_kb_dir.mkdir(parents=True, exist_ok=True)

    transcripts = read_transcripts(root)
    chunks = build_chunks(transcripts)

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_dirs": [path.as_posix() for path in SOURCE_DIRS],
        "source_file_count": len(transcripts),
        "chunk_count": len(chunks),
        "files": [
            {
                key: transcript[key]
                for key in ("source", "series", "title", "byte_length", "char_length", "sha256", "topics")
            }
            for transcript in transcripts
        ],
    }

    manifest_path = target_kb_dir / "fangtutu_manifest.json"
    chunks_path = target_kb_dir / "fangtutu_chunks.jsonl"
    index_path = target_kb_dir / "fangtutu_index.sqlite"
    manual_path = write_manual(root)

    write_json(manifest_path, manifest)
    write_jsonl(chunks_path, chunks)
    fts_available = build_sqlite_index(index_path, chunks)

    result = {
        "project_root": str(root),
        "kb_dir": str(target_kb_dir),
        "manual_path": relpath(manual_path, root),
        "manifest_path": relpath(manifest_path, root),
        "chunks_path": relpath(chunks_path, root),
        "index_path": relpath(index_path, root),
        "source_file_count": len(transcripts),
        "chunk_count": len(chunks),
        "fts_available": fts_available,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the local Fangtutu transcript knowledge base.")
    parser.add_argument("--project-root", type=Path, default=None, help="Repository root. Defaults to this script's repo.")
    parser.add_argument("--kb-dir", type=Path, default=None, help="Knowledge output directory.")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args()

    result = build_kb(project_root=args.project_root, kb_dir=args.kb_dir)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            "Fangtutu KB built: "
            f"{result['source_file_count']} source files, {result['chunk_count']} chunks, "
            f"FTS={'on' if result['fts_available'] else 'off'}"
        )
        print(f"Manifest: {result['manifest_path']}")
        print(f"Chunks:   {result['chunks_path']}")
        print(f"Manual:   {result['manual_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
