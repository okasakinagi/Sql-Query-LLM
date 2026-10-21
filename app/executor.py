# -*- coding: utf-8 -*-
"""查询执行器：带超时保护与结果集裁剪。"""

from __future__ import annotations

import datetime as dt
import time
from decimal import Decimal

import db as dbm
from config import MAX_RESULT_ROWS, QUERY_TIMEOUT


class QueryError(RuntimeError):
    """SQL 执行失败。"""


def _jsonable(v):
    """把 MySQL 返回值转成可以 JSON 序列化的类型。"""
    if isinstance(v, Decimal):
        f = float(v)
        return int(f) if f.is_integer() and abs(f) < 1e15 else f
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, dt.timedelta):
        return str(v)
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return v


def execute(
    sql: str, max_rows: int = MAX_RESULT_ROWS, timeout: int = QUERY_TIMEOUT
) -> dict:
    """执行只读 SQL，返回 {columns, rows, row_count, elapsed, truncated}。"""
    conn = dbm.connect()
    try:
        with conn.cursor() as cur:
            # 防止全表扫描把服务拖死：MySQL 会在超时后中断该查询
            cur.execute(f"SET SESSION max_execution_time = {int(timeout * 1000)}")
            start = time.perf_counter()
            try:
                cur.execute(sql)
            except Exception as exc:  # noqa: BLE001
                raise QueryError(str(exc)) from exc
            elapsed = time.perf_counter() - start

            columns = [d[0] for d in (cur.description or [])]
            fetched = cur.fetchmany(max_rows + 1) if columns else []
            truncated = len(fetched) > max_rows
            rows = [[_jsonable(v) for v in r] for r in fetched[:max_rows]]
            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "elapsed": round(elapsed, 4),
                "truncated": truncated,
            }
    finally:
        conn.close()


def explain_ok(sql: str) -> tuple[bool, str]:
    """用 EXPLAIN 预检 SQL 的语法与字段合法性，不真正取数。"""
    conn = dbm.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("EXPLAIN " + sql)
            cur.fetchall()
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    finally:
        conn.close()
