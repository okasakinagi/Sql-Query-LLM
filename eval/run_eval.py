# -*- coding: utf-8 -*-
"""Text-to-SQL 准确率评测。

方法：每条题目同时跑【参考答案 SQL】和【模型生成的 SQL】，在真实 MySQL 上执行后
比对结果集（不是比对 SQL 文本），这样才算客观的"执行准确率"。

    python eval/run_eval.py                 # 全量 30 题
    python eval/run_eval.py --limit 5       # 只跑前 5 题
    python eval/run_eval.py --ref-only      # 只校验参考答案 SQL 能否执行
    python eval/run_eval.py --ids 9,12,20   # 只跑指定题号
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from decimal import Decimal
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import service  # noqa: E402
from app import text2sql  # noqa: E402
from app.executor import execute  # noqa: E402

QUESTIONS = Path(__file__).resolve().parent / "questions.json"
OUT_DIR = ROOT / "output"


# ============================================================ 结果集归一化
def norm_value(v):
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, bool):
        return v
    if isinstance(v, float):
        return round(v, 2)
    if isinstance(v, int):
        return int(v)
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if v is None:
        return None
    return str(v).strip()


def norm_rows(rows: list[list]) -> list[tuple]:
    return sorted(tuple(norm_value(v) for v in r) for r in rows)


def close_value(a, b) -> bool:
    """数值容差比较：小的绝对容差 + 大的相对容差（覆盖浮点/四舍五入差异）。"""
    if a == b:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        diff = abs(float(a) - float(b))
        if diff <= 0.05:
            return True
        base = max(abs(float(a)), abs(float(b)), 1.0)
        return diff / base <= 0.005
    return False


def rows_close(a: list[tuple], b: list[tuple]) -> bool:
    if len(a) != len(b):
        return False
    for ra, rb in zip(a, b):
        if len(ra) != len(rb):
            return False
        for x, y in zip(ra, rb):
            if not close_value(x, y):
                return False
    return True


def project(rows: list[list], idx: list[int]) -> list[list]:
    return [[r[i] for i in idx] for r in rows]


def compare(expected: list[list], actual: list[list]) -> tuple[bool, bool]:
    """返回 (严格一致, 宽松一致)。"""
    exp, act = norm_rows(expected), norm_rows(actual)
    if exp == act:
        return True, True

    # 列数相同：带数值容差再比一次
    if expected and actual and len(expected[0]) == len(actual[0]):
        if rows_close(norm_rows(expected), norm_rows(actual)):
            return False, True

    # 列数不同：尝试从列多的一侧选出与另一侧等量的列子集（覆盖"多选了一列主键"的情况）
    if expected and actual:
        ne, na = len(expected[0]), len(actual[0])
        wider, narrower = (expected, actual) if ne > na else (actual, expected)
        k = min(ne, na)
        base = norm_rows(narrower)
        if k <= 5:
            for idx in combinations(range(len(wider[0])), k):
                if norm_rows(project(wider, list(idx))) == base:
                    return False, True
    return False, False


# ================================================================== 主流程
def run(ids: list[int] | None, limit: int | None, ref_only: bool) -> None:
    cases = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    if ids:
        cases = [c for c in cases if c["id"] in ids]
    if limit:
        cases = cases[:limit]

    results = []

    if ref_only:
        print("校验参考答案 SQL：")
        for c in cases:
            try:
                r = execute(c["sql"])
                print(f"  [OK]   题{c['id']:>2} {c['q'][:34]:<36} {r['row_count']} 行")
            except Exception as exc:  # noqa: BLE001
                print(f"  [FAIL] 题{c['id']:>2} {c['q'][:34]:<36} {exc}")
        return

    print("=" * 108)
    print("预热模型提示词缓存（与 Web 服务启动时做的是同一件事）…")
    t_warm = time.perf_counter()
    text2sql.warmup()
    print(f"预热完成，用时 {time.perf_counter() - t_warm:.2f}s\n")

    print("=" * 108)
    print(
        f"{'题号':<5}{'类型':<10}{'问题':<36}{'结果':<6}{'SQL耗时':>9}{'结果就绪':>10}{'行数':>7}"
    )
    print("-" * 108)

    for c in cases:
        try:
            expected = execute(c["sql"])["rows"]
        except Exception as exc:  # noqa: BLE001
            print(f"  [参考SQL错误] 题{c['id']}: {exc}")
            continue

        res = service.ask(c["q"])
        if res.get("ok"):
            strict, fuzzy = compare(expected, res["rows"])
        else:
            strict = fuzzy = False

        tag = "✅" if strict else ("≈" if fuzzy else "❌")
        print(
            f"{c['id']:<5}{c['type']:<10}{c['q'][:34]:<36}{tag:<6}"
            f"{res.get('timings', {}).get('SQL生成合计', 0):>8.2f}s"
            f"{res.get('result_elapsed', 0):>9.2f}s"
            f"{res.get('row_count', 0):>7}"
        )

        results.append(
            {
                "id": c["id"],
                "type": c["type"],
                "q": c["q"],
                "ref_sql": c["sql"],
                "gen_sql": res.get("sql", ""),
                "strict": strict,
                "fuzzy": fuzzy,
                "row_count": res.get("row_count", 0),
                "sql_time": res.get("timings", {}).get("SQL生成合计", 0),
                "result_elapsed": res.get("result_elapsed", 0),
                "elapsed": res.get("elapsed", 0),
                "error": res.get("error", ""),
                "attempts": len(res.get("steps", [])),
            }
        )

    # ---------------------------------------------------------- 统计
    n = len(results)
    strict_n = sum(1 for r in results if r["strict"])
    fuzzy_n = sum(1 for r in results if r["fuzzy"])
    within3 = sum(1 for r in results if r["result_elapsed"] <= 3.0)
    avg_sql = sum(r["sql_time"] for r in results) / n
    avg_res = sum(r["result_elapsed"] for r in results) / n
    avg_all = sum(r["elapsed"] for r in results) / n
    max_res = max(r["result_elapsed"] for r in results)
    retried = sum(1 for r in results if r["attempts"] > 1)

    print("=" * 108)
    print(
        f"严格准确率（结果集完全一致）      ：{strict_n}/{n} = {strict_n / n * 100:.1f}%"
    )
    print(
        f"宽松准确率（允许列多选/数值舍入）  ：{fuzzy_n}/{n} = {fuzzy_n / n * 100:.1f}%"
    )
    print(f"结果就绪平均耗时                  ：{avg_res:.2f}s（最慢 {max_res:.2f}s）")
    print(f"SQL 生成平均耗时                  ：{avg_sql:.2f}s")
    print(f"完整链路平均耗时                  ：{avg_all:.2f}s")
    print(
        f"满足 3 秒响应（结果就绪口径）      ：{within3}/{n} = {within3 / n * 100:.1f}%"
    )
    print(f"触发过自动重试的题数               ：{retried}")

    print("\n分类准确率：")
    types = sorted({r["type"] for r in results})
    for t in types:
        sub = [r for r in results if r["type"] == t]
        ok = sum(1 for r in sub if r["strict"])
        print(f"  {t:<12} {ok}/{len(sub)}")

    failed = [r for r in results if not r["fuzzy"]]
    if failed:
        print(f"\n未通过的题目（{len(failed)} 题）：")
        for r in failed:
            print(f"\n  ── 题{r['id']}（{r['type']}）{r['q']}")
            print(f"     生成：{r['gen_sql'][:220]}")
            if r["error"]:
                print(f"     错误：{r['error'][:220]}")

    # ---------------------------------------------------------- 落盘
    OUT_DIR.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    (OUT_DIR / f"评测明细_{stamp}.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = [
        "# Text-to-SQL 评测报告",
        "",
        f"- 评测时间：{dt.datetime.now():%Y-%m-%d %H:%M:%S}",
        f"- 题目数量：{n}",
        f"- **严格准确率：{strict_n}/{n} = {strict_n / n * 100:.1f}%**",
        f"- 宽松准确率：{fuzzy_n}/{n} = {fuzzy_n / n * 100:.1f}%",
        f"- 结果就绪平均耗时：{avg_res:.2f}s（最慢 {max_res:.2f}s）",
        f"- 满足 3 秒响应：{within3}/{n} = {within3 / n * 100:.1f}%",
        "",
        "## 分类准确率",
        "",
        "| 类型 | 正确/总数 |",
        "|---|---|",
    ]
    md += [
        f"| {t} | {sum(1 for r in results if r['type'] == t and r['strict'])}/"
        f"{sum(1 for r in results if r['type'] == t)} |"
        for t in types
    ]
    md += [
        "",
        "## 逐题结果",
        "",
        "| 题号 | 类型 | 问题 | 结果 | 行数 | SQL耗时 | 就绪耗时 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        tag = "✅" if r["strict"] else ("≈" if r["fuzzy"] else "❌")
        md.append(
            f"| {r['id']} | {r['type']} | {r['q']} | {tag} | {r['row_count']} | "
            f"{r['sql_time']:.2f}s | {r['result_elapsed']:.2f}s |"
        )
    (OUT_DIR / f"评测报告_{stamp}.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\n报告已保存：output/评测报告_{stamp}.md")


def main() -> None:
    ap = argparse.ArgumentParser(description="Text-to-SQL 准确率评测")
    ap.add_argument("--ids", type=str, default="", help="只跑指定题号，逗号分隔")
    ap.add_argument("--limit", type=int, default=None, help="只跑前 N 题")
    ap.add_argument("--ref-only", action="store_true", help="只校验参考答案 SQL")
    args = ap.parse_args()

    ids = [int(x) for x in args.ids.split(",") if x.strip()] if args.ids else None
    start = time.perf_counter()
    run(ids, args.limit, args.ref_only)
    print(f"\n评测总用时 {time.perf_counter() - start:.1f}s")


if __name__ == "__main__":
    main()
