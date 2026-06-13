"""员工数字人生成流水线: 一段产品讲解视频 → 可开播的数字人.

流程:
  1. 授权校验   员工书面授权文件必须存在 (合规硬门槛, 不可跳过)
  2. 素材提取   ffmpeg 抽取语音样本 wav + 形象循环视频 mp4
  3. 声音克隆   ElevenLabs IVC, 克隆后可用员工的声音说几十种语言
  4. 内容转写   faster-whisper 本地转写 (或 --transcript 提供文字稿)
  5. 风格提炼   Claude 从文字稿提炼人设/说话风格/产品知识点
  6. 生成配置   写出 personas/<id>.yaml, 即可用现有 pipeline 开播

本土员工策略: 尽量让目标市场的母语员工用母语录制。克隆音色会带录制者
的口音, 母语录制 → 该市场直播最地道, 故母语默认即数字人的主直播语言。

用法:
  # 西班牙本土员工录西语讲解 -> 面向西语市场直播
  python -m livehuman.creation.builder \\
      --video recordings/lucia.mp4 \\
      --name Lucía --employee-id E2031 \\
      --consent-doc consents/lucia_authorization.pdf \\
      --native-language es \\
      --out personas/lucia.yaml
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

import yaml

from ..persona import Persona, SourceInfo
from . import video_assets
from .style_analyzer import analyze_style
from .transcribe import transcribe
from .voice_clone import clone_voice


def build_digital_human(
    video: str | Path,
    name: str,
    consent_doc: str | Path,
    out_yaml: str | Path,
    native_language: str,
    employee_id: str = "",
    languages: list[str] | None = None,
    primary_language: str | None = None,
    transcript: str | None = None,
    loop_start: float = 0.0,
    loop_duration: float = 20.0,
    extra_notes: str = "",
    assets_dir: str | Path = "assets",
) -> Path:
    video, out_yaml = Path(video), Path(out_yaml)
    if not video.exists():
        raise FileNotFoundError(f"找不到录制视频: {video}")

    # 本土员工用母语录制: 克隆音色会带母语口音, 故母语即该数字人的主直播语言。
    # 主语言默认取母语; 语言列表默认仅母语, 但始终包含母语。
    primary_language = primary_language or native_language
    languages = languages or [native_language]
    if native_language not in languages:
        languages = [native_language, *languages]

    # 1. 授权校验 —— 没有员工书面授权一律不生成
    consent_doc = Path(consent_doc)
    if not consent_doc.exists():
        raise PermissionError(
            f"未找到员工授权文件: {consent_doc}\n"
            "克隆真人声音与形象必须先取得本人书面授权 "
            "(TikTok 合成媒体政策与各地区深度合成法规均有要求)。"
        )

    human_id = out_yaml.stem
    asset_root = Path(assets_dir) / human_id

    # 2. 素材提取
    print(f"[1/5] 提取素材 -> {asset_root}/")
    wav = video_assets.extract_voice_sample(video, asset_root / "voice_sample.wav")
    loop = video_assets.extract_idle_loop(
        video, asset_root / "idle_loop.mp4", start=loop_start, duration=loop_duration
    )

    # 3. 声音克隆
    print("[2/5] 克隆声音 (ElevenLabs)...")
    voice_id = clone_voice(name, wav)
    print(f"      voice_id = {voice_id}")

    # 4. 内容转写
    if transcript is None:
        print("[3/5] 转写讲解内容 (faster-whisper)...")
        transcript = transcribe(wav)
    else:
        print("[3/5] 使用提供的文字稿")

    # 5. 风格提炼
    print("[4/5] Claude 提炼人设与产品知识点...")
    draft = analyze_style(
        name, transcript, native_language=native_language, extra_notes=extra_notes
    )

    # 6. 生成 persona
    persona = Persona(
        name=name,
        description=draft.description,
        primary_language=primary_language,
        languages=languages,
        voice_provider="elevenlabs",
        voice_clone_id=voice_id,
        topics=draft.topics,
        avatar_video=str(loop),
        style_notes=draft.style_notes,
        source=SourceInfo(
            employee_name=name,
            employee_id=employee_id,
            native_language=native_language,
            consent_doc=str(consent_doc),
            source_video=str(video),
            created_at=datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        ),
    )
    if non_native := [lang for lang in languages if lang != native_language]:
        print(
            f"      提示: 克隆音色以母语 {native_language} 最自然; "
            f"用 {', '.join(non_native)} 直播时会带 {native_language} 口音。"
        )
    out_yaml.parent.mkdir(parents=True, exist_ok=True)
    out_yaml.write_text(
        yaml.safe_dump(persona.model_dump(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"[5/5] 完成: {out_yaml}")
    print(f"开播: python -m livehuman.pipeline {out_yaml}")
    return out_yaml


def main() -> None:
    parser = argparse.ArgumentParser(description="从员工讲解视频生成数字人")
    parser.add_argument("--video", required=True, help="员工录制的产品讲解视频")
    parser.add_argument("--name", required=True, help="员工姓名 (数字人名)")
    parser.add_argument("--consent-doc", required=True, help="员工书面授权文件路径")
    parser.add_argument("--out", required=True, help="输出 persona YAML 路径")
    parser.add_argument(
        "--native-language",
        required=True,
        help="员工母语/录制语言, 如 es / ja / zh。默认作为主直播语言, 克隆音色对它最自然",
    )
    parser.add_argument("--employee-id", default="")
    parser.add_argument(
        "--languages", nargs="+", default=None,
        help="直播语言列表 (默认仅母语; 母语始终包含在内)",
    )
    parser.add_argument(
        "--primary-language", default=None, help="主直播语言 (默认取母语)"
    )
    parser.add_argument("--transcript", help="现成文字稿文件 (跳过 whisper 转写)")
    parser.add_argument("--loop-start", type=float, default=0.0, help="形象循环片段起点(秒)")
    parser.add_argument("--loop-duration", type=float, default=20.0, help="形象循环片段时长(秒)")
    parser.add_argument("--extra-notes", default="", help="补充信息, 如产品背景")
    args = parser.parse_args()

    transcript = None
    if args.transcript:
        transcript = Path(args.transcript).read_text(encoding="utf-8")

    try:
        build_digital_human(
            video=args.video,
            name=args.name,
            consent_doc=args.consent_doc,
            out_yaml=args.out,
            native_language=args.native_language,
            employee_id=args.employee_id,
            languages=args.languages,
            primary_language=args.primary_language,
            transcript=transcript,
            loop_start=args.loop_start,
            loop_duration=args.loop_duration,
            extra_notes=args.extra_notes,
        )
    except (FileNotFoundError, PermissionError, RuntimeError) as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
