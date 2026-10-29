"""Data loader and in memory index (Spec section 2).

Revision agnostic: files are located by pattern, so a new HTS revision drop built by
build_hts.py / build_overlays.py loads without code changes. Load time assertions compare
row counts against the revision manifest in dutydrop/manifests/<revision>.json, which
tools/make_manifest.py writes for each new drop.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import config


def _rj(path):
    with open(path) as fh:
        return json.load(fh)


BASE_PAT = "US_HTS_Database_{rev}_database.csv"
CATALOG_PAT = "US_Tariff_Overlays_{rev}_catalog.csv"
COVERAGE_PAT = "US_Tariff_Overlays_{rev}_coverage.csv"
ACTIVE_PAT = "US_Tariff_Overlays_{rev}_active_by_hts.csv"
COLUMN2_PAT = "US_General_Note3b_Column2_{rev}.csv"
MANIFEST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifests")


class DataLoadError(RuntimeError):
    pass


def digits(code: str) -> str:
    return re.sub(r"\D", "", code or "")


def display_code(d: str) -> str:
    """Standard display form: 4.2.4 for 10 digits (8504.40.9580), 4.2.2 for 8."""
    if len(d) == 10:
        return f"{d[:4]}.{d[4:6]}.{d[6:]}"
    if len(d) == 8:
        return f"{d[:4]}.{d[4:6]}.{d[6:]}"
    if len(d) == 6:
        return f"{d[:4]}.{d[4:]}"
    return d


def revision_label(rev: str) -> str:
    m = re.match(r"(\d{4})_Rev(\d+)", rev)
    return f"HTS {m.group(1)} Rev {m.group(2)}" if m else f"HTS {rev}"


def find_revisions(data_dir: str) -> List[str]:
    revs = []
    for p in glob.glob(os.path.join(data_dir, "US_HTS_Database_*_database.csv")):
        m = re.search(r"US_HTS_Database_(.+)_database\.csv$", os.path.basename(p))
        if m:
            revs.append(m.group(1))

    def key(r):
        m = re.match(r"(\d{4})_Rev(\d+)", r)
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    return sorted(revs, key=key)


def _read(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        raise DataLoadError(f"Missing data file: {path}")
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@dataclass
class HTSData:
    revision: str
    label: str
    base: Dict[str, dict]                      # digits -> base row
    leaves: List[str]                          # leaf codes (10 digit, or 8 digit without children)
    catalog: Dict[str, dict]                   # ch99 heading (dotted) -> catalog row
    coverage_by_cited: Dict[str, List[dict]]   # cited code digits -> coverage rows
    active_by_hts: Dict[str, List[dict]]       # leaf digits -> active rows
    country_wide: List[dict]                   # catalog rows with all products scope (all statuses)
    described_exemptions: List[dict]           # catalog rows exempting goods described in words
    column2_origins: List[str]                 # normalized origin names from General Note 3(b)
    counts: Dict[str, int] = field(default_factory=dict)
    country_labels: List[str] = field(default_factory=list)

    def row(self, code: str) -> Optional[dict]:
        return self.base.get(digits(code))

    def exists(self, code: str) -> bool:
        return digits(code) in self.base


def load(data_dir: Optional[str] = None, revision: Optional[str] = None, check: bool = True) -> HTSData:
    data_dir = data_dir or config.DATA_DIR
    revs = find_revisions(data_dir)
    if not revs:
        raise DataLoadError(f"No HTS revision found in {data_dir}")
    rev = revision or config.DATA_REVISION or revs[-1]
    if rev not in revs:
        raise DataLoadError(f"Revision {rev} not found in {data_dir}; found {revs}")
    p = lambda pat: os.path.join(data_dir, pat.format(rev=rev))

    base_rows = _read(p(BASE_PAT))
    cat_rows = _read(p(CATALOG_PAT))
    cov_rows = _read(p(COVERAGE_PAT))
    act_rows = _read(p(ACTIVE_PAT))
    col2_rows = _read(p(COLUMN2_PAT))

    base = {}
    for r in base_rows:
        base[r["HTS Digits"]] = r
    tens = {d[:8] for d in base if len(d) == 10}
    leaves = [d for d in base if not d.startswith("99") and (len(d) == 10 or (len(d) == 8 and d not in tens))]

    catalog = {r["Ch99 Heading"]: r for r in cat_rows}
    cov = defaultdict(list)
    for r in cov_rows:
        cov[r["Cited Base Code"]].append(r)
    act = defaultdict(list)
    for r in act_rows:
        act[r["HTS Digits"]].append(r)
    country_wide = [r for r in cat_rows if r["Scope"] in ("All products of country", "All products")]
    described = [r for r in cat_rows if r["Scope"].startswith("Described goods")]
    labels = sorted({r["Country of Origin"] for r in cat_rows if r["Country of Origin"]})

    data = HTSData(
        revision=rev, label=revision_label(rev), base=base, leaves=leaves, catalog=catalog,
        coverage_by_cited=dict(cov), active_by_hts=dict(act), country_wide=country_wide,
        described_exemptions=described, column2_origins=[r["Origin"].strip().lower() for r in col2_rows],
        counts={"base": len(base_rows), "catalog": len(cat_rows), "coverage": len(cov_rows),
                "active_by_hts": len(act_rows), "country_wide": len(country_wide)},
        country_labels=labels,
    )
    if check:
        assert_manifest(data)
    return data


def section301_list_counts(data: HTSData) -> Dict[str, int]:
    heads = {"List 1": "9903.88.01", "List 2": "9903.88.02", "List 3": "9903.88.03", "List 4A": "9903.88.15"}
    return {k: int(data.catalog[h]["Codes Mapped"]) if h in data.catalog else -1 for k, h in heads.items()}


def assert_manifest(data: HTSData) -> None:
    path = os.path.join(MANIFEST_DIR, f"{data.revision}.json")
    if not os.path.exists(path):
        raise DataLoadError(
            f"No manifest for revision {data.revision}. Run tools/make_manifest.py, review the counts, "
            f"and commit dutydrop/manifests/{data.revision}.json.")
    man = _rj(path)
    errors = []
    for k, v in man["counts"].items():
        if data.counts.get(k) != v:
            errors.append(f"{k}: expected {v}, loaded {data.counts.get(k)}")
    got = section301_list_counts(data)
    for k, v in man.get("section301_lists", {}).items():
        if got.get(k) != v:
            errors.append(f"Section 301 {k}: expected {v}, loaded {got.get(k)}")
    missing = [c for c in data.active_by_hts if c not in data.base]
    if missing:
        errors.append(f"{len(missing)} active_by_hts codes not in base table, e.g. {missing[:3]}")
    if errors:
        raise DataLoadError("Data load assertions failed: " + "; ".join(errors))


def write_manifest(data: HTSData) -> str:
    os.makedirs(MANIFEST_DIR, exist_ok=True)
    path = os.path.join(MANIFEST_DIR, f"{data.revision}.json")
    with open(path, "w") as fh:
        json.dump({"revision": data.revision, "counts": data.counts,
                   "section301_lists": section301_list_counts(data)}, fh, indent=2)
    return path
