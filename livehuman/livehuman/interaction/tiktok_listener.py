"""TikTok 直播间评论监听: 基于 TikTokLive 库 (无需官方 API).

把评论事件投递到 asyncio 队列, 由 Pipeline 消费。队列设上限,
互动高峰时丢弃旧评论, 避免回复永远追不上。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MAX_PENDING_COMMENTS = 20


@dataclass
class Comment:
    username: str
    text: str


class TikTokCommentListener:
    """监听 @unique_id 直播间的评论流."""

    def __init__(self, unique_id: str):
        self.unique_id = unique_id
        self.queue: asyncio.Queue[Comment] = asyncio.Queue(maxsize=MAX_PENDING_COMMENTS)
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        # 延迟导入: 不开互动功能时无需安装 TikTokLive
        from TikTokLive import TikTokLiveClient
        from TikTokLive.events import CommentEvent

        client = TikTokLiveClient(unique_id=self.unique_id)

        @client.on(CommentEvent)
        async def on_comment(event: CommentEvent) -> None:
            comment = Comment(username=event.user.nickname, text=event.comment)
            try:
                self.queue.put_nowait(comment)
            except asyncio.QueueFull:
                self.queue.get_nowait()  # 丢最旧的, 收最新的
                self.queue.put_nowait(comment)

        self._task = asyncio.create_task(client.start())
        logger.info("开始监听 TikTok 直播间 @%s 的评论", self.unique_id)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
