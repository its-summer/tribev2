"""用 Claude 从员工的讲解文字稿中提炼数字人人设.

输出三块内容 (结构化):
- description: 这位员工的人设画像 (身份、专业领域、性格气质)
- style_notes: 他的说话风格 (口头禅、节奏、表达习惯), 让数字人"像他本人"
- topics: 从讲解中提取的产品知识点, 作为直播话题池 —— 数字人只讲
  员工真正讲过的卖点, 从源头避免直播时编造参数和承诺
"""

from __future__ import annotations

import anthropic
from pydantic import BaseModel, Field

MODEL = "claude-opus-4-8"


class PersonaDraft(BaseModel):
    description: str = Field(description="员工的人设画像, 2~4 句")
    style_notes: str = Field(description="说话风格要点: 口头禅、语气、节奏")
    topics: list[str] = Field(description="从讲解中提取的产品知识点/卖点, 每条一句话")


def analyze_style(
    employee_name: str,
    transcript: str,
    extra_notes: str = "",
    client: anthropic.Anthropic | None = None,
) -> PersonaDraft:
    client = client or anthropic.Anthropic()
    prompt = f"""以下是员工「{employee_name}」录制的产品讲解视频的文字稿。
请据此提炼 ta 的数字人直播人设。

要求:
- description 描述 ta 的身份与气质, 以 ta 的真实讲解为依据, 不要虚构经历;
- style_notes 总结 ta 的真实语言习惯 (口头禅、句式、节奏), 数字人要"像 ta 本人";
- topics 提取文字稿里实际出现的产品知识点和卖点, 忠于原话的事实,
  不要添加文字稿里没有的参数、价格或承诺。

{f"补充信息: {extra_notes}" if extra_notes else ""}

<transcript>
{transcript}
</transcript>"""

    response = client.messages.parse(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        output_format=PersonaDraft,
    )
    return response.parsed_output
