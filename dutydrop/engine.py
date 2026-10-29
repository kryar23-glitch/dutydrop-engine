"""The single agent pipeline: Identify, Retrieve, Decide, Calculate, Receipt (Spec 3).

Model calls happen only in Identify (one vision call per round, all photos together) and in
Decide (one reasoning call over the shortlist). Everything else is deterministic code.
"""
from __future__ import annotations

import datetime as dt
from typing import List, Optional

from . import calculator, config, decide, imaging, receipt
from .adapters.base import ModelAdapter, normalize_description
from .costs import CallRecord, CostCapReached, Ledger
from .data import HTSData, digits, display_code, load
from .retrieval import Index
from .store import Store


class InputError(ValueError):
    pass


def _merge(prev: dict, new: dict) -> dict:
    out = dict(new)
    out["search_terms"] = list(dict.fromkeys((new.get("search_terms") or []) + (prev.get("search_terms") or [])))[:15]
    if not new.get("materials"):
        out["materials"] = prev.get("materials", [])
    return out


def _apply_answers(desc: dict, answers: dict, questions: List[dict]) -> dict:
    d = dict(desc)
    qmap = {q.get("id"): q for q in questions or []}
    notes = []
    for k, v in answers.items():
        q = qmap.get(k, {"attribute": "other", "question": k})
        notes.append(f"{q['question']} {v}")
        if q.get("attribute") == "material":
            d["materials"] = [{"material": str(v), "confidence": 0.9}] + list(d.get("materials") or [])
        if q.get("attribute") in ("power",):
            d["power_source"] = str(v)
    if notes:
        d["function_and_use"] = (d.get("function_and_use") or "") + " | User answers: " + " ; ".join(notes)
        d["user_text"] = ((d.get("user_text") or "") + " | Answers: " + " ; ".join(notes))[-600:]
        d["search_terms"] = list(d.get("search_terms") or []) + [str(v) for v in answers.values()][:5]
    return d


class Engine:
    def __init__(self, data: Optional[HTSData] = None, adapter: Optional[ModelAdapter] = None,
                 store: Optional[Store] = None):
        self.data = data or load()
        self.index = Index(self.data)
        self._adapter = adapter
        self.store = store or Store()

    @property
    def adapter(self) -> ModelAdapter:
        if self._adapter is None:
            from .adapters.openai_compat import get_adapter
            self._adapter = get_adapter()          # raises ProviderNotConfigured: fail loudly
        return self._adapter

    # ------------------------------------------------------------------ Stage A
    def identify(self, images: Optional[list], user_text: Optional[str], ledger: Optional[Ledger] = None):
        ledger = ledger or Ledger()
        urls, hashes = imaging.prepare(images or [])
        if not urls and not (user_text or "").strip():
            raise InputError("Give at least one photo or a description")
        desc = self.adapter.identify(urls, user_text, ledger)
        return desc, urls, hashes, ledger

    # ------------------------------------------------------------------ Stages B and C
    def classify(self, description: Optional[dict] = None, answers: Optional[dict] = None,
                 audit_id: Optional[str] = None, images: Optional[list] = None,
                 user_text: Optional[str] = None) -> dict:
        answers = dict(answers or {})
        new_images = list(images or []) + list(answers.pop("images", []) or [])
        new_text = " ".join(x for x in [user_text, answers.pop("description", None)] if x)
        origin = answers.pop("origin", None)
        value = answers.pop("value", None)

        if audit_id:
            rec = self.store.load(audit_id)
            if origin:
                rec["origin"] = origin
            if value is not None:
                rec["value"] = str(value)
            if (rec.get("decision") or {}).get("final") or (not answers and not new_images and not new_text):
                self.store.save(rec)          # nothing new to classify on; return current state
                return self._response(rec)
            rnd = rec["round"] + 1
        else:
            rec = self.store.new_audit(self.data.label)
            rec.update(round=0, photos=[], photo_refs=[], texts=[], description=None, questions=[])
            rnd = 0
        ledger = Ledger()
        for c in (rec.get("cost") or {}).get("calls", []):
            ledger.add(CallRecord(**c))
        if origin:
            rec["origin"] = origin
        if value is not None:
            rec["value"] = str(value)
        rec["answers"].append({"round": rnd, "answers": answers, "new_text": new_text, "new_photos": len(new_images)})

        # cache: a repeat product (same photos and text) costs nothing
        if rnd == 0 and description is None:
            _, hashes = imaging.prepare(new_images) if new_images else ([], [])
            key = self.store.cache_key(hashes, new_text, self.data.label)
            hit = self.store.cache_get(key)
            if hit:
                rec.update(hit["rec"])
                rec["events"].append("result cache hit; no model calls")
                rec["cached"] = True
                rec["round"] = 0
                self.store.save(rec)
                return self._response(rec)
            rec["cache_key"] = key

        try:
            if description is not None and rnd == 0:
                desc = normalize_description(description)
            elif new_images or new_text or rnd == 0:
                urls, hashes = imaging.prepare(new_images)
                rec["photos"] += urls
                rec["photo_refs"] += hashes
                if new_text:
                    rec["texts"].append(new_text)
                ans_text = " ; ".join(f"{k}: {v}" for k, v in answers.items())
                text = " | ".join([t for t in rec["texts"]] + ([ans_text] if ans_text else [])) or None
                desc = self.adapter.identify(rec["photos"], text, ledger)   # one vision call, all photos
                if rec.get("description"):
                    desc = _merge(rec["description"], desc)
                if text:
                    desc["user_text"] = text[:600]
            else:
                desc = _apply_answers(rec["description"], answers, rec.get("questions"))
        except CostCapReached:
            rec["cost_cap_hit"] = True
            desc = rec.get("description")
            if desc is None:
                rec["decision"] = {"final": True, "assigned_code": None, "outcome": "cost_cap", "candidates": []}
                rec["cost"] = ledger.to_dict()
                self.store.save(rec)
                return self._response(rec)
        rec["description"] = desc

        result = decide.score_round(self.data, self.index, self.adapter, desc, ledger)
        if result.get("cost_cap_hit"):
            rec["cost_cap_hit"] = True
        rec["rounds"].append({"round": rnd, "description": desc, "result": result})
        top = result["candidates"][0] if result["candidates"] else None
        final, assigned, questions = False, None, []
        if result["outcome"] == decide.STRONG:
            final, assigned = True, top["code"]
        elif rnd >= config.MAX_LOOP_ROUNDS or rec.get("cost_cap_hit"):
            final = True                            # candidates + broker route, no code
        elif result["outcome"] == decide.MARGINAL:
            questions = decide.marginal_questions(result)
        else:
            questions = decide.weak_questions()
        rec["round"] = rnd
        rec["questions"] = questions
        rec["decision"] = {"final": final, "assigned_code": assigned, "outcome": result["outcome"],
                           "score": result["top"], "margin": result["margin"],
                           "confidence_band": decide.band(result["top"] or 0.0),
                           "candidates": result["candidates"][:5]}
        rec["cost"] = ledger.to_dict()
        if final and rec.get("cache_key"):
            self.store.cache_put(rec["cache_key"], {"rec": {k: rec[k] for k in
                                 ("description", "decision", "rounds", "photo_refs", "photos", "questions")}})
        self.store.save(rec)
        return self._response(rec)

    def _response(self, rec: dict) -> dict:
        dec = rec.get("decision") or {}
        required = []
        if not rec.get("origin"):
            required.append({"id": "origin", "attribute": "origin", "question": "Which country was it made in?"})
        if rec.get("value") in (None, ""):
            required.append({"id": "value", "attribute": "value", "question": "What is the customs value in US dollars?"})
        return {
            "audit_id": rec["audit_id"], "final": dec.get("final", False),
            "assigned_code": dec.get("assigned_code"), "outcome": dec.get("outcome"),
            "confidence_band": dec.get("confidence_band"),
            "candidates": [{"code": c["code"], "display": c["display"], "description": c["description"],
                            "score": c["score"]} for c in dec.get("candidates", [])],
            "questions": rec.get("questions", []), "required_inputs": required,
            "product_label": (rec.get("description") or {}).get("product_name", ""),
            "photo_refs": rec.get("photo_refs", []), "photo_preview": (rec.get("photos") or [None])[0],
            "origin": rec.get("origin"), "value": rec.get("value"),
            "cost_cap_hit": rec.get("cost_cap_hit", False), "cached": rec.get("cached", False),
            "cost_usd": (rec.get("cost") or {}).get("total_usd", "0"),
        }

    # ------------------------------------------------------------------ Stage D
    def estimate(self, code: str, origin: str, value, entry_date=None, mode: str = calculator.CURRENT,
                 quantity=None, quantity_unit=None, today=None) -> dict:
        if isinstance(entry_date, str) and entry_date:
            entry_date = dt.date.fromisoformat(entry_date)
        if mode not in (calculator.CURRENT, calculator.HISTORICAL):
            raise InputError("mode must be current or historical")
        return calculator.estimate(self.data, code, origin, value, entry_date or None, mode, quantity,
                                   quantity_unit, today=today)

    # ------------------------------------------------------------------ full pipeline
    def receipt(self, images=None, description_text=None, origin=None, value=None, tier=receipt.ANONYMOUS,
                entry_date=None, quantity=None, quantity_unit=None, answers=None, audit_id=None,
                description: Optional[dict] = None) -> dict:
        answers = dict(answers or {})
        if origin:
            answers["origin"] = origin
        if value is not None:
            answers["value"] = value
        cls = self.classify(description=description, answers=answers, audit_id=audit_id, images=images,
                            user_text=description_text)
        rec = self.store.load(cls["audit_id"])
        if not cls["final"] or cls["required_inputs"]:
            return {"status": "needs_input", "audit_id": cls["audit_id"],
                    "questions": cls["questions"] + cls["required_inputs"],
                    "disclaimer": config.DISCLAIMER, "link": config.PUBLIC_LINK}
        est = None
        if cls["assigned_code"]:
            est = self.estimate(cls["assigned_code"], rec["origin"], rec["value"], entry_date, calculator.CURRENT,
                                quantity, quantity_unit)
            rec["estimate"] = est
        out = receipt.build(cls, est, tier, cls["photo_preview"], rec["origin"], rec["value"], self.data.label)
        rec["receipt"] = out
        self.store.save(rec)
        return {"status": "complete", **out}

    # ------------------------------------------------------------------ lookup
    def hts(self, code: str) -> dict:
        d = digits(code)
        row = self.data.base.get(d)
        if not row:
            raise InputError(f"{code} is not in the {self.data.label} base table")
        return {"data_version": self.data.label, "code": d, "display": display_code(d), "base": row,
                "active_overlays": self.data.active_by_hts.get(d, []),
                "disclaimer": config.DISCLAIMER, "link": config.PUBLIC_LINK}
