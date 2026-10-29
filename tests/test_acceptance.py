"""Spec section 6 acceptance tests, plus the cost rules. Run: python3 -m unittest -v tests.test_acceptance

Model calls use the scripted FakeAdapter (usage simulated from the spec's reference call sizes).
The live provider is exercised by tools/live_smoke.py, which needs DEEPSEEK_API_KEY.
"""
import base64
import datetime as dt
import io
import json
import os
import shutil
import tempfile
import unittest
from decimal import Decimal

from dutydrop import calculator, config, data as datamod, receipt as receiptmod
from dutydrop.adapters.base import ProviderNotConfigured
from dutydrop.adapters.fake import FakeAdapter
from dutydrop.engine import Engine
from dutydrop.store import Store

TODAY = dt.date(2026, 10, 29)
DATA = None
STATE = tempfile.mkdtemp(prefix="dutydrop_test_")
REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")


def setUpModule():
    global DATA
    DATA = datamod.load()          # load time assertions run here (test 1)


def tearDownModule():
    from tools.cost_report import write_report
    write_report(os.path.join(STATE, "audit"), REPORT_DIR, label="test suite (simulated usage)")
    shutil.rmtree(STATE, ignore_errors=True)


HORSE = {"product_name": "live purebred breeding horse", "search_terms": ["horses", "live horses", "purebred breeding"],
         "materials": [], "function_and_use": "purebred breeding animal", "parts_and_components": [],
         "form_and_construction": "live animal", "visible_text_and_labels": [], "power_source": None,
         "attribute_confidence": {"materials": 0.9, "function": 0.9, "identity": 0.95}, "cannot_tell": []}
VAGUE = {"product_name": "object", "search_terms": ["item", "thing"], "materials": [],
         "function_and_use": "unknown", "parts_and_components": [], "form_and_construction": "unclear",
         "visible_text_and_labels": [], "power_source": None,
         "attribute_confidence": {"materials": 0.1, "function": 0.1, "identity": 0.1},
         "cannot_tell": ["identity", "materials", "function"]}


def strong_first(desc, shortlist):
    scores = []
    for i, c in enumerate(shortlist):
        v = 1.0 if i == 0 else 0.0
        scores.append({"code": c["code"], "identity": v, "material": v, "function": v, "construction": v,
                       "supports": [], "contradicts": []})
    return {"scores": scores, "questions": []}


def flat_low(desc, shortlist):
    return {"scores": [{"code": c["code"], "identity": 0.2, "material": 0.2, "function": 0.2, "construction": 0.2}
                       for c in shortlist], "questions": []}


def engine(adapter):
    return Engine(data=DATA, adapter=adapter, store=Store(STATE))


def photo(w=3000, h=2000):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (120, 80, 40)).save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


class T1DataLoad(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(DATA.counts["base"], 29861)
        self.assertEqual(DATA.counts["catalog"], 3112)
        self.assertEqual(DATA.counts["coverage"], 314287)
        self.assertEqual(DATA.counts["active_by_hts"], 101381)
        self.assertEqual(DATA.counts["country_wide"], 78)

    def test_section301_lists(self):
        self.assertEqual(datamod.section301_list_counts(DATA),
                         {"List 1": 861, "List 2": 288, "List 3": 5911, "List 4A": 2984})

    def test_version_stamp(self):
        self.assertIn("Rev 21", DATA.label)


class T2ValidationGate(unittest.TestCase):
    def test_out_of_table_codes_rejected(self):
        def tempt(desc, shortlist):
            return {"scores": [{"code": "9999.99.9999", "identity": 1, "material": 1, "function": 1, "construction": 1},
                               {"code": "8471300199", "identity": 1, "material": 1, "function": 1, "construction": 1}],
                    "questions": []}
        e = engine(FakeAdapter([HORSE], tempt))
        r = e.classify(description=HORSE)
        rec = e.store.load(r["audit_id"])
        rejected = rec["rounds"][0]["result"]["rejected_codes"]
        self.assertIn("9999.99.9999", rejected)
        self.assertIn("8471300199", rejected)
        for c in r["candidates"]:
            self.assertTrue(DATA.exists(c["code"]))
        if r["assigned_code"]:
            self.assertTrue(DATA.exists(r["assigned_code"]))


class T3Math(unittest.TestCase):
    def test_reconcile_to_cent(self):
        amt, basis, partial = calculator.rate_amount("27.5%", Decimal("40.00"), None, None)
        self.assertEqual(calculator.money(amt), Decimal("11.00"))
        self.assertEqual(Decimal("40.00") + calculator.money(amt), Decimal("51.00"))
        self.assertIsNone(partial)

    def test_real_ad_valorem_line(self):
        r = calculator.estimate(DATA, "0101300000", "Iceland", "40.00", today=TODAY)
        self.assertEqual(r["line_items"][0]["amount"], "2.72")          # 6.8% of 40.00
        self.assertEqual(r["total"], "2.72")
        self.assertEqual(r["landed"], "42.72")

    def test_free_line(self):
        r = calculator.estimate(DATA, "0101210010", "Iceland", "40.00", today=TODAY)
        self.assertEqual(r["total"], "0.00")
        self.assertTrue(any(f["flag"] == "inherited_rate" for f in r["flags"]))

    def test_specific_rate_without_quantity_is_partial(self):
        r = calculator.estimate(DATA, "0102294024", "Iceland", "40.00", today=TODAY)
        self.assertIsNone(r["total"])
        self.assertIsNone(r["line_items"][0]["amount"])
        self.assertTrue(any(f["flag"] == "partial" for f in r["flags"]))
        r2 = calculator.estimate(DATA, "0102294024", "Iceland", "40.00", quantity=100, quantity_unit="kg", today=TODAY)
        self.assertEqual(r2["line_items"][0]["amount"], "1.00")         # 1 cent per kg x 100 kg

    def test_displayed_total_equals_sum_of_lines(self):
        r = calculator.estimate(DATA, "8504409580", "China", "123.45", today=TODAY)
        shown = sum(Decimal(l["amount"]) for l in r["line_items"] if l["amount"] is not None)
        self.assertEqual(Decimal(r["provisional_total"]["amount"]), shown)


class T4StatusByEntryDate(unittest.TestCase):
    def ieepa(self, r):
        return [l for l in r["line_items"] + r["alternative_items"] if l.get("program") == "IEEPA"]

    def test_ieepa(self):
        jan = calculator.estimate(DATA, "8504409580", "China", "100", dt.date(2026, 1, 15), "historical", today=TODAY)
        self.assertTrue(self.ieepa(jan), "IEEPA should apply to a January 15, 2026 entry")
        self.assertTrue(any(f["flag"] == "refund_eligibility_candidate" for f in jan["flags"]))
        cur = calculator.estimate(DATA, "8504409580", "China", "100", dt.date(2026, 1, 15), "current", today=TODAY)
        self.assertFalse(self.ieepa(cur))
        self.assertTrue(any(x["program"] == "IEEPA" for x in cur["excluded_overlays"]))
        mar = calculator.estimate(DATA, "8504409580", "China", "100", dt.date(2026, 3, 1), "current", today=TODAY)
        self.assertFalse(self.ieepa(mar))
        mar_h = calculator.estimate(DATA, "8504409580", "China", "100", dt.date(2026, 3, 1), "historical", today=TODAY)
        self.assertFalse([l for l in self.ieepa(mar_h) if "verify_in_effect_on_entry_date" not in l["flags"]])

    def test_section122(self):
        s122 = lambda r: [l for l in r["line_items"] if l.get("program") == "Section 122"]
        jul1 = calculator.estimate(DATA, "0101300000", "Iceland", "100", dt.date(2026, 7, 1), "historical", today=TODAY)
        jul25 = calculator.estimate(DATA, "0101300000", "Iceland", "100", dt.date(2026, 7, 25), "historical", today=TODAY)
        cur = calculator.estimate(DATA, "0101300000", "Iceland", "100", dt.date(2026, 7, 1), "current", today=TODAY)
        self.assertTrue(s122(jul1))
        self.assertFalse(s122(jul25))
        self.assertFalse(s122(cur))

    def test_forced_labor_starts_july_24(self):
        fl = lambda r: [l for l in r["line_items"] if l.get("program") == "Section 301 forced labor"]
        self.assertFalse(fl(calculator.estimate(DATA, "0101300000", "Mexico", "100", dt.date(2026, 7, 23), "historical", today=TODAY)))
        self.assertTrue(fl(calculator.estimate(DATA, "0101300000", "Mexico", "100", dt.date(2026, 7, 24), "historical", today=TODAY)))


class T5Stacking(unittest.TestCase):
    def test_no_mixed_total(self):
        r = calculator.estimate(DATA, "8504409580", "China", "100", today=TODAY)
        overlays = [l for l in r["line_items"] if l["kind"] == "overlay"]
        self.assertGreaterEqual(len(overlays), 2)
        self.assertIsNone(r["total"])
        self.assertEqual(r["provisional_total"]["label"], config.PROVISIONAL_LABEL)
        self.assertTrue(any(f["flag"] == "stacking_provisional" for f in r["flags"]))


class T6WeakMatchLoop(unittest.TestCase):
    def test_loop_then_broker_route(self):
        fake = FakeAdapter([VAGUE, VAGUE, VAGUE], flat_low)
        e = engine(fake)
        r0 = e.classify(images=[photo()])
        self.assertFalse(r0["final"])
        self.assertIsNone(r0["assigned_code"])
        self.assertEqual({q["id"] for q in r0["questions"]}, {"describe", "photo"})
        r1 = e.classify(answers={"description": "not sure, some kind of thing"}, audit_id=r0["audit_id"])
        self.assertFalse(r1["final"])
        self.assertEqual({q["id"] for q in r1["questions"]}, {"describe", "photo"})
        r2 = e.classify(answers={"images": [photo(800, 600)]}, audit_id=r0["audit_id"])
        self.assertTrue(r2["final"])
        self.assertIsNone(r2["assigned_code"])
        self.assertTrue(r2["candidates"])
        self.assertEqual(fake.identify_calls, 3)        # one vision call per round, never more
        self.assertEqual(len(fake.last_images), 2)       # all photos in one call
        out = e.receipt(audit_id=r0["audit_id"], origin="China", value=25)
        self.assertEqual(out["status"], "complete")
        self.assertIsNone(out["hts"])
        self.assertEqual(out["broker_route"], config.BROKER_ROUTE)


class T7Masking(unittest.TestCase):
    def test_tiers(self):
        e = engine(FakeAdapter([HORSE], strong_first))
        anon = e.receipt(description_text="a purebred breeding horse", origin="Iceland", value=40)
        self.assertEqual(anon["status"], "complete", anon)
        code = e.store.load(anon["audit_id"])["decision"]["assigned_code"]
        self.assertEqual(anon["hts"]["code"], f"{code[:4]}.XX.XXXX")
        self.assertNotIn(code, json.dumps(anon))
        full = e.receipt(audit_id=anon["audit_id"], tier="free_account")
        self.assertEqual(full["hts"]["code"], datamod.display_code(code))
        for rec in (anon, full):
            self.assertEqual(rec["disclaimer"], "Estimate only. Check this with a customs broker. DutyDrop is not a customs broker.")
            self.assertEqual(rec["link"], "dutydrop.co")
            self.assertEqual(receiptmod.contains_foreign_domain(rec), [])
            self.assertIn("Rev 21", rec["data_version"])
            self.assertIn(rec["confidence_band"], ("High", "Medium", "Low"))


class T8USMCA(unittest.TestCase):
    def test_scenario_not_substituted(self):
        r = calculator.estimate(DATA, "0101300000", "Mexico", "40.00", today=TODAY)
        self.assertEqual(r["line_items"][0]["amount"], "2.72")          # general rate applied
        sc = r["scenarios"][0]
        self.assertEqual(sc["label"], "USMCA rate, if the goods qualify")
        self.assertEqual(sc["base_duty_if_qualifies"], "0.00")
        self.assertTrue(any(f["flag"] == "usmca_scenario_shown" for f in r["flags"]))


class T9CostRules(unittest.TestCase):
    def test_fail_loudly_without_key(self):
        from dutydrop.adapters.openai_compat import OpenAICompatAdapter
        saved = os.environ.pop("DEEPSEEK_API_KEY", None)
        try:
            with self.assertRaises(ProviderNotConfigured):
                OpenAICompatAdapter("deepseek")
        finally:
            if saved:
                os.environ["DEEPSEEK_API_KEY"] = saved

    def test_images_downscaled(self):
        from dutydrop import imaging
        from PIL import Image
        urls, _ = imaging.prepare([photo(4032, 3024)])
        im = Image.open(io.BytesIO(base64.b64decode(urls[0].split(",", 1)[1])))
        self.assertLessEqual(max(im.size), config.IMAGE_MAX_DIM)
        self.assertEqual(im.format, "JPEG")

    def test_repeat_product_costs_nothing(self):
        fake = FakeAdapter([HORSE], strong_first)
        e = engine(fake)
        img = photo(1200, 900)
        e.classify(images=[img], user_text="breeding horse")
        calls = fake.identify_calls + fake.decide_calls
        again = e.classify(images=[img], user_text="breeding horse")
        self.assertTrue(again["cached"])
        self.assertEqual(fake.identify_calls + fake.decide_calls, calls)

    def test_cost_cap_stops_calls(self):
        fake = FakeAdapter([HORSE], strong_first)
        e = engine(fake)
        old = config.COST_CAP_PER_RECEIPT
        try:
            config.COST_CAP_PER_RECEIPT = Decimal("0.0003")
            r = e.classify(description=HORSE)
            self.assertTrue(r["cost_cap_hit"])
            self.assertEqual(fake.decide_calls, 0)
        finally:
            config.COST_CAP_PER_RECEIPT = old

    def test_reference_cost_in_budget(self):
        from dutydrop.costs import price
        per_receipt = price(1000, 0, 450) + price(1800, 0, 300)
        self.assertLessEqual(per_receipt, config.COST_TARGET_PER_RECEIPT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
