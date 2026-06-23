"""开播前预检: 在真正推流前把配置/环境问题一次性查出来.

检查项: ffmpeg/ffprobe 是否就位、形象视频是否可读且含视频流、persona 语音
配置是否自洽、所属市场是否已开放、推流目标是否可解析、所需 API Key 是否设置。

    python -m livehuman.preflight personas/yuki.yaml

任一 FAIL 则退出码非 0, 适合在启动脚本/CI 里做开播前门禁。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .persona import Persona, load_persona

OK, WARN, FAIL = "OK", "WARN", "FAIL"


@dataclass
class Check:
    level: str
    name: str
    detail: str


def _ffprobe_has_video(path: str) -> bool:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=20,
        )
        return out.returncode == 0 and "video" in out.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_checks(persona: Persona) -> list[Check]:
    checks: list[Check] = []

    # 1. ffmpeg / ffprobe
    if shutil.which("ffmpeg"):
        checks.append(Check(OK, "ffmpeg", "已安装"))
    else:
        checks.append(Check(FAIL, "ffmpeg", "未找到 ffmpeg, 推流无法工作"))
    has_ffprobe = bool(shutil.which("ffprobe"))
    if not has_ffprobe:
        checks.append(Check(WARN, "ffprobe", "未找到 ffprobe, 跳过形象视频校验"))

    # 2. 形象视频
    avatar = Path(persona.avatar_video)
    if not avatar.exists():
        checks.append(Check(FAIL, "avatar_video", f"形象视频不存在: {avatar}"))
    elif has_ffprobe and not _ffprobe_has_video(str(avatar)):
        checks.append(Check(FAIL, "avatar_video", f"无法解析为含视频流的文件: {avatar}"))
    else:
        checks.append(Check(OK, "avatar_video", str(avatar)))

    # 3. 语音配置自洽
    if persona.voice_provider == "elevenlabs":
        if persona.voice_clone_id:
            checks.append(Check(OK, "voice", f"克隆音色 {persona.voice_clone_id}"))
        else:
            checks.append(Check(FAIL, "voice", "voice_provider=elevenlabs 但缺 voice_clone_id"))
    else:
        if persona.voices and persona.primary_language in persona.voices:
            checks.append(Check(OK, "voice", f"edge 音色 {len(persona.voices)} 个"))
        else:
            checks.append(Check(FAIL, "voice", "edge 音色缺失或不含主语言音色"))
    if not persona.languages:
        checks.append(Check(FAIL, "languages", "未配置任何直播语言"))

    # 4. 市场护栏
    try:
        from .market import ensure_market_active

        market = ensure_market_active(persona)
        checks.append(Check(OK, "market", f"{market.name} ({market.code}) 已开放"))
    except (PermissionError, KeyError) as e:
        checks.append(Check(FAIL, "market", str(e)))

    # 5. 推流目标
    try:
        from .pipeline import resolve_rtmp_url

        url = resolve_rtmp_url(persona)
        src = "persona.stream" if persona.stream and persona.stream.full_rtmp_url() else "环境变量"
        # 仅判断是否配置, 不打印密钥
        checks.append(Check(OK, "stream_target", f"已配置 (来源: {src})"))
    except RuntimeError as e:
        checks.append(Check(FAIL, "stream_target", str(e)))

    # 6. API Key
    if os.environ.get("ANTHROPIC_API_KEY"):
        checks.append(Check(OK, "ANTHROPIC_API_KEY", "已设置"))
    else:
        checks.append(Check(FAIL, "ANTHROPIC_API_KEY", "未设置, 无法生成内容"))
    if persona.voice_provider == "elevenlabs":
        if os.environ.get("ELEVENLABS_API_KEY"):
            checks.append(Check(OK, "ELEVENLABS_API_KEY", "已设置"))
        else:
            checks.append(Check(FAIL, "ELEVENLABS_API_KEY", "未设置, 克隆音色无法合成"))

    return checks


def format_report(checks: list[Check]) -> str:
    icon = {OK: "✓", WARN: "!", FAIL: "✗"}
    lines = [f"  [{icon[c.level]}] {c.name}: {c.detail}" for c in checks]
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) != 2:
        print("用法: python -m livehuman.preflight <persona.yaml>", file=sys.stderr)
        sys.exit(2)
    persona = load_persona(sys.argv[1])
    print(f"开播前预检: {persona.name}")
    checks = run_checks(persona)
    print(format_report(checks))
    fails = [c for c in checks if c.level == FAIL]
    if fails:
        print(f"\n预检未通过: {len(fails)} 项 FAIL, 请修复后再开播。", file=sys.stderr)
        sys.exit(1)
    print("\n预检通过, 可以开播。")


if __name__ == "__main__":
    main()
