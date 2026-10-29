"""Stage E: receipt JSON emitter (Spec 3E). Tier masking, flags, disclaimer, version stamp.
Rendering the 1080x1350 share card consumes this JSON; no model calls here."""
from __future__ import annotations

import json
import re
from typing import List, Optional

from . import config
from .data import display_code

ANONYMOUS, FREE_ACCOUNT = "anonymous", "free_account"
DOMAIN_RE = re.compile(r"\b(?:https?://)?(?:[a-z0-9-]+\.)+(?:com|co|org|net|gov|io|ai|us|info|biz|app|dev)\b(?:/\S*)?", re.I)


def mask(d: str) -> str:
    """Chapter and heading shown, remainder masked: 9405.XX.XXXX"""
    return f"{d[:4]}.XX.XXXX" if len(d) == 10 else f"{d[:4]}.XX.XX"


def scrub_domains(obj):
    """dutydrop.co is the only public link on any output."""
    if isinstance(obj, str):
        return DOMAIN_RE.sub(lambda m: m.group(0) if m.group(0).lower().rstrip("/") == config.PUBLIC_LINK else "[link removed]", obj)
    if isinstance(obj, list):
        return [scrub_domains(x) for x in obj]
    if isinstance(obj, dict):
        return {k: scrub_domains(v) for k, v in obj.items()}
    return obj


def build(classification: dict, estimate: Optional[dict], tier: str, photo_preview: Optional[str],
          origin: Optional[str], value: Optional[str], data_label: str) -> dict:
    assigned = classification.get("assigned_code")
    cands = classification.get("candidates") or []
    full = tier == FREE_ACCOUNT
    rec = {
        "product_label": classification.get("product_label") or "",
        "photo": photo_preview,
        "photo_refs": classification.get("photo_refs", []),
        "origin": origin, "customs_value": value,
        "entry_date": (estimate or {}).get("entry_date"),
        "tier": tier,
        "hts": None,
        "candidates": None,
        "duty": None,
        "confidence_band": classification.get("confidence_band"),
        "flags": [],
        "disclaimer": config.DISCLAIMER,
        "data_version": data_label,
        "link": config.PUBLIC_LINK,
        "audit_id": classification.get("audit_id"),
    }
    if assigned:
        rec["hts"] = {"code": display_code(assigned) if full else mask(assigned), "masked": not full}
    else:
        rec["candidates"] = [{"code": display_code(c["code"]) if full else mask(c["code"]),
                              "description": c["description"][:120]} for c in cands[:3]]
        rec["broker_route"] = config.BROKER_ROUTE
        rec["flags"].append({"flag": "no_assigned_code"})
    if estimate:
        rec["duty"] = {k: estimate[k] for k in ("line_items", "alternative_items", "scenarios", "base_total",
                                                "total", "provisional_total", "landed", "mode")}
        if not full:     # the full code must not leak through line references
            for item in rec["duty"]["line_items"] + rec["duty"]["alternative_items"]:
                item.pop("mapping", None)
        rec["flags"] += estimate["flags"]
    if classification.get("cost_cap_hit"):
        rec["flags"].append({"flag": "cost_cap"})
    rec = scrub_domains(rec)
    rec["link"] = config.PUBLIC_LINK
    return rec


def contains_foreign_domain(rec: dict) -> List[str]:
    found = []
    for m in DOMAIN_RE.finditer(json.dumps(rec)):
        if m.group(0).lower().rstrip("/") != config.PUBLIC_LINK:
            found.append(m.group(0))
    return found
