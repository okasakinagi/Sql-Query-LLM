# -*- coding: utf-8 -*-
"""Text-to-SQL 核心引擎。

完整闭环（自然语言 → SQL）：

    ① 固定前缀   角色 + 业务口径 + 全库紧凑 DDL 放在提示词最前面且内容恒定
    ② 示例注入   按问题相关度挑选 3 条示例，拼在固定前缀之后
    ③ 生成 SQL   temperature=0 保证稳定可复现
    ④ 抽取清洗   剥离 markdown 代码块与解释文字（sqlguard.extract_sql）
    ⑤ 安全校验   只读白名单 + 危险关键字黑名单
    ⑥ 试执行     EXPLAIN 预检语法与字段，失败把数据库报错回喂模型自动重试
    ⑦ 返回       附带每一步耗时，便于验证"3 秒响应"指标

【为什么这样设计】
本机解码速度约 35 token/s，是响应耗时的唯一瓶颈，因此：
  - 恒定内容放提示词最前面 → llama.cpp 前缀缓存可完整命中，连续提问时
    前处理耗时几乎为 0，只有新生成的 token 才耗时；
  - 紧凑 DDL 替代详细 DDL，前缀长度降到约 40%；
  - 严格限制输出长度：SQL 只输出语句本身，答案限制在 60 字以内。
"""

from __future__ import annotations

import time

from app import fewshot, llm, sqlguard
from app.executor import explain_ok
from app.schema import get_schema, schema_text
from config import MAX_RETRY

# ------------------------------------------------------------------ 固定前缀
SYSTEM_HEAD = """你是资深 MySQL 数据库工程师，负责把用户的自然语言问题翻译成一条**可直接执行的 MySQL 查询**。

【业务口径（必须遵守）】
1. 销售类统计（销售额、销量、订单数、客户消费额、业务员业绩、城市销售额等）默认排除已取消订单，必须写 `sales_orders.status <> '已取消'`；仅当用户明确要求统计取消订单时才不排除。
2. 采购类统计（采购金额、采购量、供应商采购额等）默认排除已取消采购单，必须写 `purchase_orders.status <> '已取消'`。
3. 销售金额用 `sales_order_items.amount`（已含折扣）汇总；订单总额用 `sales_orders.total_amount`。
4. 采购金额用 `purchase_order_items.amount` 汇总；采购总额用 `purchase_orders.total_amount`。
5. 商品分类为二级结构：`categories.parent_id` 指向一级分类，"大类/一级分类"需对 categories 自连接一次。
6. 按月分组统一写 `DATE_FORMAT(order_date, '%Y-%m')`；按年用 `YEAR(order_date)`。
7. 金额汇总一律用 `ROUND(..., 2)`。
8. 员工上下级：`employees.manager_id` → `employees.employee_id`（自连接），总经理 manager_id 为 NULL。
9. 客户与订单通过 `sales_orders.customer_id` 关联；库存通过 `inventory.product_id`、`inventory.warehouse_id` 关联。

【数据库表结构】
{schema}

【输出要求】
- 只输出一条 SELECT 语句本身，不要任何解释、不要 Markdown 代码块、不要输出分号。
- 只连接问题真正需要的表：问题只涉及主数据（商品、客户、员工、供应商、仓库）时，不要引入订单表。
- 当统计销售金额/销量/订单数时，必须带上 `sales_orders.status <> '已取消'`；统计采购金额/数量时，必须带上 `purchase_orders.status <> '已取消'`。
- 问题中出现的时间、城市、状态、岗位等筛选条件必须全部落到 WHERE 中，一个都不能遗漏。
- SELECT 的列严格按问题要求：不多选（不要擅自加 id、岗位等未被问及的列），也不少选。
- 选择字段时以**列注释的业务含义**为准，并遵循映射：「状态 / 审批状态 / 订单状态」→ 列名含 `status`；「类型 / 分类 / 费用类型」→ 列名含 `category` 或 `type`。二者不可混用，也不要把 `category` 的取值当作「状态」输出。
- 字段别名用简短中文（不超过 4 个字），例如 `AS 部门`、`AS 销售额`。
- 表连接必须写全 ON 条件；多表查询中重名列必须用表别名限定。
- 查询明细结果时默认加 `LIMIT 50`，除非用户要求全部或需要聚合。

【参考示例】
{examples}
"""


# ------------------------------------------------------------------ 主流程
def translate(question: str, verbose: bool = False) -> dict:
    """自然语言 → SQL（含自动重试），返回结构化结果。"""
    schema = get_schema()

    # ① 固定前缀：结构文档取自 schema/<库名>.md，内容恒定，可被前缀缓存完整命中
    # ② 相关示例拼在固定前缀之后，既提升准确率又不破坏缓存
    system = _build_system_prompt(question)
    examples = fewshot.select(question, k=3)

    timings: dict[str, float] = {}
    steps: list[dict] = []
    sql, last_error = "", ""

    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]

    t0 = time.perf_counter()
    for attempt in range(MAX_RETRY + 1):
        meta = llm.chat_ex(messages, max_tokens=300)
        raw = meta["text"]
        timings[f"生成SQL(第{attempt + 1}次)"] = round(meta["elapsed"], 3)

        try:
            candidate = sqlguard.validate(sqlguard.extract_sql(raw))
        except sqlguard.UnsafeSQLError as exc:
            last_error = str(exc)
            steps.append(
                {
                    "attempt": attempt + 1,
                    "raw": raw[:400],
                    "sql": "",
                    "error": last_error,
                }
            )
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": question},
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": f"你的回答不合法：{last_error}\n请重新只输出一条只读的 SELECT 语句。",
                },
            ]
            continue

        ok, err = explain_ok(candidate)
        if ok:
            sql = candidate
            steps.append(
                {
                    "attempt": attempt + 1,
                    "raw": raw[:400],
                    "sql": candidate,
                    "error": "",
                }
            )
            break

        last_error = err
        steps.append(
            {"attempt": attempt + 1, "raw": raw[:400], "sql": candidate, "error": err}
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
            {"role": "assistant", "content": candidate},
            {
                "role": "user",
                "content": "上面的 SQL 在 MySQL 上执行失败：" + err + "\n"
                "请检查表名、字段名与关联条件，重新只输出一条正确的 SELECT 语句。",
            },
        ]

    timings["SQL生成合计"] = round(time.perf_counter() - t0, 3)

    result = {
        "question": question,
        "sql": sql,
        "tables": list(schema),
        "examples": [e["q"] for e in examples],
        "steps": steps,
        "timings": timings,
        "messages": messages,  # 供答案生成续用同一上下文，命中前缀缓存
    }
    if not sql:
        result["error"] = f"生成 SQL 失败：{last_error}"
    if verbose:
        result["prompt"] = system
    return result


def _build_system_prompt(question: str = "") -> str:
    """构造完整的系统提示词（固定前缀 + 相关示例）。"""
    prefix, suffix = SYSTEM_HEAD.format(
        schema=schema_text(), examples="{EXAMPLES}"
    ).split("{EXAMPLES}")
    examples = fewshot.select(question, k=3)
    return prefix + fewshot.format_examples(examples) + suffix


def build_prompt(question: str = "") -> str:
    """公开接口：返回最终发给模型的完整系统提示词（供调试与导出快照）。"""
    return _build_system_prompt(question)


def warmup() -> bool:
    """预热：把固定的系统提示词先送进模型一次，让前缀缓存就位。

    这样用户打开页面后的第一个问题也能命中缓存，不会因为是“冷启动”
    而多花 2 秒左右的提示词预处理时间。只生成 1 个 token，代价极小。
    """
    try:
        llm.chat_ex(
            [
                {"role": "system", "content": _build_system_prompt()},
                {"role": "user", "content": "预热"},
            ],
            max_tokens=1,
        )
        return True
    except Exception:  # noqa: BLE001
        return False
