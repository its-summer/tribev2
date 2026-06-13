"""直播调度管线: 评论回复优先, 脚本段落兜底, 保持音频队列始终有存货.

调度策略:
- 音频队列里待播内容低于 BUFFER_LOW 秒时补充新内容;
- 有待回复评论时优先回复 (用评论语言), 否则生成下一段口播脚本;
- 始终保持少量缓冲而不是大量预生成, 这样评论回复的时延可控。

用法:
    python -m livehuman.pipeline personas/aria.yaml
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from .content.generator import ContentGenerator
from .interaction.tiktok_listener import TikTokCommentListener
from .persona import Persona, load_persona
from .stream.rtmp import RtmpStreamer
from .tts import router as tts
from .tts.edge import silence

logger = logging.getLogger(__name__)

BUFFER_LOW_SECONDS = 8.0   # 待播音频低于此值时生成新内容
IDLE_POLL_SECONDS = 1.0


def rtmp_url_from_env() -> str:
    url = os.environ.get("TIKTOK_RTMP_URL", "")
    key = os.environ.get("TIKTOK_STREAM_KEY", "")
    if not url:
        raise RuntimeError("请设置 TIKTOK_RTMP_URL (可选 TIKTOK_STREAM_KEY)")
    return f"{url.rstrip('/')}/{key}" if key else url


def resolve_rtmp_url(persona: Persona) -> str:
    """优先用 persona 自带的推流地址, 缺省回退到环境变量."""
    if persona.stream and (url := persona.stream.full_rtmp_url()):
        return url
    return rtmp_url_from_env()


def resolve_tiktok_id(persona: Persona) -> str | None:
    """优先用 persona 自带的监听账号, 缺省回退到环境变量."""
    if persona.stream and persona.stream.tiktok_unique_id:
        return persona.stream.tiktok_unique_id
    return os.environ.get("TIKTOK_UNIQUE_ID") or None


class LivePipeline:
    def __init__(
        self,
        persona: Persona,
        rtmp_url: str | None = None,
        tiktok_unique_id: str | None = None,
    ):
        # 显式传参优先; 否则从 persona.stream 解析, 再回退环境变量
        self.persona = persona
        self.generator = ContentGenerator(persona)
        self.streamer = RtmpStreamer(
            persona.avatar_video, rtmp_url or resolve_rtmp_url(persona)
        )
        tiktok_unique_id = tiktok_unique_id or resolve_tiktok_id(persona)
        self.listener = (
            TikTokCommentListener(tiktok_unique_id) if tiktok_unique_id else None
        )
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        # 市场护栏: 只有归属已激活市场的数字人才能开播
        from .market import ensure_market_active

        market = ensure_market_active(self.persona)
        await self.streamer.start()
        if self.listener:
            await self.listener.start()
        self._task = asyncio.create_task(self._run())
        logger.info("数字人「%s」开播 (市场: %s)", self.persona.name, market.name)

    async def _run(self) -> None:
        language = self.persona.primary_language
        while self.streamer.alive:
            if self.streamer.pending_audio_seconds > BUFFER_LOW_SECONDS:
                await asyncio.sleep(IDLE_POLL_SECONDS)
                continue
            try:
                if self.listener and not self.listener.queue.empty():
                    comment = self.listener.queue.get_nowait()
                    logger.info("回复评论 %s: %s", comment.username, comment.text)
                    text = await self.generator.reply_to_comment(
                        comment.username, comment.text
                    )
                else:
                    text = await self.generator.next_script_segment()
                logger.info("口播: %s", text)
                pcm = await tts.synthesize(self.persona, text, language)
                self.streamer.enqueue_pcm(pcm)
                # 段落间留一点自然停顿
                self.streamer.enqueue_pcm(silence(0.8))
            except Exception:
                logger.exception("生成/合成失败, %s 秒后重试", 5)
                await asyncio.sleep(5)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        if self.listener:
            await self.listener.stop()
        await self.streamer.stop()
        logger.info("数字人「%s」已下播", self.persona.name)

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()


async def main(persona_path: str) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    persona = load_persona(persona_path)
    # 推流目标与监听账号自动解析: persona.stream 优先, 回退环境变量
    pipeline = LivePipeline(persona)
    await pipeline.start()
    try:
        while pipeline.streamer.alive:
            await asyncio.sleep(1)
    finally:
        await pipeline.stop()


async def dry_run(
    persona_path: str, seconds: float = 20, out_file: str = "dryrun.mp4", segments: int = 2
) -> None:
    """本地实跑: 走完 内容生成 -> TTS -> ffmpeg 合成 整条链路, 录成本地 mp4。

    不推 TikTok、不经市场护栏 —— 用来在上线前确认链路真能跑通、音画正常。
    需要 ANTHROPIC_API_KEY (内容), 以及 persona 对应的 TTS 凭据。
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    persona = load_persona(persona_path)
    generator = ContentGenerator(persona)
    streamer = RtmpStreamer(
        persona.avatar_video, out_file, container="mp4",
        auto_restart=False, duration=seconds,
    )
    logger.info("dry-run 开始 (%ss) -> %s", seconds, out_file)
    await streamer.start()
    try:
        for _ in range(segments):
            text = await generator.next_script_segment()
            logger.info("dry-run 口播: %s", text)
            pcm = await tts.synthesize(persona, text, persona.primary_language)
            streamer.enqueue_pcm(pcm)
            streamer.enqueue_pcm(silence(0.5))
        # 等限时录制结束
        while streamer.alive:
            await asyncio.sleep(0.5)
    finally:
        await streamer.stop()
    logger.info("dry-run 完成, 用播放器检查音画: %s", out_file)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="启动直播 / 本地 dry-run")
    parser.add_argument("persona", help="persona YAML 路径")
    parser.add_argument(
        "--dry-run", type=float, metavar="SECONDS",
        help="本地录制 N 秒到 mp4, 不推 TikTok (验证链路用)",
    )
    parser.add_argument("--out", default="dryrun.mp4", help="dry-run 输出文件")
    args = parser.parse_args()

    if not Path(args.persona).exists():
        print(f"找不到 persona 文件: {args.persona}", file=sys.stderr)
        sys.exit(1)
    if args.dry_run:
        asyncio.run(dry_run(args.persona, seconds=args.dry_run, out_file=args.out))
    else:
        asyncio.run(main(args.persona))
