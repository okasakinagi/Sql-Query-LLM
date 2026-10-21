# -*- coding: utf-8 -*-
"""业务编排：把各模块串成一条完整的问答链路。

问题 → 生成 SQL → 安全校验 → 执行 → 自然语言答案 → 图表建议
"""

from __future__ import annotations

import time

from app import answer as answer_mod
from app import chart, llm, text2sql
from app.executor import QueryError, execute
from app.schema import maybe_reload_schema


def ask(question: str) -> dict:
    """处理一次自然语言查询，返回前端所需的完整结果。"""
    question = (question or "").strip()
    if not question:
        return {"ok": False, "error": "请输入要查询的问题"}

    total_start = time.perf_counter()
    result: dict = {"ok": True, "question": question}

    # 结构变更感知：数据库新增表/字段/外键后，无需重启服务即可识别
    try:
        reload_info = maybe_reload_schema()
    except Exception:  # noqa: BLE001
        reload_info = {"changed": False}
    result["schema_reloaded"] = bool(reload_info.get("changed"))

    # ---------- 1. 生成 SQL ----------
    try:
        tr = text2sql.translate(question)
    except llm.LLMError as exc:
        return {"ok": False, "question": question, "error": str(exc)}

    result["sql"] = tr["sql"]
    result["tables"] = tr["tables"]
    result["steps"] = tr["steps"]
    result["timings"] = dict(tr["timings"])

    if not tr["sql"]:
        result["ok"] = False
        result["error"] = tr.get("error", "生成 SQL 失败")
        result["elapsed"] = round(time.perf_counter() - total_start, 3)
        return result

    # ---------- 2. 执行 SQL ----------
    try:
        data = execute(tr["sql"])
    except QueryError as exc:
        result["ok"] = False
        result["error"] = f"SQL 执行失败：{exc}"
        result["elapsed"] = round(time.perf_counter() - total_start, 3)
        return result

    result["columns"] = data["columns"]
    result["rows"] = data["rows"]
    result["row_count"] = data["row_count"]
    result["truncated"] = data["truncated"]
    result["timings"]["数据库执行"] = data["elapsed"]

    # ---------- 3. 自然语言答案 ----------
    result["result_elapsed"] = round(time.perf_counter() - total_start, 3)
    try:
        ans = answer_mod.summarize(
            tr["messages"],
            question,
            tr["sql"],
            data["columns"],
            data["rows"],
            data["row_count"],
        )
        result["answer"] = ans["answer"]
        result["timings"]["生成答案"] = ans["elapsed"]
    except llm.LLMError as exc:
        result["answer"] = "（模型服务异常，无法生成文字总结）"
        result["timings"]["生成答案"] = 0.0
        result["warnings"] = [str(exc)]

    # ---------- 4. 图表建议 ----------
    result["chart"] = chart.recommend(question, data["columns"], data["rows"])

    # ---------- 5. 耗时统计 ----------
    total = round(time.perf_counter() - total_start, 3)
    result["elapsed"] = total
    # “3 秒响应”指从提问到查询结果（SQL + 表格 + 图表）就绪的时间；
    # elapsed 是连 AI 文字解读也生成完的完整耗时，两者分别统计。
    result["within_3s"] = result.get("result_elapsed", total) <= 3.0
    result["full_within_3s"] = total <= 3.0
    return result
