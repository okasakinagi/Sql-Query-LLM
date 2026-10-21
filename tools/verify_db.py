# -*- coding: utf-8 -*-
"""示例库数据质量自检：	行数、外键完整性、数据分布、时间跨度、异常值。

python tools/verify_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db as dbm  # noqa: E402

CHECKS: list[tuple[str, str]] = [
    # ---------------- 行数概览 ----------------
    (
        "各表行数",
        """
        SELECT '员工' AS 表, COUNT(*) AS 行数 FROM employees
        UNION ALL SELECT '客户', COUNT(*) FROM customers
        UNION ALL SELECT '商品', COUNT(*) FROM products
        UNION ALL SELECT '供应商', COUNT(*) FROM suppliers
        UNION ALL SELECT '销售单', COUNT(*) FROM sales_orders
        UNION ALL SELECT '销售明细', COUNT(*) FROM sales_order_items
        UNION ALL SELECT '采购单', COUNT(*) FROM purchase_orders
        UNION ALL SELECT '采购明细', COUNT(*) FROM purchase_order_items
        UNION ALL SELECT '库存', COUNT(*) FROM inventory
    """,
    ),
    # ---------------- 外键完整性（应全部为 0）----------------
    (
        "外键完整性检查（期望全为 0）",
        """
        SELECT '员工->部门无匹配' AS 检查项, COUNT(*) AS 异常行数
          FROM employees e LEFT JOIN departments d ON e.department_id = d.department_id
         WHERE d.department_id IS NULL
        UNION ALL
        SELECT '员工->上级无匹配', COUNT(*)
          FROM employees e LEFT JOIN employees m ON e.manager_id = m.employee_id
         WHERE e.manager_id IS NOT NULL AND m.employee_id IS NULL
        UNION ALL
        SELECT '商品->分类无匹配', COUNT(*)
          FROM products p LEFT JOIN categories c ON p.category_id = c.category_id
         WHERE c.category_id IS NULL
        UNION ALL
        SELECT '销售单->客户无匹配', COUNT(*)
          FROM sales_orders s LEFT JOIN customers c ON s.customer_id = c.customer_id
         WHERE c.customer_id IS NULL
        UNION ALL
        SELECT '销售明细->订单无匹配', COUNT(*)
          FROM sales_order_items i LEFT JOIN sales_orders s ON i.so_id = s.so_id
         WHERE s.so_id IS NULL
        UNION ALL
        SELECT '采购明细->订单无匹配', COUNT(*)
          FROM purchase_order_items i LEFT JOIN purchase_orders p ON i.po_id = p.po_id
         WHERE p.po_id IS NULL
        UNION ALL
        SELECT '库存->商品无匹配', COUNT(*)
          FROM inventory i LEFT JOIN products p ON i.product_id = p.product_id
         WHERE p.product_id IS NULL
    """,
    ),
    # ---------------- 组织架构 ----------------
    (
        "组织架构（部门 + 人数 + 负责人）",
        """
        SELECT d.department_name AS 部门,
               COUNT(e.employee_id) AS 人数,
               COALESCE((
                   SELECT GROUP_CONCAT(x.employee_name ORDER BY x.employee_id SEPARATOR ' / ')
                     FROM employees x
                    WHERE x.department_id = d.department_id
                      AND (x.employee_id IN (
                               SELECT y.manager_id FROM employees y
                                WHERE y.manager_id IS NOT NULL
                                  AND y.department_id = d.department_id)
                           OR NOT EXISTS (
                               SELECT 1 FROM employees z
                                WHERE z.department_id = d.department_id
                                  AND z.manager_id IS NOT NULL))
               ), '-') AS 负责人
          FROM departments d
          LEFT JOIN employees e ON e.department_id = d.department_id
         GROUP BY d.department_id, d.department_name
         ORDER BY d.department_id
    """,
    ),
    # ---------------- 时间跨度 ----------------
    (
        "销售数据时间跨度",
        """
        SELECT MIN(order_date) AS 最早, MAX(order_date) AS 最晚,
               COUNT(DISTINCT DATE_FORMAT(order_date, '%Y-%m')) AS 覆盖月份数
          FROM sales_orders
    """,
    ),
    (
        "销售单状态分布",
        """
        SELECT status AS 状态, COUNT(*) AS 单数,
               ROUND(SUM(total_amount), 2) AS 金额合计
          FROM sales_orders GROUP BY status ORDER BY 单数 DESC
    """,
    ),
    (
        "付款状态分布",
        """
        SELECT payment_status AS 付款状态, COUNT(*) AS 单数
          FROM sales_orders GROUP BY payment_status ORDER BY 单数 DESC
    """,
    ),
    # ---------------- 图表支撑力：月度趋势 ----------------
    (
        "月度销售额（排除已取消，最近 12 个月）",
        """
        SELECT DATE_FORMAT(order_date, '%Y-%m') AS 月份,
               COUNT(*) AS 订单数,
               ROUND(SUM(total_amount), 2) AS 销售额
          FROM sales_orders
         WHERE status <> '已取消'
         GROUP BY 月份 ORDER BY 月份 DESC LIMIT 12
    """,
    ),
    (
        "年度销售额对比（排除已取消）",
        """
        SELECT YEAR(order_date) AS 年度,
               COUNT(*) AS 订单数,
               ROUND(SUM(total_amount), 2) AS 销售额
          FROM sales_orders
         WHERE status <> '已取消'
         GROUP BY 年度 ORDER BY 年度
    """,
    ),
    (
        "一级分类销售 Top 10",
        """
        SELECT c1.category_name AS 一级分类,
               ROUND(SUM(i.amount), 2) AS 销售额,
               SUM(i.quantity) AS 销量
          FROM sales_order_items i
          JOIN sales_orders s ON i.so_id = s.so_id AND s.status <> '已取消'
          JOIN products p     ON i.product_id = p.product_id
          JOIN categories c2  ON p.category_id = c2.category_id
          JOIN categories c1  ON c2.parent_id = c1.category_id
         GROUP BY c1.category_id, c1.category_name
         ORDER BY 销售额 DESC
    """,
    ),
    (
        "客户城市分布 Top 10",
        """
        SELECT c.city AS 城市, COUNT(DISTINCT c.customer_id) AS 客户数,
               ROUND(SUM(s.total_amount), 2) AS 销售额
          FROM customers c
          JOIN sales_orders s ON s.customer_id = c.customer_id AND s.status <> '已取消'
         GROUP BY c.city ORDER BY 销售额 DESC LIMIT 10
    """,
    ),
    (
        "库存预警（低于安全库存）",
        """
        SELECT COUNT(*) AS 预警条数,
               SUM(CASE WHEN i.quantity = 0 THEN 1 ELSE 0 END) AS 零库存条数
          FROM inventory i WHERE i.quantity < i.safety_stock
    """,
    ),
    # ---------------- 异常值检查 ----------------
    (
        "异常值检查（期望全为 0）",
        """
        SELECT '销售明细金额<=0' AS 检查项, COUNT(*) AS 异常行数 FROM sales_order_items WHERE amount <= 0
        UNION ALL SELECT '销售单价<成本价', COUNT(*)
          FROM sales_order_items i JOIN products p ON i.product_id = p.product_id
         WHERE i.unit_price < p.cost_price
        UNION ALL SELECT '订单总额!=明细合计', COUNT(*) FROM (
            SELECT s.so_id FROM sales_orders s
            JOIN (SELECT so_id, ROUND(SUM(amount), 2) t FROM sales_order_items GROUP BY so_id) x
              ON x.so_id = s.so_id
           WHERE ABS(s.total_amount - x.t) > 0.01) z
        UNION ALL SELECT '采购单总额!=明细合计', COUNT(*) FROM (
            SELECT p.po_id FROM purchase_orders p
            JOIN (SELECT po_id, ROUND(SUM(amount), 2) t FROM purchase_order_items GROUP BY po_id) x
              ON x.po_id = p.po_id
           WHERE ABS(p.total_amount - x.t) > 0.01) z
        UNION ALL SELECT '在售商品无库存', COUNT(*)
          FROM products p WHERE p.status = '在售'
           AND NOT EXISTS (SELECT 1 FROM inventory i WHERE i.product_id = p.product_id)
        UNION ALL SELECT '客户无任何订单', COUNT(*)
          FROM customers c WHERE NOT EXISTS (
              SELECT 1 FROM sales_orders s WHERE s.customer_id = c.customer_id)
    """,
    ),
]


def main() -> None:
    conn = dbm.connect()
    try:
        with conn.cursor() as cur:
            for title, sql in CHECKS:
                cur.execute(sql)
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                print("=" * 78)
                print(f"▶ {title}")
                print("-" * 78)
                print("  " + " | ".join(f"{c}" for c in cols))
                for r in rows:
                    print(
                        "  "
                        + " | ".join(
                            (
                                "-"
                                if v is None
                                else (f"{v:,}" if isinstance(v, int) else str(v))
                            )
                            for v in r
                        )
                    )
                if not rows:
                    print("  （无数据）")
                print()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
