"""基于 Claude 的直播内容生成: 口播脚本段落 + 评论实时回复.

设计要点:
- 人设系统提示词放在最前并打 cache_control 断点, 长时直播下绝大部分输入
  token 走缓存 (~0.1x 价格)。
- 对话历史只保留最近若干段, 避免上下文无限增长。
- 回复评论用 effort=low 降低延迟, 生成脚本用默认 effort。
"""

from __future__ import annotations

import anthropic

from ..persona import Persona

MODEL = "claude-opus-4-8"

# 历史保留的最大消息数 (user/assistant 各算一条)
MAX_HISTORY = 40


def build_system_prompt(persona: Persona) -> str:
    languages = ", ".join(persona.languages)
    topics = "\n".join(f"- {t}" for t in persona.topics) or "- 自由发挥, 围绕人设闲聊"
    return f"""你是 TikTok 直播间的虚拟主播「{persona.name}」, 正在进行实时直播。

## 人设
{persona.description}

## 风格
{persona.style_notes or "自然、口语化、有亲和力。"}

## 直播话题池
{topics}

## 规则
1. 你的输出会被直接转成语音播出, 所以只输出纯口播文本: 不要任何舞台指示、
   括号动作、emoji、markdown 标记或 "主播:" 之类的前缀。
2. 主语言是 {persona.primary_language}, 你还能说: {languages}。
3. 回复观众评论时, 用评论本身的语言回答; 如果该语言不在你的支持列表里,
   用主语言回答并简单致意。
4. 每段口播控制在 2~4 句话, 像真人直播一样有停顿感, 不要长篇大论。
5. 自然地承接上一段内容, 不要重复打同样的招呼。
6. 直播开始时和每隔一段时间, 自然地提醒观众: 你是 AI 虚拟主播
   (这是平台合规要求, 但表达要自然不生硬)。
7. 不要编造商品价格、库存、优惠等不在话题池里的具体承诺。"""


class ContentGenerator:
    """维护一个 persona 的直播对话状态, 产出脚本段落与评论回复."""

    def __init__(self, persona: Persona, client: anthropic.AsyncAnthropic | None = None):
        self.persona = persona
        self.client = client or anthropic.AsyncAnthropic()
        self.system = [
            {
                "type": "text",
                "text": build_system_prompt(persona),
                "cache_control": {"type": "ephemeral"},
            }
        ]
        self.history: list[dict] = []

    async def next_script_segment(self) -> str:
        """生成下一段口播脚本."""
        prompt = (
            "继续直播。生成下一段口播。"
            if self.history
            else "直播刚刚开始, 向观众打个开场招呼并引入今天的话题。"
        )
        return await self._generate(prompt)

    async def reply_to_comment(self, username: str, comment: str) -> str:
        """针对观众评论生成口播回复 (用评论的语言)."""
        prompt = f"观众 {username} 发来评论: {comment}\n请在直播中口头回应这条评论。"
        return await self._generate(prompt, effort="low")

    async def _generate(self, prompt: str, effort: str | None = None) -> str:
        self.history.append({"role": "user", "content": prompt})
        kwargs: dict = {}
        if effort:
            kwargs["output_config"] = {"effort": effort}

        async with self.client.messages.stream(
            model=MODEL,
            max_tokens=1024,
            system=self.system,
            messages=self.history,
            **kwargs,
        ) as stream:
            message = await stream.get_final_message()

        text = "".join(b.text for b in message.content if b.type == "text").strip()
        self.history.append({"role": "assistant", "content": text})
        self._trim_history()
        return text

    def _trim_history(self) -> None:
        if len(self.history) > MAX_HISTORY:
            # 成对裁剪, 保证首条仍是 user
            self.history = self.history[-MAX_HISTORY:]
            while self.history and self.history[0]["role"] != "user":
                self.history.pop(0)
