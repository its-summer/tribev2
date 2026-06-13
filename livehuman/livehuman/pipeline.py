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
from pathlib import Path

from .content.generator import ContentGenerator
from .interaction.tiktok_listener import TikTokCommentListener
from .persona import Persona, load_persona
from .stream.rtmp import RtmpStreamer
from .tts import edge as tts

logger = logging.getLogger(__name__)

BUFFER_LOW_SECONDS = 8.0   # 待播音频低于此值时生成新内容
IDLE_POLL_SECONDS = 1.0


def rtmp_url_from_env() -> str:
    url = os.environ.get("TIKTOK_RTMP_URL", "")
    key = os.environ.get("TIKTOK_STREAM_KEY", "")
    if not url:
        raise RuntimeError("请设置 TIKTOK_RTMP_URL (可选 TIKTOK_STREAM_KEY)")
    return f"{url.rstrip('/')}/{key}" if key else url


class LivePipeline:
    def __init__(
        self,
        persona: Persona,
        rtmp_url: str,
        tiktok_unique_id: str | None = None,
    ):
        self.persona = persona
        self.generator = ContentGenerator(persona)
        self.streamer = RtmpStreamer(persona.avatar_video, rtmp_url)
        self.listener = (
            TikTokCommentListener(tiktok_unique_id) if tiktok_unique_id else None
        )
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        await self.streamer.start()
        if self.listener:
            await self.listener.start()
        self._task = asyncio.create_task(self._run())
        logger.info("数字人「%s」开播", self.persona.name)

    async def _run(self) -> None:
        voice = self.persona.voice_for(self.persona.primary_language)
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
                pcm = await tts.synthesize(text, voice)
                self.streamer.enqueue_pcm(pcm)
                # 段落间留一点自然停顿
                self.streamer.enqueue_pcm(tts.silence(0.8))
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
    pipeline = LivePipeline(
        persona,
        rtmp_url=rtmp_url_from_env(),
        tiktok_unique_id=os.environ.get("TIKTOK_UNIQUE_ID") or None,
    )
    await pipeline.start()
    try:
        while pipeline.streamer.alive:
            await asyncio.sleep(1)
    finally:
        await pipeline.stop()


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print(f"用法: python -m livehuman.pipeline <persona.yaml>", file=sys.stderr)
        sys.exit(1)
    if not Path(sys.argv[1]).exists():
        print(f"找不到 persona 文件: {sys.argv[1]}", file=sys.stderr)
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
