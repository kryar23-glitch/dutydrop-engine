"""Score the live engine on the golden photo set. Photo only, no user text, first round.

Usage: python3 -m golden.run_golden   (from ~/Claude/dutydrop, with DEEPSEEK_API_KEY set)
"""
import base64, json, os, shutil, sys, time
from collections import Counter
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from dutydrop.engine import Engine  # noqa: E402
from dutydrop.store import Store  # noqa: E402
from dutydrop.data import display_code  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
items = json.load(open(os.path.join(HERE, "golden.json")))
state = os.path.join(HERE, "run_state")
shutil.rmtree(state, ignore_errors=True)
eng = Engine(store=Store(state))
results = []
for it in items:
    with open(os.path.join(HERE, "photos", it["id"] + ".jpg"), "rb") as f:
        img = base64.b64encode(f.read()).decode()
    t0 = time.time()
    try:
        r = eng.classify(images=[img])
        rec = eng.store.load(r["audit_id"])
        cands = [c["code"] for c in r["candidates"]]
        desc = rec["description"]
        err = None
    except Exception as e:  # record, keep going
        r, cands, desc, err, rec = {}, [], {}, str(e)[:200], {}
    top = cands[0] if cands else ""
    acc6, acc10 = set(it["acc6"]), set(it["acc10"])
    res = {
        "id": it["id"], "identified_as": desc.get("product_name", ""), "outcome": r.get("outcome"),
        "assigned": r.get("assigned_code"), "top1": top, "top3": cands[:3],
        "top1_heading_ok": bool(top) and top[:4] in {a[:4] for a in acc6},
        "top1_sub_ok": bool(top) and top[:6] in acc6,
        "top3_sub_ok": any(c[:6] in acc6 for c in cands[:3]),
        "top1_exact_ok": (top in acc10) if acc10 else None,
        "assigned_ok": (r.get("assigned_code") in acc10 if acc10 else r.get("assigned_code", "")[:6] in acc6) if r.get("assigned_code") else None,
        "cost_usd": r.get("cost_usd", "0"), "seconds": round(time.time() - t0, 1), "error": err,
        "expected6": sorted(acc6), "expected10": sorted(acc10),
    }
    results.append(res)
    print(f"{it['id']:15} {str(res['identified_as'])[:28]:28} {display_code(top) if top else '-':13} "
          f"head={'Y' if res['top1_heading_ok'] else 'n'} sub={'Y' if res['top1_sub_ok'] else 'n'} "
          f"top3={'Y' if res['top3_sub_ok'] else 'n'} {res['outcome']} ${res['cost_usd']} {err or ''}", flush=True)

n = len(results)
ex = [r for r in results if r["top1_exact_ok"] is not None]
assigned = [r for r in results if r["assigned"]]
summary = {
    "photos": n,
    "errors": sum(1 for r in results if r["error"]),
    "top1_heading_hit": sum(r["top1_heading_ok"] for r in results),
    "top1_subheading_hit": sum(r["top1_sub_ok"] for r in results),
    "top3_subheading_hit": sum(r["top3_sub_ok"] for r in results),
    "top1_exact_10digit_hit": f"{sum(1 for r in ex if r['top1_exact_ok'])} of {len(ex)} scorable",
    "outcomes": dict(Counter(r["outcome"] for r in results)),
    "assigned_codes": len(assigned),
    "assigned_correct": sum(1 for r in assigned if r["assigned_ok"]),
    "total_cost_usd": str(sum(Decimal(r["cost_usd"] or "0") for r in results)),
    "mean_cost_usd": str((sum(Decimal(r["cost_usd"] or "0") for r in results) / n).quantize(Decimal("0.000001"))),
}
json.dump({"summary": summary, "results": results}, open(os.path.join(HERE, "golden_results.json"), "w"), indent=1)
print(json.dumps(summary, indent=1))
