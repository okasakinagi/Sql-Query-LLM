# -*- coding: utf-8 -*-
"""FastAPI 应用入口：提供查询接口、结构接口与 Word 导出接口，并托管前端页面。"""

from __future__ import annotations

import threading
import urllib.parse
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import llm, service, text2sql
from app.export import build_docx
from app.schema import get_schema, maybe_reload_schema, schema_overview
from config import BASE_DIR, DB

WEB_DIR = BASE_DIR / "web"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动时后台预热模型提示词缓存，让第一个问题也是“热”的。"""
    threading.Thread(target=text2sql.warmup, daemon=True).start()
    yield


app = FastAPI(
    title="基于大语言模型的智能数据库查询系统", version="1.0.0", lifespan=lifespan
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str = Field(..., description="自然语言问题")


class ExportRequest(BaseModel):
    question: str = ""
    answer: str = ""
    sql: str = ""
    columns: list[str] = Field(default_factory=list)
    rows: list[list] = Field(default_factory=list)
    row_count: int = 0
    chartImage: str | None = None  # ECharts 导出的 base64 PNG


# ------------------------------------------------------------------ 页面
@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


# ------------------------------------------------------------------ 接口
@app.get("/api/health")
def health() -> dict:
    """健康检查：数据库 + 模型服务。"""
    db_ok, db_detail = False, ""
    try:
        from db import connect

        conn = connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            db_ok, db_detail = True, f"数据库 {DB['database']} 正常"
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        db_detail = f"数据库连接失败：{exc}"

    model = llm.health()
    return {
        "database": {"ok": db_ok, "detail": db_detail},
        "model": model,
        "ready": db_ok and model["ok"],
    }


@app.get("/api/schema")
def api_schema(refresh: bool = False) -> dict:
    """返回表结构概览，供前端侧边栏展示。"""
    try:
        if not refresh:
            maybe_reload_schema()  # 自动感知新增表/字段
        schema = get_schema(force=refresh)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"读取数据库结构失败：{exc}"
        ) from exc
    return {"database": DB["database"], "tables": schema_overview(schema)}


@app.post("/api/schema/refresh")
def api_schema_refresh() -> dict:
    """手动强制刷新结构文档。

    用于演示"数据库结构变了，系统无需重启即可识别"：
    重建结构文档 -> 清空提示词缓存 -> 用新结构回答后续问题。
    """
    try:
        info = maybe_reload_schema(force=True)
        schema = get_schema()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"刷新结构失败：{exc}") from exc
    return {
        "ok": True,
        **info,
        "database": DB["database"],
        "tables": schema_overview(schema),
    }


@app.post("/api/ask")
def api_ask(req: AskRequest) -> JSONResponse:
    """核心接口：自然语言 -> SQL -> 结果 -> 答案 -> 图表建议。"""
    result = service.ask(req.question)
    return JSONResponse(result)


@app.post("/api/export/word")
def api_export_word(req: ExportRequest) -> Response:
    """导出 Word 报告。"""
    try:
        content = build_docx(req.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"生成 Word 失败：{exc}") from exc

    stamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"智能查询报告_{stamp}.docx"
    quoted = urllib.parse.quote(filename)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename=report.docx; filename*=UTF-8''{quoted}"
        },
    )


# ------------------------------------------------------------- 静态资源
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
