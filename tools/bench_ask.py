# -*- coding: utf-8 -*-
"""响应耗时基准：连续提问，观察前缀缓存命中后的稳定耗时。

python tools/bench_ask.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import service  # noqa: E402

QUESTIONS = [
    "各部门有多少人",
    "2025年每个月的销售额是多少",
    "销量最高的前5个商品是哪些",
    "上海仓的库存低于安全库存的商品有多少个",
    "哪些客户从来没有下过订单",
]


def main() -> None:
    print("=" * 104)
    print(
        f"{'#':<3}{'问题':<30}{'SQL生成':>9}{'结果就绪':>10}{'完整答案':>10}"
        f"{'总生成tok':>10}  {'≤3s':>5}"
    )
    print("-" * 104)

    sql_times, result_times, total_times = [], [], []
    for i, q in enumerate(QUESTIONS, 1):
        res = service.ask(q)
        t = res.get("timings", {})
        sql_t = t.get("SQL生成合计", 0)
        ans_t = t.get("生成答案", 0)
        res_t = res.get("result_elapsed", 0)
        tot_t = res.get("elapsed", 0)
        sql_times.append(sql_t)
        result_times.append(res_t)
        total_times.append(tot_t)
        flag = "✅" if res.get("within_3s") else "❌"
        print(
            f"{i:<3}{q[:28]:<30}{sql_t:>8.2f}s{res_t:>9.2f}s{tot_t:>9.2f}s"
            f"{sql_t + ans_t:>9.2f}s  {flag:>5}"
        )

    n = len(QUESTIONS)
    print("-" * 104)
    print(
        f"{'平均':<33}{sum(sql_times) / n:>8.2f}s{sum(result_times) / n:>9.2f}s"
        f"{sum(total_times) / n:>9.2f}s"
    )
    print(
        f"{'最慢':<33}{max(sql_times):>8.2f}s{max(result_times):>9.2f}s"
        f"{max(total_times):>9.2f}s"
    )
    print()
    print("说明：")
    print("  SQL生成  = 生成 SQL 的模型耗时（含重试）")
    print("  结果就绪  = 提问 → SQL + 数据 + 图表 全部就绪（用户能看到结果的时刻）")
    print("  完整答案  = 提问 → 连 AI 文字解读也生成完毕")
    print("  ≤3s      = 以“结果就绪”口径判定是否满足 3 秒响应要求")
    print()
    print("提示：第一条会因为提示词前缀缓存未命中而明显偏慢（冷启动），属于正常现象。")


if __name__ == "__main__":
    start = time.perf_counter()
    main()
    print(f"本次基准总用时 {time.perf_counter() - start:.1f}s")
