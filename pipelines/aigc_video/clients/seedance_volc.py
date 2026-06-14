"""火山引擎 Ark — Seedance 图生视频客户端（标准库实现）。

Ark 视频生成是异步任务：创建任务 -> 轮询 -> 拿视频 URL -> 下载。
endpoint:  POST {ARK_BASE}/contents/generations/tasks
查询:      GET  {ARK_BASE}/contents/generations/tasks/{id}
鉴权:      Authorization: Bearer {ARK_API_KEY}
模型:      ARK_VIDEO_MODEL = 你账号里 Seedance 的接入点ID(endpoint id 或 model id)

注意：火山 Ark 为国内节点，需在能访问国内火山的网络环境运行。
具体字段以火山官方文档为准：https://www.volcengine.com/docs/82379
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Optional

ARK_BASE = os.environ.get("ARK_API_BASE", "https://ark.cn-beijing.volces.com/api/v3")
VIDEO_MODEL = os.environ.get("ARK_VIDEO_MODEL", "")


def _key() -> str:
    k = os.environ.get("ARK_API_KEY")
    if not k:
        raise RuntimeError("缺少环境变量 ARK_API_KEY")
    return k


def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{ARK_BASE}{path}",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def _get(path: str) -> dict:
    req = urllib.request.Request(
        f"{ARK_BASE}{path}",
        headers={"Authorization": f"Bearer {_key()}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def image_to_video(
    first_frame_url: str,
    prompt: str,
    duration: int = 5,
    ratio: str = "9:16",
    resolution: str = "720p",
    out_path: str = "clip.mp4",
    poll_interval: int = 5,
    timeout_s: int = 600,
) -> str:
    """图生视频。first_frame_url 需是可被火山访问的图片URL（先上传到对象存储/可公网访问）。"""
    if not VIDEO_MODEL:
        raise RuntimeError("缺少环境变量 ARK_VIDEO_MODEL（Seedance 接入点ID）")
    # Ark content 数组：文本提示 + 首帧图（role: first_frame）
    text = f"{prompt} --ratio {ratio} --resolution {resolution} --duration {duration}"
    payload = {
        "model": VIDEO_MODEL,
        "content": [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": first_frame_url}, "role": "first_frame"},
        ],
    }
    task = _post("/contents/generations/tasks", payload)
    task_id = task.get("id") or task.get("task_id")
    if not task_id:
        raise RuntimeError(f"创建任务失败: {task}")

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        st = _get(f"/contents/generations/tasks/{task_id}")
        status = st.get("status")
        if status in ("succeeded", "success"):
            url = (st.get("content") or {}).get("video_url") or st.get("video_url")
            if not url:
                raise RuntimeError(f"任务成功但无视频URL: {st}")
            urllib.request.urlretrieve(url, out_path)
            return out_path
        if status in ("failed", "error"):
            raise RuntimeError(f"任务失败: {st}")
        time.sleep(poll_interval)
    raise TimeoutError(f"任务 {task_id} 超时")


def describe() -> dict:
    return {"client": "volcengine.ark.seedance", "base": ARK_BASE, "model": VIDEO_MODEL or "(未设置 ARK_VIDEO_MODEL)"}
