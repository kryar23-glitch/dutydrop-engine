"""Live smoke test against the configured provider (needs DEEPSEEK_API_KEY). Measures real cost.

Usage: python3 -m tools.live_smoke [--images DIR]
Writes reports/live/cost_report.md and reports/live/receipts.json. Each case is one receipt.
Text cases exercise the text path; --images DIR adds one receipt per image file (real photos).
"""
import argparse
import base64
import glob
import io
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dutydrop.engine import Engine  # noqa: E402
from dutydrop.store import Store  # noqa: E402
from tools.cost_report import write_report  # noqa: E402

TEXT_CASES = [
    ("Hand operated kitchen whisk, stainless steel wire loops, plastic handle", "China", 4.50),
    ("Men's crew neck t-shirt, knitted, 100% cotton", "Vietnam", 6.00),
    ("Desk lamp with LED bulb, plastic base and steel arm, plugs into the wall", "Mexico", 18.00),
]


def label_image(text):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (1600, 1000), "white")
    d = ImageDraw.Draw(im)
    for i, line in enumerate(text.split("\n")):
        d.text((80, 120 + i * 90), line, fill="black")
    im = im.resize((3200, 2000))     # oversize on purpose; the engine must downscale
    buf = io.BytesIO()
    im.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", default=None)
    a = ap.parse_args()
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "live")
    state = os.path.join(root, "state")
    shutil.rmtree(state, ignore_errors=True)
    e = Engine(store=Store(state))
    out = []
    for text, origin, value in TEXT_CASES:
        out.append({"case": text, **e.receipt(description_text=text, origin=origin, value=value)})
    img = label_image("PRODUCT LABEL\nStainless steel kitchen whisk\nHand operated\nMade in China")
    out.append({"case": "synthetic label photo", **e.receipt(images=[img], origin="China", value=4.5)})
    if a.images:
        for p in sorted(glob.glob(os.path.join(a.images, "*")))[:20]:
            with open(p, "rb") as f:
                b = base64.b64encode(f.read()).decode()
            out.append({"case": os.path.basename(p), **e.receipt(images=[b], origin="China", value=10)})
    for r in out:
        r.pop("photo", None)
    with open(os.path.join(root, "receipts.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)
    rep = write_report(os.path.join(state, "audit"), root, label="live provider")
    for r in out:
        hts = (r.get("hts") or {}).get("code")
        print(f"{r['case'][:50]:50} | {r['status']:11} | {hts or '-':13} | questions {len(r.get('questions', []))}")
    print(f"receipts {rep['receipts']}  mean ${rep['mean_per_receipt_usd']}  max ${rep['max_per_receipt_usd']}")


if __name__ == "__main__":
    main()
