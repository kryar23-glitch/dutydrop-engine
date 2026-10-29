"""Cost accounting and the per receipt cost cap (Spec 3A cost rules 1, 7, 8)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List

from . import config


class CostCapReached(RuntimeError):
    pass


def price(input_miss: int, input_hit: int, output: int) -> Decimal:
    m = Decimal(1_000_000)
    return (Decimal(input_miss) * config.PRICE_INPUT_PER_M / m
            + Decimal(input_hit) * config.PRICE_INPUT_CACHED_PER_M / m
            + Decimal(output) * config.PRICE_OUTPUT_PER_M / m)


@dataclass
class CallRecord:
    stage: str
    provider: str
    model: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    images: int
    cost_usd: str
    simulated: bool = False

    def to_dict(self):
        return dict(self.__dict__)


@dataclass
class Ledger:
    cap: Decimal = field(default_factory=lambda: config.COST_CAP_PER_RECEIPT)
    calls: List[CallRecord] = field(default_factory=list)
    cap_hit: bool = False

    @property
    def total(self) -> Decimal:
        return sum((Decimal(c.cost_usd) for c in self.calls), Decimal(0))

    def check(self, stage: str) -> None:
        """Raise before a call whose projected cost would cross the cap."""
        tin, tout = config.PROJECTED_TOKENS.get(stage, (2000, 500))
        if self.total + price(tin, 0, tout) > self.cap:
            self.cap_hit = True
            raise CostCapReached(f"cost cap {self.cap} USD reached before {stage}")

    def add(self, rec: CallRecord) -> None:
        self.calls.append(rec)

    def to_dict(self) -> dict:
        return {"calls": [c.to_dict() for c in self.calls], "total_usd": str(self.total),
                "cap_usd": str(self.cap), "cap_hit": self.cap_hit,
                "prices_verified": config.PRICES_VERIFIED,
                "price_per_m": {"input": str(config.PRICE_INPUT_PER_M), "input_cached": str(config.PRICE_INPUT_CACHED_PER_M),
                                "output": str(config.PRICE_OUTPUT_PER_M)}}
