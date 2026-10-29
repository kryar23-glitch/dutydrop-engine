"""Stage B: retrieval against the local HTS index (Spec 3B). Runs in code; zero model spend.

BM25 full text search over Description and Full Description Path for leaf lines, then
progressive narrowing chapter -> heading -> subheading -> leaf. Every candidate carries match
evidence (supporting and contradicting attributes) and the database row it came from.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List

from .data import HTSData, display_code

STOP = set("""a an and or of the for to in on with without by from as at is are be not other than
such kind kinds used use whether thereof therein which that this these those its their each
any all nesoi n e s i parts part articles article goods products product type types""".split())

MATERIALS = {
    "plastic": ["plastic", "plastics", "polymer", "polyethylene", "polypropylene", "pvc", "acrylic", "nylon"],
    "rubber": ["rubber", "silicone", "elastomer"],
    "leather": ["leather"],
    "wood": ["wood", "wooden", "bamboo", "timber", "plywood"],
    "paper": ["paper", "paperboard", "cardboard"],
    "cotton": ["cotton"],
    "wool": ["wool"],
    "silk": ["silk"],
    "manmade fiber": ["synthetic", "polyester", "man", "manmade", "fiber", "fibers"],
    "glass": ["glass"],
    "ceramic": ["ceramic", "porcelain", "china", "stoneware", "earthenware"],
    "iron or steel": ["iron", "steel", "stainless"],
    "aluminum": ["aluminum", "aluminium"],
    "copper": ["copper", "brass", "bronze"],
    "precious metal": ["gold", "silver", "platinum"],
    "stone": ["stone", "marble", "granite", "concrete"],
}


# Consumer words that the tariff schedule spells differently. Extend as the golden set grows.
SYNONYMS = {"lamp": ["luminaire", "lighting fitting"], "light": ["luminaire"], "tshirt": ["t-shirt"],
            "sneaker": ["footwear"], "shoe": ["footwear"], "phone": ["telephone"], "laptop": ["automatic data processing"],
            "couch": ["seat"], "sofa": ["seat"], "mug": ["tableware"], "toy": ["toys"], "bag": ["handbag", "container"]}


def stem(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith("es") and not w.endswith("ses"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def tokens(text: str) -> List[str]:
    return [stem(w) for w in re.findall(r"[a-z]+", (text or "").lower()) if w not in STOP and len(w) > 1]


@dataclass
class Candidate:
    code: str                      # digits
    display: str
    description: str
    path: str
    bm25: float
    evidence: Dict[str, List[str]] = field(default_factory=dict)   # attribute -> matched terms
    contradicts: List[str] = field(default_factory=list)
    lexical: Dict[str, float] = field(default_factory=dict)        # attribute -> 0..1
    source_row: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"code": self.code, "display": self.display, "description": self.description,
                "path": self.path, "bm25": round(self.bm25, 4), "evidence": self.evidence,
                "contradicts": self.contradicts, "lexical": {k: round(v, 3) for k, v in self.lexical.items()},
                "source_row": self.source_row}


class Index:
    K1, B = 1.4, 0.75

    def __init__(self, data: HTSData):
        self.data = data
        self.docs: Dict[str, Counter] = {}
        self.len: Dict[str, int] = {}
        self.inv: Dict[str, Dict[str, float]] = defaultdict(dict)
        for d in data.leaves:
            r = data.base[d]
            tf = Counter()
            for t in tokens(r["Description"]):
                tf[t] += 2.0
            for t in tokens(r["Full Description Path"]):
                tf[t] += 1.0
            self.docs[d] = tf
            self.len[d] = sum(tf.values())
            for t, v in tf.items():
                self.inv[t][d] = v
        self.N = len(self.docs)
        self.avg = sum(self.len.values()) / max(self.N, 1)
        self.idf = {t: math.log(1 + (self.N - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.inv.items()}

    def search(self, query_terms: List[str], limit: int = 60, weights: Dict[str, float] = None) -> List[tuple]:
        q = Counter()
        for t in query_terms:
            for tok in tokens(t):
                q[tok] += (weights or {}).get(t, 1.0)
        scores = defaultdict(float)
        for t, qw in q.items():
            post = self.inv.get(t)
            if not post:
                continue
            idf = self.idf[t]
            for d, tf in post.items():
                norm = tf * (self.K1 + 1) / (tf + self.K1 * (1 - self.B + self.B * self.len[d] / self.avg))
                scores[d] += qw * idf * norm
        return sorted(scores.items(), key=lambda x: -x[1])[:limit]


def attribute_terms(desc: dict) -> Dict[str, List[str]]:
    mats = [m.get("material", "") for m in desc.get("materials", []) if (m.get("confidence") or 0) >= 0.4]
    return {
        "identity": [desc.get("product_name", "")] + list(desc.get("search_terms", [])),
        "material": mats,
        "function": [desc.get("function_and_use", "")] + ([desc["power_source"]] if desc.get("power_source") else []),
        "construction": [desc.get("form_and_construction", "")] + list(desc.get("parts_and_components", [])),
    }


def _material_classes(words: set) -> set:
    return {cls for cls, ws in MATERIALS.items() if any(stem(w) in words for w in ws)}


def retrieve(index: Index, desc: dict, pool: int = 60, shortlist: int = 10) -> List[Candidate]:
    attrs = attribute_terms(desc)
    weights = {}
    for t in attrs["identity"]:
        weights[t] = 3.0
    for t in attrs["function"]:
        weights[t] = 1.5
    for t in attrs["material"]:
        weights[t] = 1.5
    for t in attrs["construction"]:
        weights[t] = 0.8
    query = [t for ts in attrs.values() for t in ts if t]
    for t in list(attrs["identity"]):
        for w in re.findall(r"[a-z]+", (t or "").lower()):
            for syn in SYNONYMS.get(stem(w), []):
                query.append(syn)
                weights[syn] = 2.0
    raw = index.search(query, limit=pool * 8, weights=weights)
    if not raw:
        return []
    # diversify: at most 4 lines per heading, so one crowded heading cannot hide the right one
    per_heading, hits = defaultdict(int), []
    for d, s in raw:
        if per_heading[d[:4]] < 4:
            per_heading[d[:4]] += 1
            hits.append((d, s))
        if len(hits) >= pool:
            break
    # progressive narrowing: keep the strongest chapters, then headings, then subheadings
    def narrow(hits, L, keep):
        agg = defaultdict(float)
        for d, s in hits:
            agg[d[:L]] = max(agg[d[:L]], s) + 0.1 * s
        top = set(sorted(agg, key=lambda k: -agg[k])[:keep])
        return [(d, s) for d, s in hits if d[:L] in top]
    hits = narrow(hits, 2, 4)
    hits = narrow(hits, 4, 6)
    hits = narrow(hits, 6, 10)
    # final shortlist: at most 3 lines per heading so rival headings stay in view
    per_h, picked = defaultdict(int), []
    for d, s in hits:
        if per_h[d[:4]] < 3:
            per_h[d[:4]] += 1
            picked.append((d, s))
        if len(picked) >= shortlist:
            break
    hits = picked

    attr_tokens = {a: set(tok for t in ts for tok in tokens(t)) for a, ts in attrs.items()}
    id_mats = _material_classes(attr_tokens["material"])
    out = []
    for d, s in hits:
        r = index.data.base[d]
        words = set(tokens(r["Description"] + " " + r["Full Description Path"]))
        ev, lex = {}, {}
        for a, toks in attr_tokens.items():
            m = sorted(toks & words)
            ev[a] = m
            lex[a] = (len(m) / len(toks)) if toks else 0.0
        contra = []
        cand_mats = _material_classes(words)
        if id_mats and cand_mats and not (id_mats & cand_mats):
            contra.append(f"material: line names {sorted(cand_mats)}, photo suggests {sorted(id_mats)}")
        out.append(Candidate(code=d, display=display_code(d), description=r["Description"],
                             path=r["Full Description Path"], bm25=s, evidence=ev, contradicts=contra,
                             lexical=lex, source_row={"HTS Code": r["HTS Code"], "HTS Digits": d,
                                                      "General Rate (Col 1)": r["General Rate (Col 1)"],
                                                      "General Rate Source": r["General Rate Source"]}))
    return out
