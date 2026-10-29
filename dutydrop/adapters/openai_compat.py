"""OpenAI compatible chat completions adapter. One class serves DeepSeek (primary), and the
economical alternates: a Qwen Flash class model via OpenRouter, or a Gemini Flash class model.

DeepSeek official docs (api-docs.deepseek.com, checked 2026-10-29): model "deepseek-flash" accepts
images in user messages as image_url blocks (base64 data URL or https URL), JPEG/PNG/GIF/WebP,
about 1024 tokens per image after resizing. Base URL https://api.deepseek.com.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import List, Optional

from .. import config, prompts
from ..costs import CallRecord, Ledger, price
from .base import ModelAdapter, ModelOutputError, ProviderNotConfigured, expand_decision, normalize_description, parse_json

PROVIDERS = {
    "deepseek": ("DEEPSEEK_API_KEY", lambda: config.DEEPSEEK_BASE_URL, lambda: config.DEEPSEEK_MODEL),
    "openrouter": ("OPENROUTER_API_KEY", lambda: config.OPENROUTER_BASE_URL, lambda: config.OPENROUTER_MODEL),
    "gemini": ("GEMINI_API_KEY", lambda: config.GEMINI_BASE_URL, lambda: config.GEMINI_MODEL),
}


class OpenAICompatAdapter(ModelAdapter):
    def __init__(self, provider: str = "deepseek"):
        if provider not in PROVIDERS:
            raise ProviderNotConfigured(f"Unknown provider {provider}")
        env, base, model = PROVIDERS[provider]
        key = os.environ.get(env, "").strip()
        if not key:
            raise ProviderNotConfigured(f"No API key configured: set {env}. DutyDrop will not guess without a model.")
        if not model():
            raise ProviderNotConfigured(f"No model configured for provider {provider}")
        self.provider, self.key, self.base_url, self.model = provider, key, base().rstrip("/"), model()

    # ------------------------------------------------------------ transport
    def _chat(self, stage: str, system: str, user_content, max_tokens: int, ledger: Ledger, images: int) -> dict:
        ledger.check(stage)
        body = {"model": self.model, "max_tokens": max_tokens, "temperature": 0,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user_content}]}
        body.update(config.PROVIDER_EXTRA.get(self.provider, {}))
        req = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {self.key}"})
        try:
            with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT_S) as r:
                resp = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise ModelOutputError(f"{self.provider} HTTP {e.code}: {e.read().decode()[:300]}")
        u = resp.get("usage") or {}
        pin = int(u.get("prompt_tokens", 0))
        hit = int(u.get("prompt_cache_hit_tokens", 0) or (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0)
        out = int(u.get("completion_tokens", 0))
        ledger.add(CallRecord(stage=stage, provider=self.provider, model=resp.get("model", self.model),
                              input_tokens=pin, cached_input_tokens=hit, output_tokens=out, images=images,
                              cost_usd=str(price(pin - hit, hit, out))))
        try:
            return parse_json(resp["choices"][0]["message"]["content"])
        except (KeyError, IndexError) as e:
            raise ModelOutputError(f"{self.provider} returned no message") from e

    # ------------------------------------------------------------ Stage A
    def identify(self, image_urls: List[str], user_text: Optional[str], ledger: Ledger) -> dict:
        content = [{"type": "text", "text": "User description: " + (user_text or "(none)")}]
        for u in image_urls:            # all photos in ONE call (cost rule 2)
            content.append({"type": "image_url", "image_url": {"url": u}})
        raw = self._chat("identify", prompts.IDENTIFY_SYSTEM, content, config.MAX_TOKENS_IDENTIFY, ledger, len(image_urls))
        return normalize_description(raw)

    # ------------------------------------------------------------ Stage C reasoning
    def decide(self, description: dict, shortlist: List[dict], ledger: Ledger) -> dict:
        payload = {"product": {k: description.get(k) for k in ("product_name", "materials", "function_and_use",
                                                                "form_and_construction", "power_source", "cannot_tell", "user_text")},
                   "candidates": [{"code": c["code"], "line": c["description"][:220],
                                   "under": c["path"][:max(0, len(c["path"]) - len(c["description"]))][-160:]}
                                  for c in shortlist]}
        return expand_decision(self._chat("decide", prompts.DECIDE_SYSTEM, json.dumps(payload, separators=(",", ":")),
                                          config.MAX_TOKENS_DECIDE, ledger, 0))


def get_adapter(provider: Optional[str] = None) -> ModelAdapter:
    return OpenAICompatAdapter(provider or config.PROVIDER)
