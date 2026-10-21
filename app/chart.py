# -*- coding: utf-8 -*-
"""图表推荐：根据结果集形状规则化地选择图表类型。

放在后端用规则实现（而不是再调用一次大模型），原因：
  - 省掉一次 ~0.6s 的模型往返，是"3 秒响应"指标的重要保障；
  - 规则对"维度 + 指标"这种结构化结果判断非常稳定，不依赖模型随机性。
"""

from __future__ import annotations

import re

# 时间维度识别：2024 / 2024-05 / 2024-05-12 / 2024年5月 / 第1季度
_TIME_RE = re.compile(
    r"^\s*("
    r"\d{4}"  # 年
    r"|\d{4}[-/年]\d{1,2}"  # 年-月
    r"|\d{4}[-/年]\d{1,2}[-/月]\d{1,2}"  # 年-月-日
    r"|第?[一二三四1-4]\s*季度"
    r")"
)

_PIE_HINTS = ("占比", "比例", "构成", "分布", "份额", "结构", "比重")
_PIE_MAX_SLICES = 8
_MAX_ROWS = 60


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_time_like(values: list) -> bool:
    strs = [str(v) for v in values if v is not None]
    if not strs:
        return False
    return sum(1 for s in strs if _TIME_RE.match(s)) >= max(1, int(len(strs) * 0.8))


def recommend(question: str, columns: list[str], rows: list[list]) -> dict | None:
    """返回图表配置，或 None 表示不适合出图。"""
    if len(columns) < 2 or len(rows) < 2 or len(rows) > _MAX_ROWS:
        return None

    # 判断每列是否为数值列
    numeric_flags = []
    for idx in range(len(columns)):
        vals = [r[idx] for r in rows if r[idx] is not None]
        numeric_flags.append(bool(vals) and all(_is_number(v) for v in vals))

    if not any(numeric_flags):
        return None

    dim_idx = next((i for i, flag in enumerate(numeric_flags) if not flag), None)
    if dim_idx is None:
        return None

    measures = [i for i, flag in enumerate(numeric_flags) if flag]
    x_col = columns[dim_idx]
    y_cols = [columns[i] for i in measures[:2]]
    dim_values = [r[dim_idx] for r in rows]

    if _is_time_like(dim_values):
        chart_type = "line"
    elif (
        len(measures) == 1
        and len(rows) <= _PIE_MAX_SLICES
        and any(h in question for h in _PIE_HINTS)
    ):
        chart_type = "pie"
    elif len(measures) >= 2:
        chart_type = "bar_line"
    else:
        chart_type = "bar"

    unit = (
        "元" if any(("额" in c or "金额" in c or "销售额" in c) for c in y_cols) else ""
    )
    return {
        "type": chart_type,
        "x": x_col,
        "y": y_cols,
        "unit": unit,
        "title": question.strip().rstrip("？?")[:40],
    }
