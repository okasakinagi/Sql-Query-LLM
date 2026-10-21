# -*- coding: utf-8 -*-
"""命令行版问答，用于快速验证链路与排查问题。

python tools/ask.py "2025 年每个月的销售额是多少"
python tools/ask.py "各部门有多少人" --show-prompt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import service  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="命令行智能查询")
    ap.add_argument("question", help="自然语言问题")
    ap.add_argument("--rows", type=int, default=30, help="最多打印多少行结果")
    args = ap.parse_args()

    res = service.ask(args.question)

    print("=" * 78)
    print("问题：", res["question"])
    print("-" * 78)
    if res.get("sql"):
        print("生成的 SQL：")
        for line in res["sql"].split("\n"):
            print("   ", line)
    print("-" * 78)

    if not res.get("ok"):
        print("失败：", res.get("error"))
        for step in res.get("steps", []):
            print(f"  第 {step['attempt']} 次尝试错误：{step['error']}")
        return

    cols = res["columns"]
    print(
        f"结果（{res['row_count']} 行，数据库耗时 {res['timings'].get('数据库执行')}s）："
    )
    print("  " + " | ".join(str(c) for c in cols))
    for row in res["rows"][: args.rows]:
        print("  " + " | ".join("" if v is None else str(v) for v in row))
    if res["row_count"] > args.rows:
        print(f"  ...（其余 {res['row_count'] - args.rows} 行省略）")

    print("-" * 78)
    print("回答：", res.get("answer", ""))
    if res.get("chart"):
        c = res["chart"]
        print(f"图表：{c['type']}  x={c['x']}  y={c['y']}")
    print("-" * 78)
    print("耗时明细：", ", ".join(f"{k}={v}s" for k, v in res["timings"].items()))
    print(
        f"结果就绪（SQL+数据+图表）：{res.get('result_elapsed')}s  →  "
        f"{'✅ 满足 3 秒要求' if res.get('within_3s') else '⚠️ 超过 3 秒'}"
    )
    print(f"完整链路（含文字解读）    ：{res['elapsed']}s")


if __name__ == "__main__":
    main()
