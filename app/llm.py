# -*- coding: utf-8 -*-
"""大模型客户端（OpenAI 兼容接口）。

模型作为外部依赖单独部署：llama.cpp / Ollama / LM Studio / vLLM 都可以，
本项目只通过 HTTP 调用，不包含任何模型权重文件。
部署方式见 ``deploy/README.md``。
"""

from __future__ import annotations

import time

import requests

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TEMPERATURE, LLM_TIMEOUT


class LLMError(RuntimeError):
    """模型服务不可用或返回异常。"""


def chat_ex(
    messages: list[dict],
    *,
    max_tokens: int = 512,
    temperature: float | None = None,
    stop: list[str] | None = None,
) -> dict:
    """调用模型，返回 {"text", "elapsed", "usage"}。"""
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": LLM_TEMPERATURE if temperature is None else temperature,
        "stream": False,
    }
    if stop:
        payload["stop"] = stop

    start = time.perf_counter()
    try:
        resp = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            timeout=LLM_TIMEOUT,
        )
    except requests.exceptions.ConnectionError as exc:
        raise LLMError(
            "无法连接大模型服务（%s）。请先按 deploy/README.md 启动模型服务，"
            "或通过环境变量 LLM_BASE_URL 指向已有服务。" % LLM_BASE_URL
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise LLMError(
            f"模型服务响应超时（>{LLM_TIMEOUT}s），请检查 GPU 占用情况。"
        ) from exc
    elapsed = time.perf_counter() - start

    if resp.status_code != 200:
        raise LLMError(f"模型服务返回 HTTP {resp.status_code}：{resp.text[:300]}")

    data = resp.json()
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise LLMError(f"模型返回格式异常：{str(data)[:300]}") from exc

    return {"text": text or "", "elapsed": elapsed, "usage": data.get("usage", {})}


def chat(messages: list[dict], **kwargs) -> str:
    """只要文本的简化接口。"""
    return chat_ex(messages, **kwargs)["text"]


def health() -> dict:
    """检查模型服务状态，供 /api/health 使用。"""
    try:
        r = requests.get(
            f"{LLM_BASE_URL}/models",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            timeout=5,
        )
        if r.status_code == 200:
            return {"ok": True, "detail": "模型服务在线"}
        return {"ok": False, "detail": f"HTTP {r.status_code}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": f"未连接：{exc.__class__.__name__}"}
