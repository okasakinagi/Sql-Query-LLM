# -*- coding: utf-8 -*-
"""模型服务自检：连通性 / 解码吞吐 / Text-to-SQL 粗测。

不需要 MySQL，只要能连上 OpenAI 兼容接口即可运行。

    python deploy/scripts/check_llm.py
    python deploy/scripts/check_llm.py --base-url http://127.0.0.1:11434/v1 --model qwen2.5-coder:7b

退出码：0 表示全部通过，1 表示有检查项失败。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TIMEOUT  # noqa: E402

# 三条典型问题，只检查模型能否产出结构合理的 SELECT（不涉及真实库）
SQL_PROBES = [
    (
        "单表聚合",
        "表 employees(id, name, department_id, salary)。"
        "问题：每个部门各有多少名员工？只输出一条 SQL。",
    ),
    (
        "多表 JOIN",
        "表 employees(id, name, department_id)、departments(id, name)。"
        "问题：每个部门的员工人数，按人数从高到低。只输出一条 SQL。",
    ),
    (
        "时间分组",
        "表 sales_orders(id, order_date, total_amount, status)。"
        "问题：2025 年每个月的销售额分别是多少？只输出一条 SQL。",
    ),
]


def call(base_url: str, model: str, messages: list[dict], max_tokens: int = 200) -> dict:
    resp = requests.post(
        f"{base_url}/chat/completions",
        json={
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0,
            "stream": False,
        },
        headers={"Authorization": f"Bearer {LLM_API_KEY}"},
        timeout=LLM_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    ap = argparse.ArgumentParser(description="LLM service self-check")
    ap.add_argument("--base-url", default=LLM_BASE_URL)
    ap.add_argument("--model", default=LLM_MODEL)
    args = ap.parse_args()

    base_url, model = args.base_url.rstrip("/"), args.model
    failures = 0

    print(f"base_url = {base_url}")
    print(f"model    = {model}")
    print("-" * 64)

    # 1. 服务是否在线
    try:
        r = requests.get(f"{base_url}/models", headers={"Authorization": f"Bearer {LLM_API_KEY}"}, timeout=5)
        print(f"[1] /v1/models        HTTP {r.status_code}")
        if r.status_code != 200:
            failures += 1
    except Exception as exc:  # noqa: BLE001
        print(f"[1] /v1/models        FAILED ({exc.__class__.__name__}) - is the server running?")
        return 1

    # 2. 单次对话 + 解码速度
    try:
        t0 = time.perf_counter()
        data = call(base_url, model, [{"role": "user", "content": "用一句话介绍你自己。"}], max_tokens=60)
        elapsed = time.perf_counter() - t0
        text = data["choices"][0]["message"]["content"].strip().replace("\n", " ")
        completion_tokens = (data.get("usage") or {}).get("completion_tokens")
        rate = f"{completion_tokens / elapsed:.1f} tokens/s" if completion_tokens and elapsed > 0 else "n/a"
        print(f"[2] chat completion   {elapsed:.2f}s, {rate}")
        print(f"    -> {text[:80]}")
    except Exception as exc:  # noqa: BLE001
        print(f"[2] chat completion   FAILED ({exc})")
        return 1

    # 3. Text-to-SQL 粗测
    for name, prompt in SQL_PROBES:
        try:
            t0 = time.perf_counter()
            data = call(base_url, model, [{"role": "user", "content": prompt}], max_tokens=160)
            elapsed = time.perf_counter() - t0
            sql = data["choices"][0]["message"]["content"].strip()
            one_line = " ".join(sql.split())
            ok = any(k in sql.upper() for k in ("SELECT", "WITH"))
            print(f"[3] {name:<12} {elapsed:.2f}s  {'OK ' if ok else 'BAD'}")
            print(f"    -> {one_line[:120]}")
            if not ok:
                failures += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[3] {name:<12} FAILED ({exc})")
            failures += 1

    print("-" * 64)
    if failures:
        print(f"FAILED: {failures} check(s) did not pass.")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
