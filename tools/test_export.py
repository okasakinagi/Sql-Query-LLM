# -*- coding: utf-8 -*-
"""验收 Word 导出接口（直接调用服务端接口，不经过浏览器）。

python tools/test_export.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from app import service  # noqa: E402

URL = "http://127.0.0.1:8000/api/export/word"
OUT = ROOT / "output"


def main() -> None:
    res = service.ask("2025 年每个月的销售额分别是多少")
    if not res.get("ok"):
        print("查询失败：", res.get("error"))
        return

    payload = {
        "question": res["question"],
        "answer": res.get("answer", ""),
        "sql": res["sql"],
        "columns": res["columns"],
        "rows": res["rows"],
        "row_count": res["row_count"],
        "chartImage": None,
    }
    r = requests.post(URL, json=payload, timeout=120)
    if r.status_code != 200:
        print(f"导出失败 HTTP {r.status_code}: {r.text[:300]}")
        return

    OUT.mkdir(exist_ok=True)
    path = OUT / "导出测试.docx"
    path.write_bytes(r.content)
    print(f"OK 导出成功：{path}（{len(r.content):,} 字节）")
    print("    Content-Disposition:", r.headers.get("content-disposition"))

    # 简单校验文件是合法的 docx（zip 包，含 word/document.xml）
    import zipfile

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    ok = "word/document.xml" in names
    print(f"    docx 结构校验：{'通过' if ok else '不通过'}（{len(names)} 个内部文件）")
    txt = None
    with zipfile.ZipFile(path) as z:
        txt = z.read("word/document.xml").decode("utf-8")
    for key in ("智能数据库查询报告", "生成的 SQL 语句", "查询结果明细"):
        print(f"    包含「{key}」：{'是' if key in txt else '否'}")


if __name__ == "__main__":
    main()
