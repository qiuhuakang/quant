from __future__ import annotations
"""Retrieve Fangtutu context for agent-internal stock analysis prompts."""

import argparse
import json
import re
from pathlib import Path
from typing import Optional

try:
    from tools.build_fangtutu_kb import (
        DEFAULT_KB_DIR,
        DEFAULT_MANUAL_PATH,
        TOPIC_KEYWORDS,
        build_kb,
        resolve_project_root,
        summarize,
    )
except ModuleNotFoundError:  # Allows direct execution from the tools directory.
    from build_fangtutu_kb import (  # type: ignore
        DEFAULT_KB_DIR,
        DEFAULT_MANUAL_PATH,
        TOPIC_KEYWORDS,
        build_kb,
        resolve_project_root,
        summarize,
    )


DECISION_GRAPH_PATH = Path("docs") / "fangtutu" / "decision_graph.json"


def load_chunks(chunks_path: Path) -> list[dict]:
    chunks = []
    if not chunks_path.exists():
        return chunks
    with chunks_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def load_decision_graph(project_root: Path) -> list[dict]:
    graph_path = project_root / DECISION_GRAPH_PATH
    if not graph_path.exists():
        return []
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    rules = graph.get("rules", [])
    return rules if isinstance(rules, list) else []


def load_manual_summary(project_root: Path) -> str:
    manual_path = project_root / DEFAULT_MANUAL_PATH
    if not manual_path.exists():
        return "方土土框架强调：先判断市场环境，再看形态确认，最后定义风险和仓位。"
    text = manual_path.read_text(encoding="utf-8", errors="replace")
    sections = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and len(sections) < 8:
            sections.append(stripped[2:])
    if sections:
        return "；".join(sections)
    return summarize(text, limit=360)


def query_terms(question: str) -> list[str]:
    terms: list[str] = []
    question_lower = question.lower()

    for keywords in TOPIC_KEYWORDS.values():
        for keyword in keywords:
            if keyword.lower() in question_lower:
                terms.append(keyword)

    for token in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", question):
        if len(token) >= 2:
            terms.append(token)

    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(term)
    return deduped


def score_rule(rule: dict, question: str, matched_topics: list[str], snippets: list[dict]) -> float:
    question_text = question.lower()
    snippet_text = " ".join(snippet.get("summary", "") + " " + snippet.get("quote", "") for snippet in snippets).lower()
    score = 0.0

    for trigger in rule.get("triggers", []):
        trigger_text = str(trigger).lower()
        if trigger_text in question_text:
            score += 8.0
        elif trigger_text in snippet_text:
            score += 2.0

    for topic in rule.get("topics", []):
        if topic in matched_topics:
            score += 2.5

    for source_tag in rule.get("source_tags", []):
        source_text = str(source_tag).lower()
        if source_text in question_text:
            score += 1.5
        elif source_text in snippet_text:
            score += 0.5

    return score


def match_decision_rules(
    project_root: Path,
    question: str,
    matched_topics: list[str],
    snippets: list[dict],
    top_k: int = 4,
) -> list[dict]:
    scored = []
    for rule in load_decision_graph(project_root):
        score = score_rule(rule, question, matched_topics, snippets)
        if score > 0:
            cleaned = {
                "id": rule.get("id", ""),
                "title": rule.get("title", ""),
                "condition": rule.get("condition", ""),
                "implies": rule.get("implies", []),
                "risk_actions": rule.get("risk_actions", []),
                "source_tags": rule.get("source_tags", []),
                "relevance": round(score, 3),
            }
            scored.append((score, cleaned))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [rule for _score, rule in scored[:top_k]]


def detect_query_topics(question: str) -> list[str]:
    question_lower = question.lower()
    topics = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword.lower() in question_lower for keyword in keywords):
            topics.append(topic)
    return topics


def score_chunk(chunk: dict, terms: list[str], query_topics: list[str]) -> float:
    text = f"{chunk.get('summary', '')} {chunk.get('text', '')}".lower()
    topics = set(chunk.get("topics", []))
    score = 0.0

    for term in terms:
        term_lower = term.lower()
        if term_lower in text:
            score += 4.0 if len(term) >= 4 else 2.0
            score += min(text.count(term_lower), 4) * 0.5

    for topic in query_topics:
        if topic in topics:
            score += 3.0

    if not terms and topics:
        score += 0.1
    return score


def best_quote(text: str, terms: list[str], limit: int = 160) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return ""

    lower = clean.lower()
    positions = [lower.find(term.lower()) for term in terms if lower.find(term.lower()) >= 0]
    if not positions:
        return summarize(clean, limit=limit)

    center = min(positions)
    start = max(0, center - limit // 3)
    end = min(len(clean), start + limit)
    excerpt = clean[start:end]
    if start > 0:
        excerpt = "…" + excerpt
    if end < len(clean):
        excerpt += "…"
    return excerpt


def answer_guidance(matched_topics: list[str]) -> list[str]:
    guidance = [
        "先判断当前是趋势、震荡、突破还是失败突破。",
        "把结论写成条件判断，不要给无条件买卖指令。",
        "最后必须说明无效条件、止损和仓位风险。",
    ]
    topic_guidance = {
        "EMA20": "如果价格在 EMA20 附近反应，重点看信号K和后续 follow-through。",
        "突破确认": "突破后没有持续跟随时，要防止假突破或回到震荡区间。",
        "仓位管理": "宽止损或不确定性高时，必须降低仓位，避免重仓和急着加仓。",
        "风险控制": "入场前先定义止损位置和这笔交易错了的条件。",
        "楔形": "三推/楔形后的第一次反转在强趋势中可能失败，需要确认。",
        "Measure Move": "目标位只是参考，达到过程中的反向信号需要重新评估。",
        "实战复盘": "实战片段优先用于盘中处理：突然的 Bull/Bear Surprise、特殊事件、利润保护和震荡化判断。",
    }
    for topic in matched_topics:
        item = topic_guidance.get(topic)
        if item and item not in guidance:
            guidance.append(item)
    return guidance


def rank_chunks(chunks: list[dict], question: str, top_k: int) -> tuple[list[dict], list[str]]:
    terms = query_terms(question)
    query_topics = detect_query_topics(question)
    scored = []
    for chunk in chunks:
        score = score_chunk(chunk, terms, query_topics)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [chunk for _score, chunk in scored[:top_k]]

    matched_topics = list(query_topics)
    for chunk in selected:
        for topic in chunk.get("topics", []):
            if topic not in matched_topics:
                matched_topics.append(topic)
    return selected, matched_topics[:8]


def ensure_kb(project_root: Path) -> None:
    chunks_path = project_root / DEFAULT_KB_DIR / "fangtutu_chunks.jsonl"
    manual_path = project_root / DEFAULT_MANUAL_PATH
    if not chunks_path.exists() or not manual_path.exists():
        build_kb(project_root=project_root)


def get_context(question: str, project_root: Optional[Path] = None, top_k: int = 6) -> dict:
    root = resolve_project_root(project_root)
    ensure_kb(root)

    chunks_path = root / DEFAULT_KB_DIR / "fangtutu_chunks.jsonl"
    chunks = load_chunks(chunks_path)
    selected, matched_topics = rank_chunks(chunks, question, top_k=top_k)
    terms = query_terms(question)

    snippets = [
        {
            "source": chunk["source"],
            "chunk_id": chunk["id"],
            "topics": chunk.get("topics", []),
            "summary": chunk.get("summary", ""),
            "quote": best_quote(chunk.get("text", ""), terms),
            "relevance": round(score_chunk(chunk, terms, matched_topics), 3),
        }
        for chunk in selected
    ]

    decision_rules = match_decision_rules(root, question, matched_topics, snippets)

    return {
        "question": question,
        "manual_summary": load_manual_summary(root),
        "matched_topics": matched_topics,
        "snippets": snippets,
        "decision_rules": decision_rules,
        "answer_guidance": answer_guidance(matched_topics),
        "usage": "Agent should use this context internally, then answer naturally in Chinese.",
    }


def format_markdown(context: dict) -> str:
    lines = [
        "# Fangtutu Context",
        "",
        f"Question: {context['question']}",
        "",
        "## Manual Summary",
        context["manual_summary"],
        "",
        "## Matched Topics",
        ", ".join(context["matched_topics"]) or "无明确主题",
        "",
        "## Snippets",
    ]
    for snippet in context["snippets"]:
        lines.extend(
            [
                f"- Source: `{snippet['source']}` / `{snippet['chunk_id']}`",
                f"  Topics: {', '.join(snippet['topics'])}",
                f"  Summary: {snippet['summary']}",
                f"  Quote: {snippet['quote']}",
            ]
        )
    lines.extend(["", "## Decision Rules"])
    for rule in context.get("decision_rules", []):
        lines.extend(
            [
                f"- `{rule['id']}`: {rule['title']}",
                f"  Condition: {rule['condition']}",
                f"  Implies: {'; '.join(rule['implies'])}",
                f"  Risk Actions: {'; '.join(rule['risk_actions'])}",
            ]
        )
    lines.extend(["", "## Answer Guidance"])
    lines.extend(f"- {item}" for item in context["answer_guidance"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Return Fangtutu context for an agent answer.")
    parser.add_argument("--question", required=True, help="User question to retrieve context for.")
    parser.add_argument("--project-root", type=Path, default=None, help="Repository root.")
    parser.add_argument("--top-k", type=int, default=6, help="Number of snippets to return.")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()

    context = get_context(args.question, project_root=args.project_root, top_k=args.top_k)
    if args.format == "json":
        print(json.dumps(context, ensure_ascii=False, indent=2))
    else:
        print(format_markdown(context), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
