# -*- coding: utf-8 -*-
"""从真实数据库结构生成 ER 图（Graphviz）。

    python tools/build_er_diagram.py

输出：docs/images/er_diagram.png
说明：节点/边全部来自 information_schema，结构与数据库保持一致；
      为保持可读性，每张表只展示主键、外键和少量关键业务字段。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.schema import get_schema  # noqa: E402

OUT = ROOT / "docs" / "images"
DOT = OUT / "er_diagram.dot"
PNG = OUT / "er_diagram.png"

# 业务分组与配色
GROUPS = {
    "组织": (["departments", "employees", "warehouses"], "#2563EB", "#EFF6FF"),
    "商品": (["categories", "suppliers", "products"], "#0891B2", "#ECFEFF"),
    "交易": (
        [
            "customers",
            "sales_orders",
            "sales_order_items",
            "purchase_orders",
            "purchase_order_items",
            "inventory",
        ],
        "#7C3AED",
        "#F5F3FF",
    ),
}

# 每张表额外展示的业务字段（主键与外键自动包含）。
# 演示用 ER 图只保留主键/外键，避免信息过密、缩放到幻灯片后看不清。
EXTRA_COLUMNS: dict[str, list[str]] = {}

# 边的连接端口：让 Graphviz 少交叉
EDGE_ATTR = 'color="#94A3B8", penwidth=1.1, arrowsize=0.65, arrowhead=vee'


def esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def table_node(name: str, info: dict, header: str) -> str:
    fk_cols = {f["column"]: f["ref_table"] for f in info["fks"]}
    pk_cols = {c["name"] for c in info["columns"] if c["key"] == "PRI"}

    wanted = []
    for c in info["columns"]:
        if c["name"] in pk_cols or c["name"] in fk_cols:
            wanted.append(c["name"])
    for c in EXTRA_COLUMNS.get(name, []):
        if c not in wanted:
            wanted.append(c)

    by_name = {c["name"]: c for c in info["columns"]}
    rows = []
    for col in wanted:
        meta = by_name.get(col)
        if not meta:
            continue
        if col in pk_cols:
            tag, color = "PK", "#B45309"
        elif col in fk_cols:
            tag, color = "FK", "#1D4ED8"
        else:
            tag, color = "", "#64748B"
        label = esc(col)
        if col in fk_cols:
            label += f' <FONT COLOR="#94A3B8">→ {esc(fk_cols[col])}</FONT>'
        if tag:
            tag_cell = (
                f'<TD ALIGN="LEFT" WIDTH="34"><FONT COLOR="{color}" '
                f'POINT-SIZE="8"><B>{tag}</B></FONT></TD>'
            )
        else:
            tag_cell = '<TD ALIGN="LEFT" WIDTH="34"> </TD>'
        rows.append(
            f"<TR>{tag_cell}"
            f'<TD ALIGN="LEFT"><FONT POINT-SIZE="9">{label}</FONT></TD></TR>'
        )

    return (
        f'"{name}" [label=<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" '
        f'CELLPADDING="3">'
        f'<TR><TD COLSPAN="2" BGCOLOR="{header}" ALIGN="LEFT">'
        f'<FONT COLOR="white" POINT-SIZE="10"><B>{esc(name)}</B>'
        f'  <FONT POINT-SIZE="8">{esc(info["comment"])}</FONT></FONT></TD></TR>'
        + "".join(rows)
        + f'<TR><TD COLSPAN="2" ALIGN="RIGHT"><FONT POINT-SIZE="7" COLOR="#94A3B8">'
        f'{info["rows"]} 行</FONT></TD></TR>'
        f"</TABLE>>, shape=plaintext]"
    )


def build_dot(schema: dict) -> str:
    lines = [
        "digraph ER {",
        "  graph [rankdir=TB, splines=spline, nodesep=0.22, ranksep=0.60, "
        'pad=0.15, fontname="Microsoft YaHei", bgcolor="white"];',
        '  node  [shape=plaintext, fontname="Microsoft YaHei"];',
        "  edge  [" + EDGE_ATTR + "];",
    ]

    placed = set()
    for group, (tables, header, bg) in GROUPS.items():
        present = [t for t in tables if t in schema]
        if not present:
            continue
        lines.append(f"  subgraph cluster_{hash(group) & 0xffff} {{")
        lines.append(
            f'    label=<<FONT POINT-SIZE="11" COLOR="#475569">'
            f"<B>{group}类数据</B></FONT>>;"
        )
        lines.append(
            f'    style="rounded,filled"; fillcolor="{bg}"; '
            f'color="#E2E8F0"; margin=14;'
        )
        for t in present:
            lines.append("    " + table_node(t, schema[t], header))
            placed.add(t)
        lines.append("  }")

    # 没归入分组的表也画出来
    for t, info in schema.items():
        if t not in placed:
            lines.append("  " + table_node(t, info, "#64748B"))

    # 外键边（字段名已在卡片里标了「→ 目标表」，这里不再重复标注，避免拥挤）
    for t, info in schema.items():
        if t not in schema:
            continue
        for fk in info["fks"]:
            ref = fk["ref_table"]
            if ref not in schema:
                continue
            lines.append(f'  "{t}" -> "{ref}" [{EDGE_ATTR}];')

    lines.append("}")
    return "\n".join(lines)


def main() -> None:
    schema = get_schema()
    dot = build_dot(schema)
    OUT.mkdir(exist_ok=True)
    DOT.write_text(dot, encoding="utf-8")
    print(f"DOT 已生成：{DOT}（{len(schema)} 张表）")

    result = subprocess.run(
        ["dot", "-Tpng", "-Gdpi=200", str(DOT), "-o", str(PNG)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("渲染失败：", result.stderr[:500])
        return

    from PIL import Image

    im = Image.open(PNG)
    print(
        f"ER 图已生成：{PNG}  {im.width} x {im.height}  "
        f"{PNG.stat().st_size / 1024:.0f} KB"
    )


if __name__ == "__main__":
    main()
