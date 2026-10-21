# -*- coding: utf-8 -*-
"""数据库结构读取与提示词文本生成。

设计要点：
1. 从 information_schema 动态读取表 / 字段 / 注释 / 外键，**不改代码即可适配换库**；
2. 对低基数枚举列（status、credit_level 等）采样真实取值，写进提示词——
   这是提升 Text-to-SQL 准确率最有效的手段之一（模型能准确拼出 '已完成' 等中文值）；
3. 结构文档固化成 schema/<库名>.md，内容恒定以便命中模型的前缀缓存；
4. 支持**结构变更自动感知**：提问前用轻量指纹轮询 information_schema，
   发现新增表/字段/外键就自动重建文档并清空提示词缓存，无需重启服务。
"""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path

import db as dbm
from config import BASE_DIR, DB

# 枚举列识别：按列类型（ENUM）或列名模式判断，**新增表无需改代码**。
ENUM_NAME_PATTERNS = (
    "status",
    "type",
    "category",
    "level",
    "rating",
    "unit",
    "city",
    "industry",
    "gender",
    "relationship",
    "province",
)

# 不满足通用模式、但确实需要采样的特殊列名
ENUM_COLUMN_HINTS = {"job_title", "department_name", "warehouse_name"}

# 哪些枚举值值得写进提示词（太多会把提示词撑大）
KEEP_ENUM_PATTERNS = ("status", "type", "category", "level", "rating", "unit")


def _match_name(name: str, patterns) -> bool:
    n = name.lower()
    return any(n == p or n.startswith(p + "_") or n.endswith("_" + p) for p in patterns)


def _is_identifier_or_name(name: str) -> bool:
    """id / name 这类列要么高基数、要么没有枚举语义，不参与取值采样。"""
    n = name.lower()
    return (
        n == "id"
        or n.endswith("_id")
        or n.endswith("id")
        or n == "name"
        or n.endswith("_name")
    )


def is_enum_candidate(column: dict) -> bool:
    """判断某列是否值得采样枚举取值。"""
    if column["type"].lower().startswith("enum("):
        return True
    if _is_identifier_or_name(column["name"]):
        return False
    if column["name"].lower() in ENUM_COLUMN_HINTS:
        return True
    return _match_name(column["name"], ENUM_NAME_PATTERNS)


CACHE_TTL = 300  # 秒
SCHEMA_CHECK_TTL = 3.0  # 秒：提问前最多每 3 秒做一次结构变更检查
_lock = threading.Lock()
_reload_lock = threading.Lock()
_cache: dict = {"data": None, "ts": 0.0}
_schema_text_cache: str | None = None
_last_check: float = 0.0


# ------------------------------------------------------------------ 结构读取
def _load() -> dict:
    conn = dbm.connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT TABLE_NAME, TABLE_COMMENT
                  FROM information_schema.TABLES
                 WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
                 ORDER BY TABLE_NAME
            """,
                (DB["database"],),
            )
            tables = {
                name: {
                    "name": name,
                    "comment": comment or "",
                    "columns": [],
                    "enums": {},
                    "fks": [],
                    "rows": 0,
                }
                for name, comment in cur.fetchall()
            }

            cur.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE,
                       COLUMN_KEY, COLUMN_COMMENT
                  FROM information_schema.COLUMNS
                 WHERE TABLE_SCHEMA = %s
                 ORDER BY TABLE_NAME, ORDINAL_POSITION
            """,
                (DB["database"],),
            )
            for tname, cname, ctype, nullable, key, comment in cur.fetchall():
                if tname in tables:
                    tables[tname]["columns"].append(
                        {
                            "name": cname,
                            "type": ctype,
                            "nullable": nullable == "YES",
                            "key": key,
                            "comment": comment or "",
                        }
                    )

            cur.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME,
                       REFERENCED_COLUMN_NAME
                  FROM information_schema.KEY_COLUMN_USAGE
                 WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME IS NOT NULL
                 ORDER BY TABLE_NAME, COLUMN_NAME
            """,
                (DB["database"],),
            )
            for tname, cname, rtable, rcol in cur.fetchall():
                if tname in tables:
                    tables[tname]["fks"].append(
                        {"column": cname, "ref_table": rtable, "ref_column": rcol}
                    )

            # 实际行数
            for tname, info in tables.items():
                cur.execute(f"SELECT COUNT(*) FROM `{tname}`")
                info["rows"] = cur.fetchone()[0]
    finally:
        conn.close()
    return tables


def load_enums(schema: dict) -> dict:
    """采样低基数枚举列的真实取值。

    只在【生成结构文档】时调用一次：取值会写入 schema/*.md 并被固化下来，
    之后运行时不再需要为了拼提示词去查任何业务数据。
    """
    conn = dbm.connect()
    try:
        with conn.cursor() as cur:
            for tname, info in schema.items():
                for col in info["columns"]:
                    if not is_enum_candidate(col):
                        continue
                    try:
                        cur.execute(
                            f"SELECT DISTINCT `{col['name']}` FROM `{tname}` "
                            f"WHERE `{col['name']}` IS NOT NULL LIMIT 25"
                        )
                        vals = [r[0] for r in cur.fetchall()]
                    except Exception:  # noqa: BLE001
                        continue
                    if 0 < len(vals) <= 25:
                        info["enums"][col["name"]] = vals
    finally:
        conn.close()
    return schema


def get_schema(force: bool = False) -> dict:
    """返回数据库结构（带 TTL 缓存）。"""
    with _lock:
        fresh = _cache["data"] is not None and (time.time() - _cache["ts"]) < CACHE_TTL
        if fresh and not force:
            return _cache["data"]
        data = _load()
        _cache["data"] = data
        _cache["ts"] = time.time()
        return data


# -------------------------------------------------------------- 提示词文本
def format_ddl(schema: dict, tables: list[str] | None = None) -> str:
    """把表结构格式化成给模型看的 DDL 文本（详细版，用于命令行排查）。"""
    names = [t for t in (tables or list(schema)) if t in schema]
    blocks = []
    for tname in names:
        info = schema[tname]
        lines = [
            f"### 表 {tname}（{info['comment'] or '无注释'}，约 {info['rows']} 行）"
        ]
        width = max((len(c["name"]) for c in info["columns"]), default=0)
        for c in info["columns"]:
            flags = []
            if c["key"] == "PRI":
                flags.append("主键")
            elif c["key"] == "UNI":
                flags.append("唯一")
            if not c["nullable"]:
                flags.append("非空")
            suffix = f"  [{', '.join(flags)}]" if flags else ""
            comment = f"  -- {c['comment']}" if c["comment"] else ""
            lines.append(f"  {c['name']:<{width}} {c['type']}{suffix}{comment}")
        for col, vals in info["enums"].items():
            lines.append(f"  # {col} 的取值为：" + "、".join(f"'{v}'" for v in vals))
        for fk in info["fks"]:
            lines.append(
                f"  # 外键：{fk['column']} -> " f"{fk['ref_table']}.{fk['ref_column']}"
            )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


# 提示词里保留枚举取值的列由 KEEP_ENUM_PATTERNS 统一控制（见文件开头）


def format_ddl_compact(schema: dict, tables: list[str] | None = None) -> str:
    """紧凑版 DDL：一行一张表，去掉字段类型与冗余标记。

    这是**性能关键设计**：
      - 长度只有详细版的 ~40%，前缀预处理时间同比例下降；
      - 12 张表的完整结构固定不变，放在提示词最前面，可被 llama.cpp 的
        前缀缓存完整命中，正常连续提问时前处理耗时趋近于 0。
    """
    names = [t for t in (tables or list(schema)) if t in schema]
    lines = []
    for tname in names:
        info = schema[tname]
        parts = []
        for c in info["columns"]:
            seg = c["name"]
            if c["comment"]:
                seg += f"({c['comment']})"
            if c["key"] == "PRI":
                seg += "[主键]"
            if (
                _match_name(c["name"], KEEP_ENUM_PATTERNS)
                and not _is_identifier_or_name(c["name"])
                and c["name"] in info["enums"]
            ):
                seg += "{" + "/".join(str(v) for v in info["enums"][c["name"]]) + "}"
            parts.append(seg)
        fks = "；".join(
            f"{f['column']}→{f['ref_table']}.{f['ref_column']}" for f in info["fks"]
        )
        fk_text = f"  外键：{fks}" if fks else ""
        lines.append(
            f"■ {tname}（{info['comment'] or '无注释'}，{info['rows']} 行）："
            + "，".join(parts)
            + fk_text
        )
    return "\n".join(lines)


def schema_overview(schema: dict) -> list[dict]:
    """给前端侧边栏展示的表结构概览。"""
    return [
        {
            "name": t,
            "comment": i["comment"],
            "rows": i["rows"],
            "columns": [
                {"name": c["name"], "type": c["type"], "comment": c["comment"]}
                for c in i["columns"]
            ],
        }
        for t, i in schema.items()
    ]


# ============================================================ 结构文档（md）
# 核心思路（也是性能关键）：
#   SQL 只依赖表结构、不依赖数据，所以把结构固化成一个 markdown 文件：
#     - 提示词前缀字节级恒定 -> llama.cpp 前缀缓存稳定命中，前处理耗时
#       从 ~2s 降到 ~0；
#     - 不再需要在启动时跑 DISTINCT 采样取值（纯粹为了拼提示词）；
#     - 文件可人工微调（补充同义词、业务口径），改完系统会自动校验一致性。
SCHEMA_DIR = BASE_DIR / "schema"
FINGERPRINT_PREFIX = "<!-- fingerprint: "


def fingerprint(schema: dict) -> str:
    """表 / 字段 / 外键集合的指纹，用于判断结构文档是否与真实库脱节。"""
    parts = []
    for t, info in sorted(schema.items()):
        cols = ",".join(c["name"] for c in info["columns"])
        fks = ",".join(
            sorted(
                f"{f['column']}>{f['ref_table']}.{f['ref_column']}" for f in info["fks"]
            )
        )
        parts.append(f"{t}:{cols}|{fks}")
    return hashlib.md5(";".join(parts).encode("utf-8")).hexdigest()[:16]


def _structure_fingerprint_from_db() -> str:
    """只查 information_schema 的轻量指纹，不碰任何业务数据，通常 1~3ms。"""
    conn = dbm.connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.TABLE_NAME, c.COLUMN_NAME
                  FROM information_schema.COLUMNS c
                  JOIN information_schema.TABLES t
                    ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME
                 WHERE c.TABLE_SCHEMA = %s AND t.TABLE_TYPE = 'BASE TABLE'
                 ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION
            """,
                (DB["database"],),
            )
            cols: dict = {}
            for tname, cname in cur.fetchall():
                cols.setdefault(tname, []).append(cname)

            cur.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME,
                       REFERENCED_COLUMN_NAME
                  FROM information_schema.KEY_COLUMN_USAGE
                 WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME IS NOT NULL
                 ORDER BY TABLE_NAME, COLUMN_NAME
            """,
                (DB["database"],),
            )
            fks: dict = {}
            for tname, cname, rtable, rcol in cur.fetchall():
                fks.setdefault(tname, []).append(f"{cname}>{rtable}.{rcol}")
    finally:
        conn.close()

    parts = [
        f"{t}:{','.join(cols[t])}|{','.join(sorted(fks.get(t, [])))}"
        for t in sorted(cols)
    ]
    return hashlib.md5(";".join(parts).encode("utf-8")).hexdigest()[:16]


def maybe_reload_schema(force: bool = False) -> dict:
    """检查数据库结构是否变化；变了就重建结构文档并清空提示词缓存。

    带 3 秒节流，开销可忽略（相比 2 秒级的模型耗时）。
    返回 {"changed": bool, ...}，调用方可据此提示用户。
    """
    global _last_check, _schema_text_cache

    now = time.time()
    if not force and (now - _last_check) < SCHEMA_CHECK_TTL:
        return {"changed": False, "checked": False}

    with _reload_lock:
        _last_check = now
        try:
            new_fp = _structure_fingerprint_from_db()
        except Exception as exc:  # noqa: BLE001
            return {"changed": False, "checked": True, "error": str(exc)}

        old_fp = fingerprint(get_schema())
        changed = new_fp != old_fp
        if not changed and not force:
            return {"changed": False, "checked": True, "fingerprint": new_fp}

        schema = get_schema(force=True)
        text, regenerated = ensure_schema_md(schema, force=force)
        _schema_text_cache = text
        return {
            "changed": changed,
            "checked": True,
            "old": old_fp,
            "new": new_fp,
            "tables": len(schema),
            "regenerated": regenerated,
        }


def build_schema_markdown(schema: dict) -> str:
    """根据真实库结构生成结构文档内容。"""
    load_enums(schema)
    lines = [
        f"# 数据库结构：{DB['database']}",
        "",
        f"{FINGERPRINT_PREFIX}{fingerprint(schema)} -->",
        "",
        "> 本文件由 `python tools/gen_schema_md.py` 自动生成，也可以手工微调"
        "（例如补充同义词、常见口径）。",
        "> 系统启动时会校验指纹，若与真实库不一致会自动重新生成。",
        "> 这个文件会**原样**作为提示词的一部分发给大模型，请保持简洁。",
        "",
    ]
    for tname, info in schema.items():
        lines.append(f"## {tname}（{info['comment'] or '无注释'}，{info['rows']} 行）")
        parts = []
        for c in info["columns"]:
            seg = c["name"]
            if c["comment"]:
                seg += f"({c['comment']})"
            if c["key"] == "PRI":
                seg += "[主键]"
            if (
                _match_name(c["name"], KEEP_ENUM_PATTERNS)
                and not _is_identifier_or_name(c["name"])
                and c["name"] in info["enums"]
            ):
                seg += "{" + "/".join(str(v) for v in info["enums"][c["name"]]) + "}"
            parts.append(seg)
        lines.append("，".join(parts))
        fks = "；".join(
            f"{f['column']}→{f['ref_table']}.{f['ref_column']}" for f in info["fks"]
        )
        if fks:
            lines.append(f"外键：{fks}")
        lines.append("")
    return "\n".join(lines)


def schema_md_path() -> Path:
    return SCHEMA_DIR / f"{DB['database']}.md"


def ensure_schema_md(
    schema: dict | None = None, force: bool = False
) -> tuple[str, bool]:
    """确保结构文档存在且与真实库一致，返回 (文档内容, 是否重新生成)。"""
    schema = schema or get_schema()
    path = schema_md_path()
    want = fingerprint(schema)
    if path.exists() and not force:
        text = path.read_text(encoding="utf-8")
        if f"{FINGERPRINT_PREFIX}{want} -->" in text:
            return text, False
    text = build_schema_markdown(schema)
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text, True


def schema_text(reload: bool = False) -> str:
    """返回发给大模型的结构文档（带内存缓存）。"""
    global _schema_text_cache
    if _schema_text_cache is None or reload:
        _schema_text_cache = ensure_schema_md()[0]
    return _schema_text_cache
