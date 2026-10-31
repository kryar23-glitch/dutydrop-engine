"""Validate lexicon part files against HTS Rev 21. Usage: python3 validate.py [parts_dir]"""
import csv, json, sys, os, glob, re

HERE = os.path.dirname(os.path.abspath(__file__))
rows = list(csv.DictReader(open(os.path.join(HERE, "data", "hts.csv"), encoding="utf-8-sig")))
leaf = {r["HTS Code"]: r for r in rows if r["Level"] == "Statistical (10)"}
# 8 digit tariff lines with no statistical children are leaves too; they take the suffix 00
_eight = {r["HTS Code"] for r in rows if r["Level"].startswith("Tariff line")}
for c in _eight:
    if not any(k.startswith(c + ".") for k in leaf):
        leaf[c + ".00"] = next(r for r in rows if r["HTS Code"] == c)
CODE = re.compile(r"^\d{4}\.\d{2}\.\d{2}\.\d{2}$")


def check_file(path):
    errs, ids, n = [], set(), 0
    for i, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception as ex:
            errs.append(f"{path}:{i} bad json {ex}")
            continue
        n += 1
        for k in ("id", "term", "category", "aliases", "hts10"):
            if not e.get(k):
                errs.append(f"{path}:{i} missing {k}")
        if e.get("id") in ids:
            errs.append(f"{path}:{i} duplicate id {e.get('id')}")
        ids.add(e.get("id"))
        codes = [("hts10", e.get("hts10", ""))] + [(f"variant[{v.get('when')}]", v.get("hts10", "")) for v in e.get("variants", []) or []]
        for label, c in codes:
            if not CODE.match(c or ""):
                errs.append(f"{path}:{i} {e.get('id')} {label} bad format {c!r}")
            elif c not in leaf:
                errs.append(f"{path}:{i} {e.get('id')} {label} not a 10 digit leaf in Rev 21: {c}")
    return n, errs


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "parts")
    total, allerr = 0, []
    for p in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
        if os.path.basename(p) == "variants_extra.jsonl":
            continue
        n, errs = check_file(p)
        total += n
        allerr += errs
        print(f"{os.path.basename(p)}: {n} entries, {len(errs)} errors")
    print(f"TOTAL {total} entries, {len(allerr)} errors")
    for e in allerr[:200]:
        print(e)
