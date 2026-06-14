"""OpenAI gpt-image-1 文生图 / 图生图客户端（标准库实现，无三方依赖）。

锁一致性：把 character_sheet 与产品参考图作为 image edits 的输入参考。
文档：https://platform.openai.com/docs/api-reference/images
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional

API_BASE = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")


def _key() -> str:
    k = os.environ.get("OPENAI_API_KEY")
    if not k:
        raise RuntimeError("缺少环境变量 OPENAI_API_KEY")
    return k


def generate_frame(prompt: str, size: str = "1024x1536", out_path: str = "frame.png") -> str:
    """文生图：生成一张分镜首帧。size 默认竖版 9:16 近似。返回落盘路径。"""
    req = urllib.request.Request(
        f"{API_BASE}/images/generations",
        data=json.dumps({"model": MODEL, "prompt": prompt, "size": size, "n": 1}).encode(),
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)
    import base64
    b64 = data["data"][0]["b64_json"]
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(b64))
    return out_path


def describe() -> dict:
    """dry-run 用：返回该阶段将要做的事，不发起请求。"""
    return {"client": "openai.gpt-image-1", "base": API_BASE, "model": MODEL}
