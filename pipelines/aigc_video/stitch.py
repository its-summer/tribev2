"""ffmpeg 拼接：合并各镜片段 + 旁白 + BGM + 烧字幕。

需要系统已安装 ffmpeg。dry-run 模式只打印将执行的命令。
"""
from __future__ import annotations

import shlex
import subprocess
from typing import List, Optional


def has_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def build_concat_cmd(clips: List[str], out_path: str, concat_list: str) -> List[str]:
    with open(concat_list, "w") as f:
        for c in clips:
            f.write(f"file '{c}'\n")
    return ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
            "-c", "copy", out_path]


def build_mux_cmd(video: str, voice: Optional[str], bgm: Optional[str], out_path: str) -> List[str]:
    """把旁白与 BGM 混入视频。bgm 压低音量，voice 为主。"""
    cmd = ["ffmpeg", "-y", "-i", video]
    inputs = 1
    filt = []
    if voice:
        cmd += ["-i", voice]
        inputs += 1
    if bgm:
        cmd += ["-stream_loop", "-1", "-i", bgm]
        inputs += 1
    audio_parts = []
    if voice:
        audio_parts.append("[1:a]")
    if bgm:
        idx = 2 if voice else 1
        filt.append(f"[{idx}:a]volume=0.25[bg]")
        audio_parts.append("[bg]")
    if audio_parts:
        filt.append("".join(audio_parts) + f"amix=inputs={len(audio_parts)}:duration=first[aout]")
        cmd += ["-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[aout]"]
    cmd += ["-c:v", "copy", "-shortest", out_path]
    return cmd


def run(cmd: List[str], dry_run: bool = False) -> None:
    printable = " ".join(shlex.quote(c) for c in cmd)
    if dry_run:
        print(f"  [dry-run] {printable}")
        return
    print(f"  $ {printable}")
    subprocess.run(cmd, check=True)
