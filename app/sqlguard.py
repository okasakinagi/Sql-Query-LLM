# -*- coding: utf-8 -*-
"""SQL 安全校验：只允许只读查询。

大模型可能生成写操作或破坏性语句，执行前必须经过本模块过滤。
采用"白名单 + 黑名单"双重校验：
  - 白名单：语句必须以 SELECT / WITH 开头
  - 黑名单：整句不得出现任何写操作关键字、多语句分隔符、文件操作函数
"""

from __future__ import annotations

import re

# 允许的起始关键字
_ALLOWED_HEAD = re.compile(r"^\s*(SELECT|WITH)\b", re.I)

# 禁止出现的关键字（词边界匹配，避免误伤 e.g. "created_date" 中的 create）
_FORBIDDEN = re.compile(
    r"\b("
    r"INSERT|UPDATE|DELETE|REPLACE|TRUNCATE|DROP|ALTER|CREATE|RENAME|"
    r"GRANT|REVOKE|COMMIT|ROLLBACK|SAVEPOINT|LOCK|UNLOCK|CALL|EXECUTE|"
    r"PREPARE|DEALLOCATE|HANDLER|LOAD|OUTFILE|DUMPFILE|INFILE|"
    r"INTO\s+OUTFILE|LOAD_FILE|BENCHMARK|SLEEP|GET_LOCK|SET\s+GLOBAL|"
    r"SET\s+SESSION|SHUTDOWN|KILL|USE|DESCRIBE|EXPLAIN\s+ANALYZE"
    r")\b",
    re.I,
)

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"(--|#)[^\n]*")


class UnsafeSQLError(ValueError):
    """生成的 SQL 未通过安全校验。"""


def clean(sql: str) -> str:
    """去掉注释、多余空白和结尾分号。"""
    sql = _BLOCK_COMMENT.sub(" ", sql)
    sql = _LINE_COMMENT.sub(" ", sql)
    sql = re.sub(r"\s+", " ", sql).strip()
    return sql.rstrip(";").strip()


def extract_sql(text: str) -> str:
    """从模型输出中稳健地抽取 SQL（容忍 markdown 代码块与前后说明文字）。"""
    text = text.strip()
    fences = re.findall(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    if fences:
        text = fences[0]
    match = re.search(r"(?is)\b(select|with)\b", text)
    if match:
        text = text[match.start() :]
    return clean(text)


def validate(sql: str) -> str:
    """校验并返回干净的 SQL；不合法则抛出 UnsafeSQLError。"""
    if not sql or not sql.strip():
        raise UnsafeSQLError("模型未生成任何 SQL 语句")

    body = clean(sql)
    if not body:
        raise UnsafeSQLError("生成的 SQL 为空")

    if ";" in body:
        raise UnsafeSQLError("生成的 SQL 包含多条语句，出于安全考虑已拒绝执行")

    if not _ALLOWED_HEAD.match(body):
        raise UnsafeSQLError("生成的语句不是只读查询（必须以 SELECT 或 WITH 开头）")

    hit = _FORBIDDEN.search(body)
    if hit:
        raise UnsafeSQLError(
            f"生成的 SQL 含受限关键字 `{hit.group(0).upper()}`，已拒绝执行"
        )

    return body
