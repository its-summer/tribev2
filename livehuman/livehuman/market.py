"""市场 (Market) 配置: 按市场组织本土员工数字人, 控制开放节奏.

每个市场登记代码、名称、母语、状态。只有 status=active 的市场允许开播;
其他市场设 coming_soon, 随业务扩张逐步激活。本土员工按母语录制, 其数字人
通过 persona 的 market 字段归属到对应市场。

当前仅日本 (jp) 激活, 后续市场陆续放开。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from .persona import Persona, list_personas

DEFAULT_MARKETS_FILE = Path(__file__).parent.parent / "markets.yaml"


class Market(BaseModel):
    code: str = Field(description="市场代码, 如 jp / us / es")
    name: str = Field(description="市场名称, 如 日本")
    language: str = Field(description="该市场母语/直播语言, 如 ja")
    status: Literal["active", "coming_soon"] = Field(
        default="coming_soon", description="active=可开播; coming_soon=预留未开放"
    )
    note: str = ""

    @property
    def is_active(self) -> bool:
        return self.status == "active"


def load_markets(path: str | Path = DEFAULT_MARKETS_FILE) -> dict[str, Market]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    markets = [Market.model_validate(m) for m in data.get("markets", [])]
    return {m.code: m for m in markets}


def get_market(code: str, path: str | Path = DEFAULT_MARKETS_FILE) -> Market:
    markets = load_markets(path)
    if code not in markets:
        known = ", ".join(markets) or "(无)"
        raise KeyError(f"未知市场: {code}。已登记市场: {known}")
    return markets[code]


def personas_by_market(
    personas_dir: str | Path,
    markets_file: str | Path = DEFAULT_MARKETS_FILE,
) -> dict[str, list[str]]:
    """按市场代码汇总归属的 persona 名称 (文件名)."""
    result: dict[str, list[str]] = {code: [] for code in load_markets(markets_file)}
    for name, persona in list_personas(personas_dir).items():
        result.setdefault(persona.market, []).append(name)
    return result


def ensure_market_active(persona: Persona, markets_file: str | Path = DEFAULT_MARKETS_FILE) -> Market:
    """开播前的市场护栏: persona 必须归属一个已激活市场, 否则拒绝."""
    if not persona.market:
        raise PermissionError(
            f"数字人「{persona.name}」未归属任何市场, 无法开播 (请在 persona 设置 market)"
        )
    market = get_market(persona.market, markets_file)
    if not market.is_active:
        raise PermissionError(
            f"市场「{market.name}」({market.code}) 尚未开放 (status={market.status}), "
            f"暂不能开播。当前仅开放已激活市场。"
        )
    return market
