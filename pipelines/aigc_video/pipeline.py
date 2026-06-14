#!/usr/bin/env python3
"""AIGC 带货视频管线编排器。

读 shots.json，按阶段执行：frames -> video -> voice -> stitch。
每阶段产物回写 shots.json，支持断点续跑与 --only 单阶段。

dry-run（离线，仅 python3）：
    python3 pipeline.py example_shots.json --dry-run
真实生成（需出网 + ffmpeg + 环境变量）：
    python3 pipeline.py example_shots.json --out ./output
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clients import openai_image, seedance_volc, tts  # noqa: E402
import stitch  # noqa: E402

STAGES = ["frames", "video", "voice", "stitch"]


def load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def save(path: str, data: dict) -> None:
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def stage_frames(doc: dict, out: str, dry: bool) -> None:
    print("\n[1/4] frames — 逐镜首帧文生图 (gpt-image-1)")
    if dry:
        print(f"  client: {openai_image.describe()}")
    for s in doc["shots"]:
        prompt = s.get("first_frame_prompt") or s.get("action", "")
        dst = os.path.join(out, f"shot{s['id']}_frame.png")
        if dry:
            print(f"  镜{s['id']}: -> {dst}\n      prompt: {prompt[:80]}")
            s["first_frame_image"] = dst
            continue
        s["first_frame_image"] = openai_image.generate_frame(prompt, out_path=dst)
        print(f"  镜{s['id']} ✓ {dst}")


def stage_video(doc: dict, out: str, dry: bool) -> None:
    print("\n[2/4] video — 逐镜图生视频 (火山 Seedance)")
    if dry:
        print(f"  client: {seedance_volc.describe()}")
    for s in doc["shots"]:
        dst = os.path.join(out, f"shot{s['id']}.mp4")
        if dry:
            print(f"  镜{s['id']}: {s.get('first_frame_image','?')} -> {dst} "
                  f"({s.get('duration',5)}s {doc.get('aspect_ratio','9:16')})")
            s["video_clip"] = dst
            continue
        # 注意：火山图生视频需首帧图为可公网访问 URL，正式跑前先上传对象存储
        url = s.get("first_frame_url") or s["first_frame_image"]
        s["video_clip"] = seedance_volc.image_to_video(
            url, s.get("action", ""), duration=s.get("duration", 5),
            ratio=doc.get("aspect_ratio", "9:16"), out_path=dst)
        print(f"  镜{s['id']} ✓ {dst}")


def stage_voice(doc: dict, out: str, dry: bool) -> None:
    print("\n[3/4] voice — 旁白 TTS (OpenAI)")
    if dry:
        print(f"  client: {tts.describe()}")
    lines = [s.get("voiceover") for s in doc["shots"] if s.get("voiceover")]
    if not lines:
        print("  (无旁白文本，跳过)")
        return
    script = " ".join(lines)
    dst = os.path.join(out, "voice.mp3")
    if dry:
        print(f"  -> {dst}\n      文本: {script[:80]}...")
        doc["voice_track"] = dst
        return
    doc["voice_track"] = tts.synthesize(script, out_path=dst)
    print(f"  ✓ {dst}")


def stage_stitch(doc: dict, out: str, dry: bool) -> None:
    print("\n[4/4] stitch — ffmpeg 拼接 + 旁白 + BGM")
    if not dry and not stitch.has_ffmpeg():
        print("  ⚠️ 未检测到 ffmpeg，跳过。请先安装 ffmpeg。")
        return
    clips = [s["video_clip"] for s in doc["shots"] if s.get("video_clip")]
    merged = os.path.join(out, "_merged.mp4")
    final = os.path.join(out, f"{doc.get('project','final')}.mp4")
    stitch.run(stitch.build_concat_cmd(clips, merged, os.path.join(out, "_concat.txt")), dry)
    stitch.run(stitch.build_mux_cmd(merged, doc.get("voice_track"), doc.get("bgm"), final), dry)
    doc["final_video"] = final
    print(f"  成片 -> {final}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("shots", help="shots.json 路径")
    ap.add_argument("--out", default="./output", help="产物目录")
    ap.add_argument("--dry-run", action="store_true", help="离线验证流程，不调用 API")
    ap.add_argument("--only", choices=STAGES, help="只跑某一阶段")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    doc = load(args.shots)
    print(f"项目: {doc.get('project')} | 镜头数: {len(doc['shots'])} | "
          f"市场: {doc.get('market')} | {'DRY-RUN' if args.dry_run else 'LIVE'}")

    todo = [args.only] if args.only else STAGES
    fns = {"frames": stage_frames, "video": stage_video,
           "voice": stage_voice, "stitch": stage_stitch}
    for st in todo:
        fns[st](doc, args.out, args.dry_run)

    save(args.shots, doc)
    print(f"\n完成。shots.json 已更新产物路径。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
