"""Score the matcher on an eval CSV (query,expected) where expected is pipe separated 6 digit codes.
Usage: python3 score.py [eval_csv]"""
import csv, os, sys, json
from match import Matcher

HERE = os.path.dirname(os.path.abspath(__file__))
path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "eval", "eval_set.csv")
m = Matcher(os.path.join(HERE, "dist"))
rows = list(csv.DictReader(open(path)))
ok, miss, wrong = 0, [], []
for r in rows:
    res = m.match(r["query"])
    exp = r["expected"].split("|")
    if res["confidence"] == "none":
        miss.append(r["query"])
        continue
    got = res["hts10"].replace(".", "")[:6]
    if got in exp:
        ok += 1
    else:
        wrong.append((r["query"], res["hts10"], res["term"], r["expected"]))
print(f"{ok}/{len(rows)} correct at 6 digits, {len(miss)} no match, {len(wrong)} wrong")
for q in miss:
    print("NO MATCH:", q)
for w in wrong:
    print("WRONG:", w)
