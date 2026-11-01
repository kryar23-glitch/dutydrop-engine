"""Receipt gate rules R1 to R8 (lexicon/rules/GATE_RULES.md).

calculator.estimate() is deliberately cautious: any second overlay, any possible exemption and any
unpriced line leaves the total provisional. This module applies the HTSUS Rev 21 note text to turn
the cases the notes already settle into a firm total, and prints every assumption it makes.

    from dutydrop import gate
    receipt = gate.firm_receipt(data, code, origin, value, quantity=None, unit_price=None)

Returns the calculator result with: total (firm, or None when a seller input is truly required),
assumptions (lines to print), notes (lines to print), scenarios and dropped (what was removed and why).
"""
from __future__ import annotations

import os
import re
from decimal import Decimal
from functools import lru_cache
from typing import Optional

from . import calculator as C, config
from .data import HTSData

# R1 (overlay lines): headings that need an importer certification of end use
END_USE_HEADINGS = {"9903.94.07"}   # note 33(p): parts certified for U.S. automobile production or repair
# R11: transitional headings for goods already in transit on a past date
IN_TRANSIT = re.compile(r"exported to the United States before", re.I)

# R1: exemptions that depend on an end use or industry the seller has not stated
END_USE = re.compile(r"civil aircraft|pharmaceutical|for sowing|ground flight simulators|personal use|donation|"
                     r"informational materials|accompanied baggage", re.I)

@lru_cache(maxsize=1)
def _note16():
    import json
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifests", "note16_lists_2026_Rev21.json")
    return json.load(open(p)) if os.path.exists(p) else {}


def note16_subdivisions(code: str):
    """The U.S. note 16(c) lists that name this code, by the longest matching prefix."""
    d = C.digits(code)
    hits = [(len(p), k) for k, v in _note16().items() for p in v if d.startswith(p)]
    if not hits:
        return []
    top = max(h[0] for h in hits)
    return sorted({k for n, k in hits if n == top})


@lru_cache(maxsize=1)
def _group_countries(ch99_path: str) -> dict:
    """R2: map 9903 headings to the countries named in the group header above them ("Articles the
    product of Japan:"), for headings whose catalog row leaves the country blank."""
    out = {}
    if not os.path.exists(ch99_path):
        return out
    lines = open(ch99_path, encoding="utf-8", errors="ignore").read().splitlines()
    current, since = None, 999
    i = 0
    while i < len(lines):
        line = lines[i]
        h = re.match(r"\s*(9903\.\d\d\.\d\d)\b", line)
        if not h and "Articles the product of" in line:
            text = line.split("Articles the product of", 1)[1]
            j = i
            while ":" not in text and j < i + 6:
                j += 1
                text += " " + lines[j].strip()
            current, since = re.sub(r"\s+", " ", text.split(":")[0]).strip(), 0
            i = j + 1
            continue
        if h and current and since < 150:
            out.setdefault(h.group(1), current)
        since += 1
        i += 1
    return out


def _ch99_path() -> str:
    return os.path.join(config.DATA_DIR, "ch99.txt")


def _applies_to_origin(heading: str, origin: str, data: HTSData = None) -> bool:
    if data is not None and (data.catalog.get(heading, {}).get("Country of Origin") or "").strip():
        return True        # the catalog already names the country; the calculator filtered on it
    countries = _group_countries(_ch99_path()).get(heading)
    if not countries:
        return True
    return origin.lower() in countries.lower()


def firm_receipt(data: HTSData, code: str, origin: str, value, quantity=None, quantity_unit: Optional[str] = None,
                 unit_price=None, metal_under_15pct: Optional[bool] = None, usmca: bool = False,
                 quartz_surface: bool = False, **kw) -> dict:
    value = Decimal(str(value))
    row = data.base.get(C.digits(code)) or {}
    unit = (row.get("Unit of Quantity") or "").strip().rstrip(".").lower() or None
    assumptions, notes, scenarios, dropped = [], [], [], []

    # R8: compound rates need a quantity; derive it from a stated unit price when given
    if quantity is None and unit_price:
        per = {"doz": 12, "gross": 144}.get(unit or "", 1)
        quantity = (value / Decimal(str(unit_price)) / per).quantize(Decimal("0.0001"))
        quantity_unit = unit
        assumptions.append(f"Assumes {value / Decimal(str(unit_price)):.0f} units at ${Decimal(str(unit_price)):.2f} each.")

    r = C.estimate(data, code, origin, value, quantity=quantity, quantity_unit=quantity_unit or unit, **kw)
    o = origin.strip().lower()

    keep_alts = []
    for a in r["alternative_items"]:
        cat = data.catalog.get(a["heading"], {})
        desc = cat.get("Description", "")
        if a["kind"] == "exemption" and END_USE.search(desc):                       # R1
            dropped.append((a["heading"], "end-use exemption not claimed"))
        elif not _applies_to_origin(a["heading"], o, data):                               # R2
            dropped.append((a["heading"], "heading limited to other countries"))
        elif a["kind"] == "exemption" and cat.get("Program", "").startswith("Section 301 China"):   # R3
            dropped.append((a["heading"], "USTR product exclusion, not applied by default"))
            if "A USTR product exclusion" not in " ".join(notes):
                notes.append("A USTR product exclusion may apply if your product matches the exclusion text exactly.")
        elif a["heading"] in ("9903.45.30", "9903.45.31") and not quartz_surface:      # R9 note 41(a)
            dropped.append((a["heading"], "note 41(a): quartz surface products only"))
            if "quartz surface" not in " ".join(notes):
                notes.append("If this is a quartz surface product (silica and resin slab, countertop or tile), a 25% or 50% safeguard duty applies.")
        elif a["kind"] == "exemption" and a["heading"].startswith("9903.82"):     # R7 low metal
            dropped.append((a["heading"], "metal weight exemption shown as scenario"))
        else:
            keep_alts.append(a)
    lines = []
    for l in r["line_items"]:
        h = l.get("heading", "")
        if l.get("kind") != "overlay":
            lines.append(l)
        elif not _applies_to_origin(h, o, data):                                          # R2
            dropped.append((h, "heading limited to other countries"))
        elif h in END_USE_HEADINGS:                                                       # R1
            dropped.append((h, "needs an importer end-use certification"))
        elif IN_TRANSIT.search(data.catalog.get(h, {}).get("Description", "")):           # R11
            dropped.append((h, "transitional heading for goods in transit on a past date"))
        elif not listed_for(h, code, data):                                               # R10
            dropped.append((h, "code is not on the note list this heading cites"))
        else:
            lines.append(l)
    keep_alts = [a for a in keep_alts if listed_for(a["heading"], code, data) and a["heading"] not in END_USE_HEADINGS
                 and not IN_TRANSIT.search(data.catalog.get(a["heading"], {}).get("Description", ""))]

    # R7: Section 232 metals. Note 16(a): exactly one 9903.82 heading per article, chosen by the note 16(c)
    # list that names the code. (i)-(v) 50 percent; (vi)-(viii) and (xi) 25 percent; (ix)-(x) a 15 percent
    # floor (heading 9903.82.10 or .11), because imports do not meet the U.S. melt rules of note 16(e).
    # Codes on no list owe no metals duty, whatever headings the overlay join attached.
    metal_rows = [x for x in lines if x.get("heading", "").startswith("9903.82")]
    for x in metal_rows:
        lines.remove(x)
    keep_alts = [a for a in keep_alts if not a["heading"].startswith("9903.82")]
    subs = note16_subdivisions(code)
    metal_line = None
    if subs:
        d = C.digits(code)
        base_amt = Decimal(lines[0]["amount"]) if lines and lines[0].get("amount") is not None else None
        base_rate = (base_amt / value) if base_amt is not None and value else None
        if set(subs) & {"i", "ii", "iii", "iv", "v"}:
            heading, rate = "9903.82.02", Decimal("0.50")
        elif set(subs) & {"vi", "vii", "viii", "xi"}:
            heading, rate = "9903.82.09", Decimal("0.25")
        else:
            if base_rate is None:
                heading, rate = "9903.82.10", None
            elif base_rate < Decimal("0.15"):
                heading, rate = "9903.82.10", Decimal("0.15") - base_rate
            else:
                heading, rate = "9903.82.11", Decimal(0)
        weight_rule = not d.startswith(("72", "73", "74", "76"))
        if weight_rule and metal_under_15pct:
            dropped.append(("9903.82", "metal under 15 percent of weight, as stated"))
        elif rate is not None:
            cat = data.catalog.get(heading, {})
            metal_line = {"label": f"Section 232 metals ({heading})", "heading": heading, "program": cat.get("Program", ""),
                          "kind": "overlay", "basis": f"{(rate * 100).normalize()}% additional ad valorem on full value",
                          "amount": str(C.money(value * rate)), "effect": cat.get("Effect", ""), "flags": []}
            lines.append(metal_line)
            if weight_rule:
                assumptions.append("Assumes steel, aluminum or copper is at least 15% of the product's weight.")
                scenarios.append({"label": "If metal is under 15% of weight", "remove": [heading]})
        else:
            notes.append("Section 232 metals duty is a 15% floor; it needs the base duty, which needs a quantity.")
    else:
        dropped += [(x["heading"], "code is on no U.S. note 16 list") for x in metal_rows]

    # R5: note 52 country duties do not apply to goods under Section 232 (note 52(f))
    s232 = [x for x in lines if x.get("heading", "").startswith(("9903.82", "9903.76", "9903.74", "9903.94", "9903.79"))]
    if s232:
        for x in [x for x in lines if x.get("heading", "").startswith("9903.05")]:
            lines.remove(x)
            dropped.append((x["heading"], "note 52(f): not applied to Section 232 goods"))

    # R12: note 52(b) and 52(c) exempt listed articles from the country duties (headings 9903.05.86, 9903.05.87)
    exempt52 = [h for h, sub in (("9903.05.86", "b"), ("9903.05.87", "c"))
                if any(C.digits(code).startswith(x) for x in note_list_codes(52, sub))]
    if exempt52:
        for x in [x for x in lines if "9903.05.20" <= x.get("heading", "") <= "9903.05.84"]:
            lines.remove(x)
            dropped.append((x["heading"], f"note 52 exemption {exempt52[0]}: listed article"))
        keep_alts = [a for a in keep_alts if a["heading"] not in exempt52]
        notes.append(f"Exempt from the country duty under heading {exempt52[0]} (U.S. note 52 list).")

    # R6: Mexico USMCA is a scenario, not an open stack
    mx = [l for l in lines if l.get("heading") == "9903.05.55"]
    if o == "mexico":
        if usmca and mx:
            for l in mx:
                lines.remove(l)
                dropped.append((l["heading"], "USMCA qualifying, note 52(h)"))
        elif mx:
            scenarios.append({"label": "If USMCA qualifying", "remove": [l["heading"] for l in mx]})

    remaining_open = [a for a in keep_alts if a["kind"] in ("in_lieu", "unpriced", "conditional")]
    partial = [f for f in r["flags"] if f["flag"] == "partial"]
    priced = [l for l in lines if l.get("amount") is not None]
    total = None
    if not partial and not remaining_open and lines and lines[0].get("amount") is not None:
        total = str(sum((Decimal(l["amount"]) for l in priced), Decimal(0)))        # R4: stacked lines add
    r.update(line_items=lines, alternative_items=remaining_open, total=total,
             landed=str(C.money(value) + Decimal(total)) if total else None,
             assumptions=assumptions, notes=notes, scenarios=r["scenarios"] + scenarios, dropped=dropped,
             needs=[f.get("reason") for f in partial] + [a["heading"] for a in remaining_open])
    return r


@lru_cache(maxsize=1)
def _ch99_lines():
    p = _ch99_path()
    return open(p, encoding="utf-8", errors="ignore").read().split("\n") if os.path.exists(p) else []


@lru_cache(maxsize=512)
def note_list_codes(note: int, sub: str):
    """R10: the HTS codes enumerated in U.S. note <note>(<sub>), as digit strings. Empty when the
    subdivision is narrative (no code list) or cannot be found."""
    lines = _ch99_lines()
    start = next((i for i, l in enumerate(lines) if re.match(rf"\s*{note}\.\s*\(a\)", l)
                  or (re.match(rf"\s*{note}\.\s*$", l) and any("(a)" in x for x in lines[i + 1:i + 4]))), None)
    if start is None:
        return ()
    end = next((i for i in range(start + 1, len(lines)) if re.match(rf"\s*{note + 1}\.\s*(\(a\))?\s", lines[i])), len(lines))
    # top-level subdivisions: "(x)" near the margin followed by a capitalized sentence
    top = re.compile(r"^(?:\s*\d+\.)?\s{0,12}\(([a-z]{1,2})\)\s+[A-Z]")
    heads = [(i, m.group(1)) for i in range(start, end) for m in [top.match(lines[i])] if m]
    pos, chosen = -1, {}
    for k in range(ord("a"), ord(sub) + 2):
        ch = chr(k)
        nxt = next(((i, c) for i, c in heads if i > pos and c == ch), None)
        if nxt is not None:
            chosen[ch], pos = nxt[0], nxt[0]
    if sub not in chosen:
        return ()
    s = chosen[sub]
    e = chosen.get(chr(ord(sub) + 1), end)
    text = "\n".join(lines[s:e])
    return tuple(sorted({c.replace(".", "") for c in re.findall(r"\b\d{4}\.\d{2}(?:\.\d{2,4})?\b", text)
                         if not c.startswith(("98", "99"))}))


def listed_for(heading: str, code: str, data: HTSData) -> bool:
    """True unless the heading's own note subdivision lists codes and this code is not among them."""
    refs = (data.catalog.get(heading, {}).get("Note References") or "")
    m = re.fullmatch(r"\s*note (\d+)\(([a-z])\)\s*", refs)
    if not m or (data.catalog.get(heading, {}).get("Scope") or "") != "Product list":
        return True
    codes = note_list_codes(int(m.group(1)), m.group(2))
    if not codes:
        return True
    d = C.digits(code)
    return any(d.startswith(c) for c in codes)
