"""FastAPI 控制台: 管理数字人与直播任务.

    uvicorn livehuman.server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .market import ensure_market_active, load_markets, personas_by_market
from .persona import list_personas
from .pipeline import LivePipeline

PERSONAS_DIR = Path(os.environ.get("PERSONAS_DIR", Path(__file__).parent.parent / "personas"))

app = FastAPI(title="LiveHuman 控制台", version="0.1.0")

# MVP: 单实例单直播; 多房间并发见 README roadmap
_current: LivePipeline | None = None
_current_name: str | None = None


class StartRequest(BaseModel):
    persona: str
    tiktok_unique_id: str | None = None


@app.get("/markets")
def get_markets() -> dict:
    markets = load_markets()
    members = personas_by_market(PERSONAS_DIR)
    return {
        code: {
            "name": m.name,
            "language": m.language,
            "status": m.status,
            "personas": members.get(code, []),
        }
        for code, m in markets.items()
    }


@app.get("/personas")
def get_personas() -> dict:
    personas = list_personas(PERSONAS_DIR)
    return {
        name: {
            "name": p.name,
            "market": p.market,
            "languages": p.languages,
            "topics": p.topics,
        }
        for name, p in personas.items()
    }


@app.post("/streams/start")
async def start_stream(req: StartRequest) -> dict:
    global _current, _current_name
    if _current and _current.running:
        raise HTTPException(409, f"数字人「{_current_name}」正在直播, 请先停止")

    personas = list_personas(PERSONAS_DIR)
    if req.persona not in personas:
        raise HTTPException(404, f"未找到数字人: {req.persona}")

    persona = personas[req.persona]
    # 市场护栏: 未开放市场拒绝开播 (返回 403)
    try:
        ensure_market_active(persona)
    except (PermissionError, KeyError) as e:
        raise HTTPException(403, str(e)) from e

    # 推流目标: 请求显式指定 > persona.stream > 环境变量
    try:
        pipeline = LivePipeline(persona, tiktok_unique_id=req.tiktok_unique_id)
    except RuntimeError as e:  # 既无 persona.stream 也无环境变量
        raise HTTPException(400, str(e)) from e
    await pipeline.start()
    _current, _current_name = pipeline, req.persona
    return {"status": "started", "persona": req.persona}


@app.post("/streams/stop")
async def stop_stream() -> dict:
    global _current, _current_name
    if not _current:
        raise HTTPException(404, "当前没有进行中的直播")
    await _current.stop()
    name, _current, _current_name = _current_name, None, None
    return {"status": "stopped", "persona": name}


@app.get("/streams/status")
def stream_status() -> dict:
    if not _current:
        return {"running": False}
    return {
        "running": _current.running,
        "persona": _current_name,
        "stream_alive": _current.streamer.alive,
        "pending_audio_seconds": round(_current.streamer.pending_audio_seconds, 1),
    }
