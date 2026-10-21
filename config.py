# -*- coding: utf-8 -*-
"""全局配置。

所有「环境相关」参数集中在这里，其他模块统一 ``from config import ...``。

配置优先级（从高到低）：

1. 进程环境变量（例如 ``set LLM_BASE_URL=...``）
2. 项目根目录下的 ``.env`` 文件（可从 ``.env.example`` 复制而来）
3. 本文件里的默认值

这样既能在本机直接跑，也能在 Docker / CI 里通过环境变量覆盖，
不会把口令和绝对路径写死在代码里。
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


# --------------------------------------------------------------- .env 解析
def _load_dotenv(path: Path) -> None:
    """极简 .env 解析器（不引入额外依赖）。

    仅支持 ``KEY=VALUE`` 形式，忽略空行与 ``#`` 注释，
    已存在的环境变量不会被覆盖。
    """
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(BASE_DIR / ".env")


# ------------------------------------------------------------------ 取值工具
def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


# -------------------------------------------------------------------- MySQL
# 默认值与 ``.env.example`` 保持一致，方便首次运行。
DB = {
    "host": _env("DB_HOST", "127.0.0.1"),
    "port": _env_int("DB_PORT", 3306),
    "user": _env("DB_USER", "root"),
    "password": _env("DB_PASSWORD", "123456"),
    "database": _env("DB_NAME", "erp_demo"),
    "charset": _env("DB_CHARSET", "utf8mb4"),
}

# ------------------------------------------------------ 大模型（外部依赖）
# 任何提供 OpenAI 兼容接口的服务都可以接：llama.cpp / Ollama / LM Studio / vLLM。
# 部署方式见 deploy/README.md。
LLM_BASE_URL = _env("LLM_BASE_URL", "http://127.0.0.1:8080/v1")
LLM_MODEL = _env("LLM_MODEL", "qwen2.5-coder-7b-instruct")
LLM_API_KEY = _env("LLM_API_KEY", "not-needed")
LLM_TIMEOUT = _env_int("LLM_TIMEOUT", 120)  # 单次请求超时（秒）
LLM_TEMPERATURE = _env_float("LLM_TEMPERATURE", 0.0)  # 生成 SQL 用 0，保证可复现

# ---------------------------------------------------------------- 查询与安全
QUERY_TIMEOUT = _env_int("QUERY_TIMEOUT", 10)  # 单条 SQL 执行超时，防全表扫描
MAX_RETRY = _env_int("MAX_RETRY", 2)  # 生成失败后的自动重试次数
MAX_RESULT_ROWS = _env_int("MAX_RESULT_ROWS", 2000)  # 返回前端的最大行数
ANSWER_PREVIEW_ROWS = _env_int("ANSWER_PREVIEW_ROWS", 30)  # 送模型的预览行数

# ---------------------------------------------------------------------- Web
WEB_HOST = _env("WEB_HOST", "127.0.0.1")
WEB_PORT = _env_int("WEB_PORT", 8000)

# ------------------------------------------------------------------ 数据生成
SEED = _env_int("SEED", 20260910)  # 随机种子，保证每次重建数据完全一致
