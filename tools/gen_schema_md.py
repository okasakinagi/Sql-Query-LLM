# -*- coding: utf-8 -*-
"""生成 / 刷新数据库结构文档 schema/<库名>.md。

    python tools/gen_schema_md.py            # 结构与指纹一致时跳过，不一致才重写
    python tools/gen_schema_md.py --force    # 强制按真实库重新生成（会覆盖手工修改）

为什么要把它做成固定文件：
    1. SQL 只依赖表结构、不依赖数据，所以结构完全可以固化下来；
    2. 提示词前缀在字节层面恒定不变 -> llama.cpp 的前缀缓存能稳定命中，
       实测可把一次查询的提示词预处理从约 2s 降到接近 0；
    3. 运行时不再需要为了拼提示词去查询任何业务数据（枚举取值已写入文档）；
    4. 文件可以人工微调（补充同义词、统一口径），改完会在数据库结构变化时
       被自动重新生成，并用指纹保证不会静默脱节。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.schema import (
    build_schema_markdown,
    fingerprint,  # noqa: E402
    get_schema,
    schema_md_path,
)


def main() -> None:
    ap = argparse.ArgumentParser(description="生成数据库结构文档")
    ap.add_argument("--force", action="store_true", help="强制重新生成")
    args = ap.parse_args()

    schema = get_schema(force=True)
    path = schema_md_path()
    want = fingerprint(schema)

    if path.exists() and not args.force:
        text = path.read_text(encoding="utf-8")
        if f"fingerprint: {want} -->" in text:
            print(f"结构文档已是最新（指纹 {want}）：{path}")
            return
        print(f"检测到数据库结构变化（指纹 {want}），重新生成 ...")

    text = build_schema_markdown(schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

    print(f"已生成结构文档：{path}")
    print(f"    指纹：{want}")
    print(
        f"    表数：{len(schema)}，字符数：{len(text)}（约 {len(text) // 3.5:.0f} tokens）"
    )


if __name__ == "__main__":
    main()
