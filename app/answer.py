# -*- coding: utf-8 -*-
"""结果解读：把 SQL 查询结果整理成自然语言答案。

性能设计：直接续用“生成 SQL”那一轮的对话上下文（system + 用户问题 + 助手 SQL），
两轮请求共享同一前缀，前缀缓存可以命中，只有新增的结果数据需要做前处理，
省掉一次完整的提示词预处理（约 0.3~0.9s）。同时把答案限制在 60 字以内，
把解码 token 数压到最低——本机解码速度约 35 token/s，输出长度直接决定耗时。
"""

from __future__ import annotations

from app import llm
from config import ANSWER_PREVIEW_ROWS


def _precomputed_stats(columns: list[str], rows: list[list]) -> list[str]:
    """在 Python 里把关键统计量算好，让模型只负责表达、不负责算术。

    7B 模型很容易在「求百分比」这类除法上出错（实测把 45.3% 说成了 25.85%），
    所以把合计、最大最小和各项占比直接算好塞给它。
    """
    if not rows:
        return []

    lines: list[str] = []
    for j, col in enumerate(columns):
        vals = [r[j] for r in rows if isinstance(r[j], (int, float))]
        if len(vals) != len(rows) or not vals:
            continue
        lines.append(
            f"{col}：合计 {sum(vals):,.2f}，最大 {max(vals):,.2f}，最小 {min(vals):,.2f}"
        )

    # 两列（维度 + 指标）时，直接把占比算好
    if len(columns) == 2 and len(rows) <= 15:
        vals = [rows[i][1] for i in range(len(rows))]
        if all(isinstance(v, (int, float)) for v in vals):
            total = sum(vals) or 1
            shares = "，".join(
                f"{rows[i][0]} {vals[i] / total * 100:.2f}%" for i in range(len(rows))
            )
            lines.append(f"各项占比（分母为合计）：{shares}")

    return lines


def build_followup(
    question: str, columns: list[str], rows: list[list], total_rows: int
) -> str:
    """构造第二轮的用户消息（结果数据 + 已算好的统计 + 作答要求）。"""
    preview = rows[:ANSWER_PREVIEW_ROWS]
    lines = [" | ".join(str(c) for c in columns)]
    lines += [" | ".join("" if v is None else str(v) for v in r) for r in preview]
    if total_rows > len(preview):
        more = f"\n（共 {total_rows} 行，上面是前 {len(preview)} 行）"
    else:
        more = f"\n（共 {total_rows} 行）"

    stats = _precomputed_stats(columns, preview)
    stats_block = (
        ("\n\n【后端已算好的统计（请直接引用，禁止自行计算）】\n" + "\n".join(stats))
        if stats
        else ""
    )

    return (
        f"【用户问题】{question}\n\n"
        f"【查询结果】\n"
        + "\n".join(lines)
        + more
        + stats_block
        + "\n\n【重要】这一次不要生成 SQL，请直接用不超过 60 字的中文给出结论；"
        "不要逐行罗列所有数据，只概括关键结论（最高/最低/合计/趋势）；"
        "涉及合计、占比等数值时，必须直接使用上面已算好的结果。"
    )


def summarize(
    messages: list[dict],
    question: str,
    sql: str,
    columns: list[str],
    rows: list[list],
    total_rows: int,
) -> dict:
    """续用 SQL 生成时的对话上下文，返回 {"answer", "elapsed"}。"""
    if not rows:
        return {
            "answer": "没有查询到符合条件的数据，可以尝试放宽筛选条件，"
            "或确认相关业务数据是否存在。",
            "elapsed": 0.0,
        }

    followup = build_followup(question, columns, rows, total_rows)
    meta = llm.chat_ex(
        list(messages)
        + [
            {"role": "assistant", "content": sql},
            {"role": "user", "content": followup},
        ],
        max_tokens=180,
    )
    return {"answer": meta["text"].strip(), "elapsed": round(meta["elapsed"], 3)}
