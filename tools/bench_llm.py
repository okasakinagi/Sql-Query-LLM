# -*- coding: utf-8 -*-
"""模型性能基准：定位响应耗时瓶颈。

python tools/bench_llm.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from app.fewshot import format_examples, select  # noqa: E402
from app.schema import format_ddl, get_schema  # noqa: E402
from config import LLM_BASE_URL, LLM_MODEL  # noqa: E402


def call(messages, max_tokens=200, label=""):
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": False,
    }
    start = time.perf_counter()
    resp = requests.post(f"{LLM_BASE_URL}/chat/completions", json=payload, timeout=180)
    elapsed = time.perf_counter() - start
    usage = resp.json().get("usage", {})
    pt = usage.get("prompt_tokens", 0)
    ct = usage.get("completion_tokens", 0)
    print(
        f"  {label:<34} {elapsed:6.2f}s   prompt={pt:>5}tok  "
        f"生成={ct:>4}tok  解码={ct / elapsed if elapsed else 0:5.1f} tok/s  "
        f"预处理={pt / elapsed if elapsed else 0:6.1f} tok/s"
    )
    return elapsed


def main() -> None:
    print("=" * 100)
    print("① 短提示词（重复两次，看前缀缓存效果）")
    short = [{"role": "user", "content": "写一条 SQL：统计每个部门的员工人数。"}]
    call(short, 120, "第 1 次（冷）")
    call(short, 120, "第 2 次（应命中缓存）")

    print("=" * 100)
    print("② 真实场景提示词（选表后的 DDL + 3 条示例）")
    schema = get_schema()
    picked = ["sales_orders", "sales_order_items", "products"]
    ddl = format_ddl(schema, picked)
    ex = format_examples(select("每个月的销售额", k=3))
    system = (
        "你是一名资深的 MySQL 数据库工程师。\n\n【表结构】\n"
        + ddl
        + "\n\n【示例】\n"
        + ex
        + "\n\n只输出 SQL。"
    )
    print(f"  （提示词长度：DDL {len(ddl)} 字符，示例 {len(ex)} 字符）")
    real = [
        {"role": "system", "content": system},
        {"role": "user", "content": "2025 年每个月的销售额是多少"},
    ]
    call(real, 300, "第 1 次（冷）")
    call(real, 300, "第 2 次（应命中缓存）")
    call(real, 300, "第 3 次（应命中缓存）")

    print("=" * 100)
    print("③ 示例数量对提示词长度的影响（3 条 vs 1 条）")
    for k in (1, 2, 3):
        d = len(format_ddl(schema, picked)) + len(format_examples(select("x", k=k)))
        print(f"  {k} 条示例 -> 提示词约 {d} 字符（≈{d // 3.5:.0f} tokens）")
    print()


if __name__ == "__main__":
    main()
