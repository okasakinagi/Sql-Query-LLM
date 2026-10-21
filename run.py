# -*- coding: utf-8 -*-
"""开发服务器启动脚本：python run.py

默认监听 http://127.0.0.1:8000
"""

from __future__ import annotations

import uvicorn

from config import LLM_BASE_URL, WEB_HOST, WEB_PORT

if __name__ == "__main__":
    print(f"Web 服务： http://{WEB_HOST}:{WEB_PORT}")
    print(f"模型服务： {LLM_BASE_URL}（不可用请参考 deploy/README.md）")
    uvicorn.run("app.main:app", host=WEB_HOST, port=WEB_PORT, reload=False)
