"""Cost report: cost per receipt and per stage, from audit records (Spec 3A cost accounting).

Usage: python3 -m tools.cost_report <audit_dir> [<out_dir>]
"""
import glob
import json
import os
import sys
from collections import defaultdict
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dutydrop import config  # noqa: E402


def _rj(path):
    with open(path) as fh:
        return json.load(fh)



def write_report(audit_dir, out_dir, label="run"):
    rows, by_stage = [], defaultdict(lambda: {"calls": 0, "input": 0, "cached": 0, "output": 0, "images": 0, "cost": Decimal(0)})
    simulated = False
    for p in sorted(glob.glob(os.path.join(audit_dir, "*.json"))):
        rec = _rj(p)
        calls = (rec.get("cost") or {}).get("calls", [])
        total = sum((Decimal(c["cost_usd"]) for c in calls), Decimal(0))
        rows.append({"audit_id": rec["audit_id"], "calls": len(calls), "cost_usd": str(total),
                     "cached": rec.get("cached", False), "cap_hit": rec.get("cost_cap_hit", False),
                     "outcome": (rec.get("decision") or {}).get("outcome")})
        for c in calls:
            s = by_stage[c["stage"]]
            s["calls"] += 1
            s["input"] += c["input_tokens"]
            s["cached"] += c["cached_input_tokens"]
            s["output"] += c["output_tokens"]
            s["images"] += c["images"]
            s["cost"] += Decimal(c["cost_usd"])
            simulated = simulated or c.get("simulated", False)
    n = len(rows) or 1
    total = sum((Decimal(r["cost_usd"]) for r in rows), Decimal(0))
    report = {
        "label": label, "simulated_usage": simulated, "prices_verified": config.PRICES_VERIFIED,
        "price_per_m": {"input": str(config.PRICE_INPUT_PER_M), "output": str(config.PRICE_OUTPUT_PER_M)},
        "receipts": len(rows), "total_usd": str(total), "mean_per_receipt_usd": str((total / n).quantize(Decimal("0.000001"))),
        "max_per_receipt_usd": max((r["cost_usd"] for r in rows), key=Decimal, default="0"),
        "target_usd": str(config.COST_TARGET_PER_RECEIPT), "cap_usd": str(config.COST_CAP_PER_RECEIPT),
        "per_stage": {k: {**v, "cost": str(v["cost"]), "mean_cost_per_call": str((v["cost"] / max(v["calls"], 1)).quantize(Decimal("0.000001")))}
                      for k, v in by_stage.items()},
        "per_receipt": rows,
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "cost_report.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    lines = [f"# Cost report: {label}", "",
             f"Receipts: {report['receipts']}  Total: ${report['total_usd']}  Mean per receipt: ${report['mean_per_receipt_usd']}  Max: ${report['max_per_receipt_usd']}",
             f"Target ${report['target_usd']} per receipt, cap ${report['cap_usd']}. Prices verified against official page: {report['prices_verified']}. Simulated usage: {simulated}.",
             "", "| Stage | Calls | Input tok | Cached tok | Output tok | Images | Cost | Mean per call |", "|---|---|---|---|---|---|---|---|"]
    for k, v in report["per_stage"].items():
        lines.append(f"| {k} | {v['calls']} | {v['input']} | {v['cached']} | {v['output']} | {v['images']} | ${v['cost']} | ${v['mean_cost_per_call']} |")
    with open(os.path.join(out_dir, "cost_report.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return report


if __name__ == "__main__":
    print(json.dumps(write_report(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "reports"), indent=2)[:2000])
