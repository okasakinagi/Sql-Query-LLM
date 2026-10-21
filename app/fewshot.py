# -*- coding: utf-8 -*-
"""Few-shot 示例库。

7B 小模型靠"示例"学习业务口径的效果，远好于靠"规则描述"。
这里按"涉及的表"给每个示例打标签，运行时只挑选与当前问题相关的 3 条注入提示词，
既保证了准确率，又不会撑爆 8192 上下文。
"""

from __future__ import annotations

import re

EXAMPLES: list[dict] = [
    {
        "tables": {"departments", "employees"},
        "q": "每个部门各有多少名员工",
        "sql": (
            "SELECT d.department_name AS 部门, COUNT(e.employee_id) AS 人数\n"
            "FROM departments d\n"
            "LEFT JOIN employees e ON e.department_id = d.department_id\n"
            "GROUP BY d.department_id, d.department_name\n"
            "ORDER BY 人数 DESC"
        ),
    },
    {
        "tables": {"sales_orders"},
        "q": "2025 年每个月的销售额分别是多少",
        "sql": (
            "SELECT DATE_FORMAT(order_date, '%Y-%m') AS 月份,\n"
            "       ROUND(SUM(total_amount), 2) AS 销售额\n"
            "FROM sales_orders\n"
            "WHERE status <> '已取消' AND YEAR(order_date) = 2025\n"
            "GROUP BY 月份\n"
            "ORDER BY 月份"
        ),
    },
    {
        "tables": {"sales_order_items", "products", "sales_orders"},
        "q": "销量最高的前 5 个商品",
        "sql": (
            "SELECT p.product_name AS 商品名称, SUM(i.quantity) AS 销量\n"
            "FROM sales_order_items i\n"
            "JOIN sales_orders s ON i.so_id = s.so_id AND s.status <> '已取消'\n"
            "JOIN products p     ON i.product_id = p.product_id\n"
            "GROUP BY p.product_id, p.product_name\n"
            "ORDER BY 销量 DESC\n"
            "LIMIT 5"
        ),
    },
    {
        "tables": {"sales_order_items", "products", "categories", "sales_orders"},
        "q": "各大类（一级分类）的销售额占比",
        "sql": (
            "SELECT c1.category_name AS 一级分类,\n"
            "       ROUND(SUM(i.amount), 2) AS 销售额\n"
            "FROM sales_order_items i\n"
            "JOIN sales_orders s ON i.so_id = s.so_id AND s.status <> '已取消'\n"
            "JOIN products p     ON i.product_id = p.product_id\n"
            "JOIN categories c2  ON p.category_id = c2.category_id\n"
            "JOIN categories c1  ON c2.parent_id  = c1.category_id\n"
            "GROUP BY c1.category_id, c1.category_name\n"
            "ORDER BY 销售额 DESC"
        ),
    },
    {
        "tables": {"inventory", "products", "warehouses"},
        "q": "当前库存低于安全库存的商品有哪些",
        "sql": (
            "SELECT w.warehouse_name AS 仓库, p.product_name AS 商品,\n"
            "       i.quantity AS 当前库存, i.safety_stock AS 安全库存\n"
            "FROM inventory i\n"
            "JOIN products p   ON i.product_id = p.product_id\n"
            "JOIN warehouses w ON i.warehouse_id = w.warehouse_id\n"
            "WHERE i.quantity < i.safety_stock\n"
            "ORDER BY i.quantity ASC\n"
            "LIMIT 50"
        ),
    },
    {
        "tables": {"customers", "sales_orders"},
        "q": "哪些客户从来没有下过订单",
        "sql": (
            "SELECT c.customer_name AS 客户名称, c.city AS 城市\n"
            "FROM customers c\n"
            "WHERE NOT EXISTS (\n"
            "    SELECT 1 FROM sales_orders s WHERE s.customer_id = c.customer_id\n"
            ")\n"
            "ORDER BY c.customer_id"
        ),
    },
    {
        "tables": {"employees"},
        "q": "每个员工的直属上级叫什么名字",
        "sql": (
            "SELECT e.employee_name AS 员工, m.employee_name AS 直属上级\n"
            "FROM employees e\n"
            "LEFT JOIN employees m ON e.manager_id = m.employee_id"
        ),
    },
    {
        "tables": {"sales_orders", "customers"},
        "q": "按收货城市统计销售额前 10 名",
        "sql": (
            "SELECT s.city AS 城市,\n"
            "       COUNT(*) AS 订单数,\n"
            "       ROUND(SUM(s.total_amount), 2) AS 销售额\n"
            "FROM sales_orders s\n"
            "WHERE s.status <> '已取消'\n"
            "GROUP BY s.city\n"
            "ORDER BY 销售额 DESC\n"
            "LIMIT 10"
        ),
    },
    {
        "tables": {"sales_orders"},
        "q": "有多少笔订单还没有付款，涉及金额多少",
        "sql": (
            "SELECT COUNT(*) AS 订单数,\n"
            "       ROUND(SUM(total_amount), 2) AS 金额\n"
            "FROM sales_orders\n"
            "WHERE payment_status = '未付款'"
        ),
    },
    {
        "tables": {"purchase_orders", "suppliers"},
        "q": "采购金额最高的前 5 个供应商",
        "sql": (
            "SELECT s.supplier_name AS 供应商, ROUND(SUM(p.total_amount), 2) AS 采购额\n"
            "FROM purchase_orders p\n"
            "JOIN suppliers s ON p.supplier_id = s.supplier_id\n"
            "WHERE p.status <> '已取消'\n"
            "GROUP BY s.supplier_id, s.supplier_name\n"
            "ORDER BY 采购额 DESC\n"
            "LIMIT 5"
        ),
    },
    {
        "tables": {"products", "categories"},
        "q": "每个一级分类下商品的平均售价是多少",
        "sql": (
            "SELECT c1.category_name AS 一级分类,\n"
            "       ROUND(AVG(p.sale_price), 2) AS 平均售价\n"
            "FROM products p\n"
            "JOIN categories c2 ON p.category_id = c2.category_id\n"
            "JOIN categories c1 ON c2.parent_id  = c1.category_id\n"
            "GROUP BY c1.category_id, c1.category_name"
        ),
    },
    {
        "tables": {"sales_orders"},
        "q": "按订单状态统计各状态的订单笔数",
        "sql": (
            "SELECT status AS 状态, COUNT(*) AS 订单数\n"
            "FROM sales_orders\n"
            "GROUP BY status"
        ),
    },
]

# 每个示例的触发关键词（与 EXAMPLES 一一对应）。
# 选择示例时按“关键词命中 + 文本相似度”打分，把最贴题的示例送进提示词。
KEYWORDS: list[list[str]] = [
    ["部门", "员工", "人数", "多少人", "多少个", "几名"],
    ["每月", "每个月", "月份", "月度", "月销售", "趋势", "各月"],
    ["销量", "最高", "最多", "前", "排行", "排名", "热门"],
    ["分类", "大类", "一级", "二级", "类别", "占比"],
    ["库存", "安全库存", "缺货", "补货", "预警", "仓储"],
    ["没有", "从未", "从来没有", "下过", "未下"],
    ["上级", "经理", "汇报", "领导", "下属", "上级是谁"],
    ["城市", "地区", "地域", "省份", "收货"],
    ["付款", "未付款", "欠款", "应收", "支付", "已付"],
    ["供应商", "采购", "进货", "供货"],
    ["售价", "价格", "单价", "平均价", "定价"],
    ["状态", "各状态", "按状态", "审批"],
]

assert len(KEYWORDS) == len(EXAMPLES), "KEYWORDS 与 EXAMPLES 数量必须一致"


def _bigrams(text: str) -> set[str]:
    text = re.sub(r"\s+", "", text)
    return {text[i : i + 2] for i in range(len(text) - 1)} or {text}


def _similarity(a: str, b: str) -> float:
    """字符二元组 Jaccard 相似度，用于关键词未能命中时的兑底。"""
    A, B = _bigrams(a), _bigrams(b)
    return len(A & B) / max(len(A | B), 1)


def select(question: str, k: int = 3) -> list[dict]:
    """挑选与当前问题最相关的 k 条示例。

    注意：不能按“表重合度”选（全库表都是同一批，重合度分不开），
    要用问题文本本身的关键词与相似度来判断。
    """
    q = (question or "").lower()
    scored = []
    for i, ex in enumerate(EXAMPLES):
        hits = 0.0
        for kw in KEYWORDS[i]:
            if kw.lower() in q:
                hits += 1.0 + 0.5 * (len(kw) - 1)  # 长关键词更有区分度
        score = hits + 1.5 * _similarity(question or "", ex["q"])
        scored.append((score, -i, ex))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [ex for _, _, ex in scored[:k]]


def format_examples(examples: list[dict]) -> str:
    blocks = []
    for ex in examples:
        blocks.append(f"问题：{ex['q']}\nSQL：\n{ex['sql']}")
    return "\n\n".join(blocks)
