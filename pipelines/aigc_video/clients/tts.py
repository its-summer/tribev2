"""OpenAI TTS 旁白客户端（标准库实现）。

文档：https://platform.openai.com/docs/api-reference/audio/createSpeech
"""
from __future__ import annotations

import json
import os
import urllib.request

API_BASE = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
MODEL = os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
VOICE = os.environ.get("OPENAI_TTS_VOICE", "alloy")


def _key() -> str:
    k = os.environ.get("OPENAI_API_KEY")
    if not k:
        raise RuntimeError("缺少环境变量 OPENAI_API_KEY")
    return k


def synthesize(text: str, out_path: str = "voice.mp3") -> str:
    req = urllib.request.Request(
        f"{API_BASE}/audio/speech",
        data=json.dumps({"model": MODEL, "voice": VOICE, "input": text, "response_format": "mp3"}).encode(),
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        with open(out_path, "wb") as f:
            f.write(resp.read())
    return out_path


def describe() -> dict:
    return {"client": "openai.tts", "base": API_BASE, "model": MODEL, "voice": VOICE}
