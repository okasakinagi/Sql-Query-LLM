# -*- coding: utf-8 -*-
"""导出一份「模型实际看到过的完整提示词」快照（纯文本，用于查看与留档）。

    python tools/dump_prompt.py                          # 用默认问题
    python tools/dump_prompt.py "销量最高的前 5 个商品"     # 指定问题
    python tools/dump_prompt.py "问题" --out my_prompt.txt

输出：docs/prompt-example.md

注意：这只是**导出的快照**，程序运行时并不读取它；
提示词的真实来源是 app/text2sql.py 里的 SYSTEM_HEAD 常量。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import text2sql  # noqa: E402
from app.schema import schema_md_path  # noqa: E402

DEFAULT_QUESTION = "2025 年每个月的销售额分别是多少"


def main() -> None:
    ap = argparse.ArgumentParser(description="导出完整提示词")
    ap.add_argument(
        "question",
        nargs="?",
        default=DEFAULT_QUESTION,
        help="用哪个问题来挑选示例（影响 {{EXAMPLES}} 部分）",
    )
    ap.add_argument("--out", default=None, help="输出路径")
    args = ap.parse_args()

    prompt = text2sql.build_prompt(args.question)

    out = Path(args.out) if args.out else ROOT / "docs" / "prompt-example.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(prompt, encoding="utf-8")

    print(f"问题      ：{args.question}")
    print(f"结构文档  ：{schema_md_path()}")
    print(f"输出文件  ：{out}")
    print(f"长度      ：{len(prompt):,} 字符（约 {len(prompt) / 3.5:.0f} tokens）")
    print("说明      ：这只是导出的快照，程序运行时不读取它。")


if __name__ == "__main__":
    main()
