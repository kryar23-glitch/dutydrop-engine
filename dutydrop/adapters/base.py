"""Model adapter interface (Spec 3A). Swap providers without touching downstream stages."""
from __future__ import annotations

import json
import re
from typing import List, Optional

from ..costs import Ledger

DESCRIPTION_KEYS = ["product_name", "search_terms", "materials", "function_and_use", "parts_and_components",
                    "form_and_construction", "visible_text_and_labels", "power_source", "attribute_confidence",
                    "cannot_tell"]


class ProviderNotConfigured(RuntimeError):
    """Raised when no API key is configured. The engine never falls back to guessing."""


class ModelOutputError(RuntimeError):
    pass


def parse_json(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ModelOutputError("model returned no JSON object")
        try:
            return json.loads(m.group(0))
        except ValueError as e:
            raise ModelOutputError(f"model returned malformed JSON: {e}")


def expand_decision(raw: dict) -> dict:
    """Accept the compact decide format {"s":[[code,i,m,f,c]],"q":[[attr,question]]}."""
    if "scores" in raw:
        return raw
    scores = []
    for row in raw.get("s") or []:
        if isinstance(row, list) and len(row) >= 5:
            scores.append({"code": str(row[0]), "identity": row[1], "material": row[2], "function": row[3],
                           "construction": row[4], "supports": [], "contradicts": []})
    qs = [{"attribute": str(q[0]), "question": str(q[1])} for q in raw.get("q") or [] if isinstance(q, list) and len(q) >= 2]
    return {"scores": scores, "questions": qs}


def normalize_description(d: dict) -> dict:
    """Coerce to the Stage A schema. Drops anything that looks like a tariff code."""
    out = {
        "product_name": str(d.get("product_name") or ""),
        "search_terms": [str(x) for x in (d.get("search_terms") or [])][:15],
        "materials": [],
        "function_and_use": str(d.get("function_and_use") or ""),
        "parts_and_components": [str(x) for x in (d.get("parts_and_components") or [])][:10],
        "form_and_construction": str(d.get("form_and_construction") or ""),
        "visible_text_and_labels": [str(x) for x in (d.get("visible_text_and_labels") or [])][:10],
        "power_source": d.get("power_source") if d.get("power_source") not in ("", "null") else None,
        "attribute_confidence": {k: float((d.get("attribute_confidence") or {}).get(k, 0) or 0)
                                 for k in ("materials", "function", "identity")},
        "cannot_tell": [str(x) for x in (d.get("cannot_tell") or [])][:10],
    }
    if d.get("user_text"):
        out["user_text"] = str(d["user_text"])[:600]
    for m in d.get("materials") or []:
        if isinstance(m, dict):
            out["materials"].append({"material": str(m.get("material", "")), "confidence": float(m.get("confidence") or 0)})
        elif isinstance(m, str):
            out["materials"].append({"material": m, "confidence": 0.5})
    code_like = re.compile(r"\b\d{4}\.\d{2}(\.\d{2,4})?\b|\b\d{8,10}\b")
    out["search_terms"] = [t for t in out["search_terms"] if not code_like.search(t)]
    return out


class ModelAdapter:
    provider = "base"
    model = ""

    def identify(self, image_urls: List[str], user_text: Optional[str], ledger: Ledger) -> dict:
        raise NotImplementedError

    def decide(self, description: dict, shortlist: List[dict], ledger: Ledger) -> dict:
        raise NotImplementedError
