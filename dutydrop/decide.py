"""Stage C: score candidates and decide: assign, ask, or loop (Spec 3C).

The reasoning model sees only the shortlist (top 10, truncated). It scores attribute
agreement; code blends those scores with lexical evidence, weights the attributes that
separate the surviving candidates, and applies configurable thresholds. The validation gate
rejects any code the model returns that is not in the shortlist or not in the base table.
"""
from __future__ import annotations

from typing import Dict, List

from . import config
from .adapters.base import ModelAdapter, ModelOutputError
from .costs import CostCapReached, Ledger
from .data import HTSData
from .retrieval import Candidate, Index, retrieve

ATTRS = ("identity", "material", "function", "construction")
STRONG, MARGINAL, WEAK = "strong", "marginal", "weak"


def band(score: float) -> str:
    if score >= config.BAND_HIGH:
        return "High"
    if score >= config.BAND_MEDIUM:
        return "Medium"
    return "Low"


def _clip(x) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.0


def score_round(data: HTSData, index: Index, adapter: ModelAdapter, desc: dict, ledger: Ledger) -> dict:
    cands: List[Candidate] = retrieve(index, desc, pool=config.RETRIEVE_POOL, shortlist=config.SHORTLIST_SIZE)
    result = {"candidates": [], "rejected_codes": [], "model_questions": [], "model_used": False,
              "cost_cap_hit": False, "outcome": WEAK, "top": None, "margin": 0.0}
    if not cands:
        return result
    short_codes = {c.code for c in cands}
    model_scores: Dict[str, dict] = {}
    try:
        raw = adapter.decide(desc, [c.to_dict() for c in cands], ledger)
        result["model_used"] = True
        for s in raw.get("scores", []) or []:
            code = "".join(ch for ch in str(s.get("code", "")) if ch.isdigit())
            if code not in short_codes or not data.exists(code):        # hard validation gate
                result["rejected_codes"].append(str(s.get("code")))
                continue
            model_scores[code] = s
        for q in (raw.get("questions") or [])[:3]:
            if isinstance(q, dict) and q.get("question"):
                result["model_questions"].append({"attribute": str(q.get("attribute", "other")),
                                                  "question": str(q["question"])[:200]})
    except CostCapReached:
        result["cost_cap_hit"] = True
    except ModelOutputError as e:
        result["model_error"] = str(e)

    # blend model and lexical evidence per attribute
    per = {}
    for c in cands:
        m = model_scores.get(c.code)
        vals = {}
        for a in ATTRS:
            lex = c.lexical.get(a, 0.0)
            vals[a] = (config.MODEL_WEIGHT * _clip(m.get(a)) + config.LEXICAL_WEIGHT * lex) if m else lex
        per[c.code] = (vals, m)
    # weight toward attributes that separate the surviving candidates
    spread = {a: (max(v[a] for v, _ in per.values()) - min(v[a] for v, _ in per.values())) for a in ATTRS}
    w = {a: config.ATTRIBUTE_WEIGHTS[a] * (0.5 + spread[a]) for a in ATTRS}
    tw = sum(w.values()) or 1.0
    conf = desc.get("attribute_confidence") or {}
    scored = []
    for c in cands:
        vals, m = per[c.code]
        s = sum(w[a] * vals[a] for a in ATTRS) / tw
        s -= 0.1 * len(c.contradicts)
        if m and m.get("contradicts"):
            s -= 0.05 * min(len(m["contradicts"]), 2)
        s *= 0.6 + 0.4 * _clip(conf.get("identity", 0.5))      # low identity confidence caps the score
        s = max(0.0, min(1.0, s))
        d = c.to_dict()
        d.update({"score": round(s, 4), "attribute_scores": {a: round(vals[a], 3) for a in ATTRS},
                  "weights": {a: round(w[a] / tw, 3) for a in ATTRS},
                  "model_supports": (m or {}).get("supports", []), "model_contradicts": (m or {}).get("contradicts", [])})
        scored.append(d)
    scored.sort(key=lambda x: -x["score"])
    result["candidates"] = scored
    top = scored[0]["score"]
    second = scored[1]["score"] if len(scored) > 1 else 0.0
    result["top"], result["margin"] = top, round(top - second, 4)
    if top >= config.STRONG_SCORE and (top - second) >= config.STRONG_MARGIN:
        result["outcome"] = STRONG
    elif top >= config.MARGINAL_SCORE:
        result["outcome"] = MARGINAL
    else:
        result["outcome"] = WEAK
    return result


def marginal_questions(result: dict) -> List[dict]:
    """Only questions that discriminate between surviving candidates."""
    qs = list(result.get("model_questions") or [])
    if not qs:
        top = result["candidates"][:3]
        if len({tuple(sorted(c["evidence"].get("material", []))) for c in top}) > 1 or any(c["contradicts"] for c in top):
            qs.append({"attribute": "material", "question": "What is it mainly made of?"})
        qs.append({"attribute": "function", "question": "What is it used for, and how is it powered (if at all)?"})
    for i, q in enumerate(qs):
        q["id"] = f"q{i + 1}"
    return qs[:3]


def weak_questions() -> List[dict]:
    return [
        {"id": "describe", "attribute": "description",
         "question": "In your own words: what is it, what is it for, and what is it made of?"},
        {"id": "photo", "attribute": "photo",
         "question": "Can you add another photo: a different angle, the label or spec tag, or the product in use?"},
    ]
