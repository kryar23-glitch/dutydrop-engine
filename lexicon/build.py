"""Merge lexicon parts into deliverables.

Outputs in /home/claude/lexicon/dist:
  lexicon.json        all entries keyed by id
  aliases.csv         alias,entry_id,kind (term|alias|plural)
  misspellings.csv    misspelling,correct,entry_id   (generated, collision filtered)
  stats.json          counts
"""
import json, glob, os, csv, re, itertools, collections

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")
os.makedirs(DIST, exist_ok=True)

entries = {}
for p in sorted(glob.glob(os.path.join(HERE, "parts", "*.jsonl"))) + [os.path.join(HERE, "patches", "entries_extra.jsonl")]:
    if not os.path.exists(p):
        continue
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        e = json.loads(line)
        eid = e["id"]
        if eid in entries:  # cross file duplicate: keep first, merge aliases and variants
            old = entries[eid]
            old["aliases"] = sorted(set(old["aliases"]) | set(e.get("aliases", [])))
            seen = {v["when"].lower() for v in old.get("variants") or []}
            old["variants"] = (old.get("variants") or []) + [v for v in e.get("variants") or [] if v["when"].lower() not in seen]
            if e["hts10"] != old["hts10"]:
                old.setdefault("conflicts", []).append({"file": os.path.basename(p), "hts10": e["hts10"]})
            continue
        e["source_file"] = os.path.basename(p)
        entries[eid] = e

# broker-reviewed resolutions for cross-file conflicts, and extra aliases
ov_path = os.path.join(HERE, "patches", "overrides.json")
if os.path.exists(ov_path):
    for eid, code in json.load(open(ov_path)).items():
        if eid in entries:
            entries[eid]["hts10"] = code
vx = os.path.join(HERE, "patches", "variants_extra.jsonl")
if os.path.exists(vx):
    for line in open(vx):
        if line.strip():
            v = json.loads(line)
            if v["id"] in entries:
                entries[v["id"]].setdefault("variants", []).insert(0, {k: v[k] for k in ("when", "hts10", "note")})
removed = set()
ar = os.path.join(HERE, "patches", "aliases_remove.csv")
if os.path.exists(ar):
    removed = {(r["alias"], r["entry_id"]) for r in csv.DictReader(open(ar))}
    for a, eid in removed:
        if eid in entries:
            entries[eid]["aliases"] = [x for x in entries[eid]["aliases"] if x.lower() != a]
ea_path = os.path.join(HERE, "patches", "aliases_extra.csv")
if os.path.exists(ea_path):
    for r in csv.DictReader(open(ea_path)):
        if r["entry_id"] in entries:
            entries[r["entry_id"]]["aliases"] = sorted(set(entries[r["entry_id"]]["aliases"]) | {r["alias"]})


def norm(s):
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def singular(w):
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("ches", "shes", "xes", "sses")):
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is")) and len(w) > 3:
        return w[:-1]
    return w


def plural(w):
    if w.endswith("s") and not w.endswith("ss"):
        return w
    if w.endswith(("s", "x", "z", "ch", "sh")):
        return w + "es"
    if w.endswith("y") and len(w) > 2 and w[-2] not in "aeiou":
        return w[:-1] + "ies"
    if w.endswith("f"):
        return w[:-1] + "ves"
    if w.endswith("fe"):
        return w[:-2] + "ves"
    return w + "s"


alias_rows, alias_map = [], collections.defaultdict(set)
for eid, e in entries.items():
    forms = [("term", e["term"])] + [("alias", a) for a in e.get("aliases", [])]
    for kind, a in forms:
        a = norm(a)
        if not a:
            continue
        alias_map[a].add(eid)
        alias_rows.append((a, eid, kind))
        words = a.split()
        pl = " ".join(words[:-1] + [plural(words[-1])])
        sg = " ".join(words[:-1] + [singular(words[-1])])
        for form in {pl, sg} - {a}:
            alias_map[form].add(eid)
            alias_rows.append((form, eid, "plural"))

# vocabulary of real words, so generated misspellings never collide with them
vocab = set()
for a in alias_map:
    vocab.update(a.split())
hts_words = set()
for r in csv.DictReader(open(os.path.join(HERE, "data", "hts.csv"), encoding="utf-8-sig")):
    hts_words.update(re.findall(r"[a-z]+", r["Description"].lower()))
vocab |= hts_words

KEYB = {
    "q": "wa", "w": "qes", "e": "wrd", "r": "etf", "t": "ryg", "y": "tuh", "u": "yij", "i": "uok", "o": "ipl", "p": "ol",
    "a": "qsz", "s": "adwx", "d": "sfe", "f": "dgr", "g": "fht", "h": "gjy", "j": "hku", "k": "jli", "l": "kop",
    "z": "asx", "x": "zsc", "c": "xvd", "v": "cbf", "b": "vng", "n": "bmh", "m": "nj",
}
PHON = [("ph", "f"), ("f", "ph"), ("ie", "ei"), ("ei", "ie"), ("c", "k"), ("k", "c"), ("s", "z"), ("z", "s"),
        ("ou", "o"), ("our", "or"), ("or", "our"), ("er", "re"), ("re", "er"), ("ck", "k"), ("x", "cks"),
        ("tion", "shun"), ("ee", "ea"), ("ea", "ee"), ("ai", "ay"), ("y", "ie"), ("ie", "y"), ("oo", "u")]


def variants(w):
    out = set()
    n = len(w)
    if n < 4:
        return out
    for i in range(n):  # deletion
        out.add(w[:i] + w[i + 1:])
    for i in range(n - 1):  # transposition
        out.add(w[:i] + w[i + 1] + w[i] + w[i + 2:])
    for i in range(n):  # doubling and undoubling
        out.add(w[:i + 1] + w[i] + w[i + 1:])
    for i in range(1, n):
        if w[i] == w[i - 1]:
            out.add(w[:i] + w[i + 1:])
    for i, ch in enumerate(w):  # adjacent key substitution, interior letters only
        if 0 < i < n - 1:
            for k in KEYB.get(ch, ""):
                out.add(w[:i] + k + w[i + 1:])
    for a, b in PHON:
        if a in w:
            out.add(w.replace(a, b, 1))
    out.discard(w)
    return {v for v in out if len(v) >= 3 and v not in vocab}


miss = {}
for word in sorted(vocab - hts_words | {w for a in alias_map for w in a.split()}):
    if len(word) < 4 or not word.isalpha():
        continue
    for v in variants(word):
        if v in miss and miss[v] != word:
            miss[v] = None  # ambiguous: two real words share this typo, drop it
        elif v not in miss:
            miss[v] = word
miss = {k: v for k, v in miss.items() if v}
mx = os.path.join(HERE, "patches", "misspellings_extra.csv")
if os.path.exists(mx):
    for r in csv.DictReader(open(mx)):
        miss[r["misspelling"]] = r["correct_word"]

word_to_entries = collections.defaultdict(set)
for a, ids in alias_map.items():
    for w in a.split():
        word_to_entries[w] |= ids

with open(os.path.join(DIST, "lexicon.json"), "w") as f:
    json.dump(entries, f, indent=1, sort_keys=True)
with open(os.path.join(DIST, "aliases.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["alias", "entry_id", "kind"])
    w.writerows(sorted(set(alias_rows)))
with open(os.path.join(DIST, "misspellings.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["misspelling", "correct_word"])
    w.writerows(sorted(miss.items()))

stats = {
    "entries": len(entries),
    "aliases_including_plurals": len(alias_map),
    "misspellings": len(miss),
    "variant_rules": sum(len(e.get("variants", []) or []) for e in entries.values()),
    "distinct_hts10": len({e["hts10"] for e in entries.values()} | {v["hts10"] for e in entries.values() for v in e.get("variants", []) or []}),
    "by_category": dict(collections.Counter(e["category"] for e in entries.values())),
}
json.dump(stats, open(os.path.join(DIST, "stats.json"), "w"), indent=1)
print(json.dumps(stats, indent=1))
