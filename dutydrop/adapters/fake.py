"""Scripted adapter for tests. Never used in production paths; usage numbers are simulated
from the spec's reference call sizes and marked simulated=True in the cost report."""
from __future__ import annotations

from typing import Callable, List, Optional

from ..costs import CallRecord, Ledger, price
from .base import ModelAdapter, normalize_description

SIM = {"identify": (1000, 450), "decide": (1800, 300), "headings": (1200, 20)}


class FakeAdapter(ModelAdapter):
    provider = "fake"
    model = "scripted"

    def __init__(self, descriptions: List[dict], decide_fn: Optional[Callable] = None):
        self.descriptions = list(descriptions)
        self.decide_fn = decide_fn or (lambda desc, shortlist: {"scores": [], "questions": []})
        self.identify_calls = 0
        self.decide_calls = 0
        self.last_images = []

    def _bill(self, stage, ledger, images=0):
        ledger.check(stage)
        tin, tout = SIM[stage]
        ledger.add(CallRecord(stage=stage, provider=self.provider, model=self.model, input_tokens=tin,
                              cached_input_tokens=0, output_tokens=tout, images=images,
                              cost_usd=str(price(tin, 0, tout)), simulated=True))

    def identify(self, image_urls, user_text, ledger: Ledger) -> dict:
        self._bill("identify", ledger, len(image_urls))
        self.identify_calls += 1
        self.last_images = image_urls
        d = self.descriptions[min(self.identify_calls - 1, len(self.descriptions) - 1)]
        return normalize_description(d(user_text) if callable(d) else d)

    def decide(self, description, shortlist, ledger: Ledger) -> dict:
        self._bill("decide", ledger)
        self.decide_calls += 1
        return self.decide_fn(description, shortlist)
