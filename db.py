# -*- coding: utf-8 -*-
"""MySQL 连接的轻量封装（供构建脚本与后端共用）。"""

from __future__ import annotations

import re
from pathlib import Path

import pymysql

from config import DB


def connect(with_database: bool = True, autocommit: bool = True):
    """创建一个 MySQL 连接。

    with_database=False 时不指定库，用于执行 CREATE DATABASE。
    """
    cfg = {k: v for k, v in DB.items() if k != "database"}
    if with_database:
        cfg["database"] = DB["database"]
    return pymysql.connect(autocommit=autocommit, **cfg)


_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"--[^\n]*")


def split_sql(text: str) -> list[str]:
    """把 .sql 文件拆成一条条可执行语句（去掉注释与空语句）。"""
    text = _BLOCK_COMMENT.sub("", text)
    text = _LINE_COMMENT.sub("", text)
    return [s.strip() for s in text.split(";") if s.strip()]


def run_sql_file(path: str | Path, with_database: bool = True) -> int:
    """执行整个 .sql 文件，返回执行的语句数。"""
    path = Path(path)
    statements = split_sql(path.read_text(encoding="utf-8"))
    conn = connect(with_database=with_database)
    try:
        with conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)
    finally:
        conn.close()
    return len(statements)


def table_counts(tables: list[str]) -> list[tuple[str, int]]:
    """统计各表行数，用于构建完成后的自检输出。"""
    conn = connect()
    try:
        out = []
        with conn.cursor() as cur:
            for t in tables:
                cur.execute(f"SELECT COUNT(*) FROM `{t}`")
                out.append((t, cur.fetchone()[0]))
        return out
    finally:
        conn.close()
