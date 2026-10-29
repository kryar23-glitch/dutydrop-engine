"""Stage D: deterministic duty calculator (Spec 3D). No model calls. All arithmetic here.

Lines are computed at full precision and each displayed amount is rounded half up to cents.
Any total shown equals the sum of the displayed lines it covers.
"""
from __future__ import annotations

import datetime as dt
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional

from . import config, status
from .data import HTSData, digits, display_code

CENT = Decimal("0.01")
CURRENT, HISTORICAL = "current", "historical"


def money(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def _dec(s) -> Optional[Decimal]:
    try:
        return Decimal(str(s)) if str(s).strip() not in ("", "None") else None
    except Exception:
        return None


# ---------------------------------------------------------------- rate parsing
SPEC_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(¢|\$)\s*/\s*([A-Za-z0-9.]+)")
PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
UNIT_ALIASES = {"kg": "kg", "kilogram": "kg", "kilograms": "kg", "liter": "liter", "liters": "liter", "l": "liter",
                "doz": "doz", "dozen": "doz", "each": "no", "no": "no", "no.": "no", "unit": "no", "units": "no",
                "pcs": "no", "pieces": "no", "pr": "pr", "pair": "pr", "pairs": "pr", "m2": "m2", "m": "m",
                "head": "head", "gross": "gross", "kg.": "kg", "proof liter": "pf.liter", "pf.liter": "pf.liter"}


def _unit(u: str) -> str:
    return UNIT_ALIASES.get((u or "").strip().lower(), (u or "").strip().lower())


def rate_amount(rate_text: str, value: Decimal, qty: Optional[Decimal], qty_unit: Optional[str]):
    """Returns (amount or None, basis text, partial flag reason or None). Never converts a
    specific rate into a percentage."""
    t = (rate_text or "").strip()
    tl = t.lower()
    if not t:
        return None, "No rate in data", "no_rate_in_data"
    if tl == "free":
        return Decimal(0), "Free", None
    specs = SPEC_RE.findall(t)
    pcts = PCT_RE.findall(t)
    if not specs and pcts and re.fullmatch(r"\s*\d+(?:\.\d+)?\s*%\s*", t):
        r = Decimal(pcts[0]) / 100
        return value * r, f"{pcts[0]}% ad valorem", None
    if specs:
        if qty is None or not qty_unit:
            return None, t, "quantity_needed_for_specific_rate"
        total = Decimal(0)
        for amt, cur, unit in specs:
            if _unit(unit) != _unit(qty_unit):
                return None, t, f"quantity_unit_mismatch: rate is per {unit}, quantity given in {qty_unit}"
            per = Decimal(amt) / (100 if cur == "¢" else 1)
            total += per * qty
        rest = SPEC_RE.sub("", t)
        for p in PCT_RE.findall(rest):
            total += value * Decimal(p) / 100
        if re.search(r"[a-z]{4,}", SPEC_RE.sub("", PCT_RE.sub("", t)).lower().replace("+", "")):
            return None, t, "rate_text_not_machine_readable"
        return total, t, None
    return None, t, "rate_text_not_machine_readable"


# ---------------------------------------------------------------- overlays
_CONDITIONAL = re.compile(r"determined by|transship|in transit|loaded onto a vessel|personal use|donation|"
                          r"informational materials|for use in|of a kind used|entered under|temporary importation", re.I)


def country_wide_kind(cat: dict) -> str:
    """'origin' when the heading reaches every product of an origin; 'described' when the text
    limits it to goods described in words (not mapped to codes, so it cannot be priced)."""
    desc = cat["Description"]
    m = re.search(r"\b(?:the )?products? of\b", desc)
    if not m:
        return "described"
    prefix = desc[:m.start()]
    last = prefix.split(",")[-1].strip().lower()
    last = re.sub(r".*\d{4}\.\d{2}\.\d{2}\s*", "", last)
    last = re.sub(r"^(?:all|and|or)\s+", "", last)
    return "origin" if last in ("", "articles", "articles that are", "all", "products") else "described"


def _column2_only(cat: dict) -> bool:
    return "general note 3(b)" in cat["Description"].lower()


def _overlay_rows(data: HTSData, code: str, origin: str, mode: str) -> List[dict]:
    """Product specific overlays for this code and origin, plus country wide overlays."""
    rows = []
    if mode == CURRENT:
        for r in data.active_by_hts.get(code, []):            # primary join table (Spec 3D.4)
            rows.append({"heading": r["Ch99 Heading"], "country": r["Country of Origin"], "source": "active_by_hts",
                         "method": r["Mapping Method"]})
    else:
        seen = set()
        for L in (4, 6, 8, 10):                                  # all statuses, for recovery mode
            for r in data.coverage_by_cited.get(code[:L], []):
                if r["Ch99 Heading"] in seen:
                    continue
                seen.add(r["Ch99 Heading"])
                rows.append({"heading": r["Ch99 Heading"], "country": r["Country of Origin"], "source": "coverage",
                             "method": r["Mapping Method"]})
    for c in data.country_wide:
        rows.append({"heading": c["Ch99 Heading"], "country": c["Country of Origin"], "source": "country_wide",
                     "method": "All products of origin", "cw_kind": country_wide_kind(c)})
    out, seen = [], set()
    for r in rows:
        if r["heading"] in seen or not status.origin_matches(r["country"], origin):
            continue
        cat = data.catalog.get(r["heading"])
        if not cat or not cat["Ch99 Heading"].startswith("9903"):
            continue       # 9902 reductions, 9904 quotas, FTA subchapters: not applied as duties
        if _column2_only(cat) and origin not in data.column2_origins:
            continue
        r["conditional"] = bool(_CONDITIONAL.search(cat["Description"]))
        seen.add(r["heading"])
        r["cat"] = cat
        out.append(r)
    return out


EXEMPT_WORDS = {"steel": ["steel", "iron"], "aluminum": ["aluminum"], "copper": ["copper"],
                "civil aircraft": ["aircraft"], "pharmaceutical": ["pharmaceutical", "medicament"],
                "vehicle": ["vehicle", "automobile"], "wood": ["wood", "timber", "lumber"],
                "semiconductor": ["semiconductor"]}


def _word_exemptions(data: HTSData, base_row: dict, origin: str, programs: set, on: dt.date) -> List[dict]:
    text = (base_row["Full Description Path"] + " " + base_row["Description"]).lower()
    flags = []
    for c in data.described_exemptions:
        if c["Program"] not in programs or not status.origin_matches(c["Country of Origin"], origin):
            continue
        if not status.in_effect(c, on):
            continue
        d = c["Description"].lower()
        hit = [k for k, ws in EXEMPT_WORDS.items() if any(w in d for w in ws) and any(w in text for w in ws)]
        if hit:
            flags.append({"flag": "may_be_exempt", "label": config.MAY_BE_EXEMPT_LABEL, "heading": c["Ch99 Heading"],
                          "program": c["Program"], "reason": f"Exemption written in words covers {', '.join(hit)}",
                          "text": c["Description"][:240]})
    return flags


# ---------------------------------------------------------------- main entry
def estimate(data: HTSData, code: str, origin: str, value, entry_date: Optional[dt.date] = None,
             mode: str = CURRENT, quantity=None, quantity_unit: Optional[str] = None,
             today: Optional[dt.date] = None) -> dict:
    today = today or dt.date.today()
    entry_date = entry_date or today
    d = digits(code)
    row = data.base.get(d)
    if row is None:
        raise ValueError(f"HTS code {code} is not in the {data.label} base table")
    if len(d) < 8:
        raise ValueError(f"HTS code {code} is not a tariff line; give an 8 or 10 digit line")
    value = Decimal(str(value))
    qty = _dec(quantity)
    flags, lines, alternatives, scenarios = [], [], [], []
    o = status.norm_origin(origin)

    # 1 and 3: base or Column 2
    col2 = o in data.column2_origins
    if col2:
        rate_text, label = row["Column 2 Rate"], "Column 2 duty"
        basis_ref = "Column 2 rate; origin listed in General Note 3(b)"
    else:
        rate_text, label = row["General Rate (Col 1)"], "Base duty (general rate)"
        basis_ref = "General rate, Column 1"
    amt, basis, partial = rate_amount(rate_text, value, qty, quantity_unit)
    inherited = row["General Rate Source"].startswith("Inherited") and not col2
    lines.append({"label": label, "kind": "base", "basis": basis, "reference": basis_ref,
                  "rate_source": row["General Rate Source"] if not col2 else "Column 2",
                  "amount": str(money(amt)) if amt is not None else None})
    if inherited:
        flags.append({"flag": "inherited_rate", "detail": row["General Rate Source"]})
    if partial:
        flags.append({"flag": "partial", "reason": partial})

    # 2: special programs as scenarios or flags, never substituted
    if o in ("mexico", "canada") and not col2:
        ua, ub, up = rate_amount(row["USMCA Rate"], value, qty, quantity_unit)
        scenarios.append({"label": config.USMCA_SCENARIO_LABEL, "basis": ub or "No USMCA rate in data",
                          "base_duty_if_qualifies": str(money(ua)) if ua is not None else None,
                          "partial_reason": up})
        flags.append({"flag": "usmca_scenario_shown"})
    prog_flags = [k for k in row if k.endswith(")") and "(" in k and row[k] == "Y" and not k.startswith("USMCA")]
    if prog_flags:
        flags.append({"flag": "special_program_codes", "programs": prog_flags,
                      "detail": "Eligibility not collected; rates not applied"})

    # 4: overlays, status as of entry date
    excluded = []
    for r in _overlay_rows(data, d, o, mode):
        cat = r["cat"]
        if mode == CURRENT:
            applies = status.in_effect(cat, entry_date) and not status.ended_by(cat, today)
            hflags = []
        else:
            applies, hflags = status.in_effect_historical(cat, entry_date)
        if not applies:
            if status.in_effect_historical(cat, entry_date)[0] and mode == CURRENT:
                excluded.append({"heading": cat["Ch99 Heading"], "program": cat["Program"],
                                 "reason": "ended or expired as of today; see recovery mode"})
            continue
        rate = _dec(cat["Duty Rate"])
        effect = cat["Effect"]
        if r.get("cw_kind") == "described":
            flags.append({"flag": "possible_overlay_described_in_words", "heading": cat["Ch99 Heading"],
                          "program": cat["Program"], "status": cat["Status"],
                          "reason": "Applies only to goods described in the heading text; not mapped to codes",
                          "text": cat["Description"][:240]})
            continue
        item = {"label": f"{cat['Program']} ({cat['Ch99 Heading']})", "heading": cat["Ch99 Heading"],
                "program": cat["Program"], "origin_label": cat["Country of Origin"] or "All origins",
                "effect": effect, "status": cat["Status"], "mapping": r["method"], "flags": hflags}
        if r.get("conditional"):
            item["flags"] = item["flags"] + ["conditional: applies only to goods meeting the heading text"]
        if effect == "Additional ad valorem" and rate is not None and r.get("conditional"):
            item.update(kind="conditional", basis=f"{(rate * 100).normalize()}% additional, only if the heading conditions are met",
                        amount=str(money(value * rate)))
            alternatives.append(item)
        elif effect == "Additional ad valorem" and rate is not None:
            item.update(kind="overlay", basis=f"{(rate * 100).normalize()}% additional ad valorem",
                        amount=str(money(value * rate)))
            lines.append(item)
        elif effect.startswith("Exemption"):
            item.update(kind="exemption", basis="Possible exemption, no additional duty", amount="0.00")
            alternatives.append(item)
        elif effect.startswith("Rate in lieu") and rate is not None:
            item.update(kind="in_lieu", basis=f"{(rate * 100).normalize()}% in lieu of base, if it applies",
                        amount=str(money(value * rate)))
            alternatives.append(item)
        else:
            item.update(kind="unpriced", basis=cat["General Duty Text"] or "See heading text", amount=None)
            alternatives.append(item)
            flags.append({"flag": "partial", "reason": f"overlay {cat['Ch99 Heading']} has no machine readable rate"})
        if mode == HISTORICAL:
            rule = config.STATUS_RULES.get(cat["Program"])
            if rule and rule.get("refund_note") and status.ended_by(cat, today):
                item["refund_eligibility_candidate"] = rule["refund_note"]
                flags.append({"flag": "refund_eligibility_candidate", "heading": cat["Ch99 Heading"],
                              "program": cat["Program"]})
        if cat["Program"].startswith("Other: U.S. note"):
            item["authority_label_note"] = "Legal authority not named in the note text; label kept generic"

    # 6: word defined exemptions
    programs = {l["program"] for l in lines + alternatives if l.get("program")}
    flags += _word_exemptions(data, row, o, programs, entry_date)
    if o in ("mexico", "canada") and programs:
        flags.append({"flag": "may_be_exempt", "label": config.MAY_BE_EXEMPT_LABEL,
                      "reason": "USMCA qualifying goods are exempt from some overlays; qualification not collected"})

    # 5: stacking guardrail and 8: reconciled totals
    overlay_lines = [l for l in lines if l["kind"] == "overlay"]
    priced = [l for l in lines if l["amount"] is not None]
    has_partial = any(f["flag"] == "partial" for f in flags)
    stacking_open = len(overlay_lines) > 1 or bool(alternatives) or any(f["flag"] == "may_be_exempt" for f in flags)
    shown_sum = sum((Decimal(l["amount"]) for l in priced), Decimal(0))
    result = {
        "code": d, "display_code": display_code(d), "origin": origin, "customs_value": str(money(value)),
        "entry_date": entry_date.isoformat(), "mode": mode, "data_version": data.label,
        "line_items": lines, "alternative_items": alternatives, "scenarios": scenarios,
        "excluded_overlays": excluded, "flags": flags,
        "base_total": lines[0]["amount"], "total": None, "provisional_total": None, "landed": None,
        "source_rows": {"base": {"HTS Code": row["HTS Code"], "HTS Digits": d,
                                 "General Rate Source": row["General Rate Source"]},
                        "overlays": [l["heading"] for l in overlay_lines + alternatives]},
    }
    if has_partial and lines[0]["amount"] is None:
        result["flags"].append({"flag": "no_total", "reason": "base duty cannot be computed without more input"})
    elif stacking_open:
        result["provisional_total"] = {"label": config.PROVISIONAL_LABEL, "amount": str(shown_sum),
                                       "covers": [l["label"] for l in priced]}
        result["flags"].append({"flag": "stacking_provisional"})
    elif has_partial:
        result["provisional_total"] = {"label": "Partial total, some lines could not be priced",
                                       "amount": str(shown_sum), "covers": [l["label"] for l in priced]}
    else:
        result["total"] = str(shown_sum)
        result["landed"] = str(money(value) + shown_sum)
    return result
