# -*- coding: utf-8 -*-
"""验收「数据库结构变更自动感知」能力。

模拟真实场景：系统运行中，DBA 新建了一张 `expense_claims`（费用报销单）表并写入数据，
不重启服务，看系统能否自动识别并正确回答新表相关的问题。

    python tools/test_schema_change.py          # 跑完自动删表（干净）
    python tools/test_schema_change.py --keep   # 保留新表，用于演示

验证四件事：
    ① 新增表 -> 结构指纹变化被检测到
    ② 结构文档 schema/erp_demo.md 自动重建，包含新表与枚举取值
    ③ 模型能对新表生成正确 SQL 并返回结果
    ④ 删表后同样能被检测到（结构退回）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db as dbm  # noqa: E402
from app import service  # noqa: E402
from app.schema import maybe_reload_schema, schema_md_path  # noqa: E402

DDL = """
CREATE TABLE IF NOT EXISTS expense_claims (
    claim_id    INT AUTO_INCREMENT COMMENT '报销单ID',
    employee_id INT NOT NULL COMMENT '申请人（员工ID）',
    claim_date  DATE NOT NULL COMMENT '报销日期',
    category    VARCHAR(20) NOT NULL COMMENT '费用类型：差旅 / 招待 / 办公 / 交通',
    amount      DECIMAL(10, 2) NOT NULL COMMENT '报销金额（元）',
    status      VARCHAR(10) NOT NULL COMMENT '审批状态：待审批 / 已通过 / 已驳回',
    PRIMARY KEY (claim_id),
    KEY idx_claim_emp (employee_id),
    CONSTRAINT fk_claim_emp FOREIGN KEY (employee_id) REFERENCES employees (employee_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '费用报销单表'
"""

ROWS = [
    (1, "2026-07-03", "差旅", 3260.50, "已通过"),
    (3, "2026-07-08", "差旅", 1880.00, "已通过"),
    (8, "2026-07-12", "办公", 420.00, "已通过"),
    (12, "2026-07-15", "招待", 2600.00, "待审批"),
    (20, "2026-07-19", "交通", 380.50, "已通过"),
    (25, "2026-07-22", "差旅", 4120.00, "已通过"),
    (33, "2026-08-02", "招待", 5300.00, "已驳回"),
    (40, "2026-08-06", "办公", 260.00, "已通过"),
    (50, "2026-08-11", "差旅", 2350.00, "已通过"),
    (58, "2026-08-18", "交通", 155.00, "待审批"),
]


def run_sql(sql: str, params=None) -> None:
    conn = dbm.connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def exists() -> bool:
    conn = dbm.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES LIKE 'expense_claims'")
            return cur.fetchone() is not None
    finally:
        conn.close()


def check(ok: bool, text: str) -> bool:
    print(f"  {'✅' if ok else '❌'} {text}")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description="数据库结构变更感知验收")
    ap.add_argument("--keep", action="store_true", help="保留测试表用于演示")
    args = ap.parse_args()

    passed = []

    # ---------------------------------------------------------------- 建表
    print("=" * 78)
    print("【1】模拟 DBA 新增一张表 expense_claims（费用报销单）")
    maybe_reload_schema(force=True)  # 先加载变更前的基线结构
    if exists():
        run_sql("DROP TABLE expense_claims")
        maybe_reload_schema(force=True)
    run_sql(DDL)
    conn = dbm.connect()
    try:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO expense_claims (employee_id, claim_date, category, amount, status) "
                "VALUES (%s, %s, %s, %s, %s)",
                ROWS,
            )
        conn.commit()
    finally:
        conn.close()
    print(f"  已建表并写入 {len(ROWS)} 行数据")

    # ------------------------------------------------------- 检测结构变化
    print("\n【2】不重启服务，检查系统能否感知结构变化")
    info = maybe_reload_schema(force=True)
    passed.append(
        check(
            info.get("changed") is True,
            f"检测到结构变更（{info.get('old')} → {info.get('new')}）",
        )
    )

    md = schema_md_path().read_text(encoding="utf-8")
    lines = md.splitlines()
    idx = next(
        (i for i, l in enumerate(lines) if l.startswith("## expense_claims")), -1
    )
    table_line = lines[idx + 1] if idx >= 0 else ""
    has_status_enum = (
        "{" in table_line and "已通过" in table_line and "待审批" in table_line
    )
    has_category_enum = (
        "{" in table_line and "差旅" in table_line and "招待" in table_line
    )

    passed.append(check("expense_claims" in md, "结构文档已自动重建，包含新表"))
    passed.append(check("费用报销单表" in md, "新表的表注释已写入结构文档"))
    passed.append(check(has_status_enum, "status 列的真实枚举取值已自动采样并写入"))
    passed.append(check(has_category_enum, "category 列同样按通用规则被识别并采样"))
    passed.append(
        check("employee_id→employees.employee_id" in md, "新表外键关系已写入结构文档")
    )

    # --------------------------------------------------- 用新表回答问题
    print("\n【3】直接对新表提问（系统此前从未见过这张表）")
    for q, must in [
        ("费用类型为差旅的报销单总金额是多少", "category"),
        ("每个审批状态各有多少张报销单", "status"),
    ]:
        res = service.ask(q)
        sql = (res.get("sql") or "").lower()
        ok = bool(res.get("ok") and "expense_claims" in sql and must in sql)
        passed.append(
            check(
                ok,
                f"「{q}」→ {'正确命中新表与字段' if ok else '未正确命中'}（期望含 {must}）",
            )
        )
        if res.get("ok"):
            print(f"     SQL : {res['sql'][:150]}")
            print(f"     结果: {res['row_count']} 行 | {res.get('answer', '')[:60]}")
        else:
            print(f"     错误: {res.get('error')}")

    # ------------------------------------------------------------ 删表
    if not args.keep:
        print("\n【4】删除测试表，确认系统同样能感知")
        run_sql("DROP TABLE expense_claims")
        info2 = maybe_reload_schema(force=True)
        md2 = schema_md_path().read_text(encoding="utf-8")
        passed.append(check(info2.get("changed") is True, "检测到结构回退"))
        passed.append(check("expense_claims" not in md2, "结构文档已移除该表"))
    else:
        print("\n【4】保留测试表（--keep），结构文档中仍包含 expense_claims")

    print("\n" + "=" * 78)
    print(f"验收结果：{sum(passed)}/{len(passed)} 项通过")
    print(
        "说明：结构变更后的第一次提问会因提示词缓存失效而稍慢（约 +2 秒），之后恢复正常。"
    )


if __name__ == "__main__":
    main()
