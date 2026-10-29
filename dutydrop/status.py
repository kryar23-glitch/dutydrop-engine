"""Date aware overlay status (Spec 2.5) and origin matching.

An overlay is in effect on an entry date when start <= date < end. Program windows come from
config.STATUS_RULES. Line level dates come from the data: a compiler's note date, an
"effective through" date, or an "on or after" date in the heading text. When a date the decision
needs is not in the data, the result carries a flag instead of a guess.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import List, Optional

from . import config

_MONTH = r"(January|February|March|April|May|June|July|August|September|October|November|December)"


def _parse_date(text: str, pattern: str) -> Optional[dt.date]:
    m = re.search(pattern, text or "")
    if not m:
        return None
    try:
        return dt.datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y").date()
    except ValueError:
        return None


def _close_of(text: str) -> Optional[dt.date]:
    m = re.search(r"close of ([A-Z][a-z]{2,8})\.? (\d{1,2}),? (\d{4})", text or "")
    if not m:
        return None
    try:
        d = dt.datetime.strptime(f"{m.group(1)[:3]} {m.group(2)} {m.group(3)}", "%b %d %Y").date()
        return d + dt.timedelta(days=1)
    except ValueError:
        return None


@dataclass
class Window:
    start: Optional[dt.date]
    end: Optional[dt.date]               # exclusive
    start_known: bool
    end_known: bool
    basis: str
    flags: List[str] = field(default_factory=list)


def window(cat: dict) -> Window:
    prog = cat.get("Program", "")
    status = cat.get("Status", "")
    basis_text = cat.get("Status Basis", "")
    desc = cat.get("Description", "")
    start = _parse_date(desc, r"on or after " + _MONTH + r" (\d{1,2}),? (\d{4})")
    end = None
    rule = config.STATUS_RULES.get(prog)
    basis = basis_text or status
    if rule:
        start = rule["start"] or start
        end = rule["end"]
        basis = rule["basis"]
    if status.startswith("Active through"):
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", status)
        if m:
            end = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) + dt.timedelta(days=1)
    elif status in ("Terminated", "Suspended", "Expired"):
        end = _parse_date(basis_text, r"as of " + _MONTH + r" (\d{1,2}),? (\d{4})") or _close_of(basis_text)
        m = re.search(r"effective through (\d{4})-(\d{2})-(\d{2})", basis_text)
        if m:
            end = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) + dt.timedelta(days=1)
        if end is None:
            end = dt.date.min   # ended on a date the data does not give
    w = Window(start=start, end=end, start_known=start is not None,
               end_known=end not in (None, dt.date.min), basis=basis)
    if not w.start_known:
        w.flags.append("start_date_not_in_data")
    if end == dt.date.min:
        w.flags.append("end_date_not_in_data")
    return w


def in_effect(cat: dict, on: dt.date) -> bool:
    w = window(cat)
    if w.end == dt.date.min:
        return False
    if w.start and on < w.start:
        return False
    if w.end and on >= w.end:
        return False
    return True


def ended_by(cat: dict, today: dt.date) -> bool:
    w = window(cat)
    return w.end is not None and today >= w.end


def in_effect_historical(cat: dict, on: dt.date) -> tuple:
    """For recovery mode: (applies, flags). A line whose end date is unknown is surfaced, flagged."""
    w = window(cat)
    flags = list(w.flags)
    if w.end == dt.date.min:
        return True, flags + ["verify_in_effect_on_entry_date"]
    if w.start and on < w.start:
        return False, flags
    if w.end and on >= w.end:
        return False, flags
    if not w.start_known:
        flags.append("verify_in_effect_on_entry_date")
    return True, flags


# ---------------------------------------------------------------- origins
def norm_origin(o: str) -> str:
    o = (o or "").strip().lower()
    o = config.ORIGIN_ALIASES.get(o, o)
    return o


_EU = {m.lower() for m in config.EU_MEMBERS}


def origin_matches(label: str, origin: str) -> bool:
    """Does an overlay's Country of Origin label cover this origin?"""
    lab = (label or "").strip().lower()
    o = norm_origin(origin)
    if lab in ("", "any country"):
        return True
    if lab == o:
        return True
    if lab == "european union":
        return o in _EU or o == "european union"
    parts = [x.strip() for x in re.split(r"\band\b|,", lab) if x.strip()]
    if o in parts:
        return True
    if config.ORIGIN_ALIASES.get(lab) == o or norm_origin(lab) == o:
        return True
    return False


def origin_is_named(label: str, origin: str) -> bool:
    """True only when the label names this origin (not a blanket any country label)."""
    lab = (label or "").strip().lower()
    return lab not in ("", "any country") and origin_matches(label, origin)
