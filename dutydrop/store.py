"""Audit records and the result cache (Spec 3C audit record; cost rule 6).

Audit records are JSON files, one per classification session, holding every input, model output,
candidate set with evidence and scores, question and answer, decision, data rows, and cost. A
receipt can be reproduced from its record. The result cache keys on photo hashes plus a
normalized description hash, so a repeat product costs nothing in model calls.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import uuid
from typing import Optional

from . import config


def _rj(path):
    with open(path) as fh:
        return json.load(fh)



class Store:
    def __init__(self, root: Optional[str] = None):
        self.root = root or config.STATE_DIR
        self.audit_dir = os.path.join(self.root, "audit")
        self.cache_dir = os.path.join(self.root, "cache")
        os.makedirs(self.audit_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)

    # ------------------------------------------------ audit
    def new_audit(self, data_version: str) -> dict:
        return {"audit_id": uuid.uuid4().hex, "created": dt.datetime.utcnow().isoformat() + "Z",
                "data_version": data_version, "rounds": [], "inputs": [], "answers": [],
                "decision": None, "cost": None, "events": []}

    def save(self, rec: dict) -> None:
        with open(os.path.join(self.audit_dir, rec["audit_id"] + ".json"), "w") as f:
            json.dump(rec, f, indent=1, default=str)

    def load(self, audit_id: str) -> dict:
        p = os.path.join(self.audit_dir, f"{audit_id}.json")
        if not os.path.exists(p):
            raise KeyError(f"unknown audit_id {audit_id}")
        return _rj(p)

    # ------------------------------------------------ cache
    @staticmethod
    def cache_key(photo_hashes, text: str, data_version: str) -> str:
        norm = " ".join((text or "").lower().split())
        h = hashlib.sha256()
        h.update(data_version.encode())
        for p in sorted(photo_hashes or []):
            h.update(p.encode())
        h.update(hashlib.sha256(norm.encode()).hexdigest().encode())
        return h.hexdigest()

    def cache_get(self, key: str) -> Optional[dict]:
        p = os.path.join(self.cache_dir, key + ".json")
        return _rj(p) if os.path.exists(p) else None

    def cache_put(self, key: str, value: dict) -> None:
        with open(os.path.join(self.cache_dir, key + ".json"), "w") as f:
            json.dump(value, f, default=str)
