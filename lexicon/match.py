"""Reference matcher: product text -> lexicon entry -> HTS line.

This is the logic Diego wires in front of the existing search. Pure Python, no dependencies.

  from match import Matcher
  m = Matcher("dist")
  m.match("Ceramic cofee mugs, 12oz")   # -> dict with entry_id, hts10, assumption, alternatives, confidence

Steps
1. Normalize: lowercase, strip punctuation, collapse spaces, drop sizes and counts (12oz, 2-pack, 30cm).
2. Correct spelling word by word with misspellings.csv; if a word is still unknown, try a 1 edit fuzzy
   match against the alias vocabulary (only when the word has 5 or more letters).
3. Find aliases in the text, longest phrase first (n-grams up to 6 words). Score = words covered,
   with a bonus when the alias is the canonical term and a penalty when only one generic word matched.
4. Pick the best entry; apply variants whose "when" words appear in the text (material, gender, power).
5. Return the HTS line, the assumption to print, alternatives, and a confidence label:
   exact (full alias match), strong (multi word alias), weak (single word only) or none.
   Fall back to the existing search when confidence is none or weak and the existing search finds a
   heading with a better score.
"""
import csv, json, os, re, collections

SIZE = re.compile(r"\b\d+(\.\d+)?\s*(oz|ml|l|cm|mm|m|in|inch|inches|ft|lb|lbs|kg|g|pcs|pc|pack|count|ct|set|x)\b")
NUM = re.compile(r"\b\d+\b")
GENERIC = {"set", "kit", "pack", "case", "cover", "holder", "stand", "bag", "box", "tool", "accessory",
           "accessories", "for", "with", "and", "the", "a", "of", "new", "premium", "best", "pro"}


def norm(s):
    s = s.lower().replace("&", " and ")
    s = SIZE.sub(" ", s)
    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    s = NUM.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def sg(w):
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("ches", "shes", "xes", "sses")):
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is")) and len(w) > 3:
        return w[:-1]
    return w


def edits1(w):
    letters = "abcdefghijklmnopqrstuvwxyz"
    splits = [(w[:i], w[i:]) for i in range(len(w) + 1)]
    return ({a + b[1:] for a, b in splits if b} |
            {a + b[1] + b[0] + b[2:] for a, b in splits if len(b) > 1} |
            {a + c + b[1:] for a, b in splits if b for c in letters} |
            {a + c + b for a, b in splits for c in letters})

GENDER = {"men": "men", "mens": "men", "man": "men", "male": "men", "gents": "men",
          "women": "women", "womens": "women", "woman": "women", "ladies": "women", "lady": "women", "female": "women",
          "boy": "boys", "boys": "boys", "girl": "girls", "girls": "girls",
          "kid": "kids", "kids": "kids", "child": "kids", "children": "kids", "childrens": "kids", "youth": "kids",
          "baby": "baby", "babies": "baby", "infant": "baby", "infants": "baby", "toddler": "baby", "newborn": "baby"}
MATERIAL = set("""cotton polyester leather plastic plastics textile synthetic wood wooden metal steel nylon wool bamboo stainless
glass rayon aluminum aluminium acrylic rubber pu silk silicone paper ceramic viscose spandex denim canvas pvc jute linen
porcelain rattan gold silver teak fleece fabric cashmere iron sterling marble felt straw reptile brass carbon vegan resin
crystal foam wicker lace seagrass stone vinyl titanium copper pearl enamel modal microfiber melamine borosilicate mdf
particleboard stoneware faux satin velvet nitrile cork merino concrete latex elastane lycra polypropylene polyethylene
cardboard suede fur down feather hemp acetate tpu abs zinc chrome tungsten platinum bone earthenware terracotta
cast nonstick tempered gemstone pewter tin slate quartz granite coir sisal alloy""".split())
MATSYN = {"poly": "polyester", "elastane": "spandex", "lycra": "spandex", "aluminium": "aluminum", "wooden": "wood",
          "pleather": "pu", "plastics": "plastic", "inox": "stainless", "ss": "stainless"}
VSTOP = {"or", "and", "with", "other", "only", "of", "for", "by", "in", "on", "the", "a", "an", "type", "style", "like",
         "material", "part", "over", "under", "less", "more", "to", "per", "valued", "cents", "dozen", "up", "w", "kw",
         "va", "g", "cm", "mm", "inch", "liters", "years", "sizes", "size", "made", "well"}
NEG = {"not", "no", "without", "non"}
NONELECTRIC = {"ceramic", "porcelain", "stoneware", "earthenware", "glass", "wood", "wooden", "bamboo", "enamel", "enameled",
               "terracotta", "clay"}
POWERCUE = {"electric", "electrical", "electronic", "plug", "plugin", "cordless", "rechargeable", "usb", "battery",
            "powered", "watt", "watts", "automatic", "smart", "digital", "heated", "heating", "motor", "machine"}
PARTWORDS = {"frame", "base", "top", "leg", "finish", "handle", "sole", "upper", "lining", "shell", "body", "strap",
             "band", "lid", "cover", "construction", "seat", "back", "trim", "tip", "blade", "head"}
PREP = {"with", "for", "from", "in", "to", "by", "compatible", "fits", "fit", "made", "includes", "including"}
SOFT = {"upper", "sole", "genuine", "collapsible", "natural", "solid", "real", "pure", "blend", "garment", "shell",
        "frame", "base", "cover", "covering", "fiber", "fibers", "yarn", "man", "sewn", "lined", "printed", "knit",
        "woven", "textile", "molded", "moulded", "wickerwork", "fine", "quality", "body", "outer", "soft", "sided",
        "hard", "structured", "surface", "sheeting", "rigid", "plain", "regular", "standard", "household", "blue", "black",
        "colored", "waterproof", "mesh", "covering", "power", "loomed", "machine", "made"}
MATFALL = {"textile": {"fabric", "polyester", "nylon", "synthetic"}, "fabric": {"textile", "polyester", "nylon"},
           "plastic": {"pu", "pvc", "vinyl", "acrylic", "synthetic", "abs", "polycarbonate"},
           "metal": {"steel", "iron", "aluminum"}, "steel": {"metal", "iron"}, "stainless": {"steel", "metal"},
           "aluminum": {"metal"}, "iron": {"metal", "steel"}, "ceramic": {"stoneware", "earthenware"},
           "porcelain": {"china", "ceramic"}, "brass": {"metal"}, "copper": {"metal"}, "zinc": {"metal"},
           "alloy": {"metal"}, "cotton": {"denim"}, "denim": {"cotton"}}


def vtokens(s):
    s = s.lower().replace("'", "").replace("-", " ")
    s = re.sub(r"\(([^)]*)\)", r" \1 ", s)
    s = s.replace(",", " , ")
    return s.split()


def cat(tok):
    if tok in GENDER:
        return "g"
    if tok in MATERIAL:
        return "m"
    return "d"


def parse_when(when):
    """Return list of groups: (category, set_of_alternatives, negative)."""
    groups, conn, neg = [], None, False
    for tok in vtokens(when):
        if tok == ",":
            conn = ","
            continue
        if tok == "or":
            conn = "or"
            continue
        if tok in NEG:
            neg = True
            continue
        if any(ch.isdigit() for ch in tok) or "$" in tok or "%" in tok or tok in VSTOP:
            continue
        tok = GENDER.get(tok, MATSYN.get(tok, tok))
        if tok.endswith("s") and tok[:-1] in MATERIAL:
            tok = tok[:-1]
        c = cat(tok)
        if groups and not neg and not groups[-1][2] and (conn == "or" or (conn == "," and groups[-1][0] == c and c == "m")):
            pc, alts, _ = groups[-1]
            groups[-1] = (pc if pc != "d" else c, alts | {tok}, False)
        else:
            groups.append((c, {tok}, neg))
        conn, neg = None, False
    return groups


def text_attrs(words):
    t = " ".join(words)
    t = re.sub(r"\bflat weave\b", "flatweave", t)
    t = re.sub(r"\b(rubber|plastic|tpr|eva|synthetic|foam|pu) (out)?soles?\b", r"\1", t)
    t = re.sub(r"\b(gold|silver|rose gold|rhodium|chrome) (plated|plate|tone|toned|finish)\b", r"plated", t)
    words = t.split()
    toks, skip = set(), False
    for w in words:
        if w in NEG:
            skip = True
            continue
        if skip:  # "not upholstered", "no lining": the word is ruled out, not stated
            skip = False
            continue
        w = w.replace("'", "")
        w = GENDER.get(w, MATSYN.get(w, w))
        toks.add(w)
        if w.endswith("s") and w[:-1] in MATERIAL:
            toks.add(w[:-1])
    if re.search(r"\b(faux|vegan|synthetic|pu|imitation|artificial) leather\b|\bpleather\b", t):
        toks |= {"pu", "synthetic", "plastic", "vegan", "faux"}
    if re.search(r"\b(bed|table|kitchen|bath|household) linens?\b", t):
        toks.discard("linen")
    fibers = {"cotton", "polyester", "nylon", "wool", "silk", "linen", "rayon", "viscose", "acrylic", "spandex", "jute"}
    if toks & {"textile", "fabric", "cloth"} and not toks & fibers:
        toks |= {"polyester", "nylon", "synthetic"}
    if "kids" in toks:
        toks |= {"boys"}
    return toks


def pick_variant(entry, words):
    v = _pick_variant(entry, text_attrs(words))
    if v is None:  # retry with broader material words (textile -> polyester, plastic -> PU)
        toks = text_attrs(words)
        wide = set(toks)
        for t in toks:
            wide |= MATFALL.get(t, set())
        if wide != toks:
            v = _pick_variant(entry, wide)
    return v


def _pick_variant(entry, toks):
    vs = entry.get("variants") or []
    if not vs:
        return None
    text_cats = {cat(x) for x in toks}
    # attributes implied by the default line, used for categories the text does not state
    fill = {}
    for v in vs:
        if v.get("hts10") == entry["hts10"]:
            for c, alts, neg in parse_when(v.get("when", "")):
                if c in ("g", "m") and not neg and c not in text_cats and c not in fill:
                    fill[c] = alts
            break
    best, best_key, lenient = None, None, []
    for idx, v in enumerate(vs):
        groups = parse_when(v.get("when", ""))
        if not groups:
            continue
        has_key = any(c in ("g", "m") and not n for c, _, n in groups)
        ok, from_text, total, missing, covered, hard_miss, desc_hit = True, 0, 0, 0, set(), 0, 0
        for c, alts, neg in groups:
            if neg:
                if alts & toks:
                    ok = False
                    break
                continue
            if alts & toks:
                from_text += 1
                total += 1
                covered |= alts & toks
                if c == "d" and not alts & SOFT:
                    desc_hit += 1
            elif c in fill and alts & fill[c]:
                total += 1
            elif c == "d" and alts & SOFT:
                missing += 1
            elif c == "d" and has_key:
                hard_miss += 1
            else:
                ok = False
                break
        if not ok or from_text == 0:
            continue
        if hard_miss:
            # a specific descriptor the text did not state (enameled, mesh); allowed only when the text
            # confirms another descriptor of this variant, and ranked below full matches
            if not desc_hit:
                continue
            lenient.append(((len(covered), from_text, -hard_miss - missing, total, -idx), v))
            continue
        key = (len(covered), from_text, -missing, total, -idx)
        if best_key is None or key > best_key:
            best, best_key = v, key
    if lenient:
        lk, lv = max(lenient, key=lambda x: x[0])
        if best_key is None or lk[0] > best_key[0]:
            best, best_key = lv, lk
    if best is not None and best_key[2] < 0:
        # the best variant leaves some of its words unconfirmed; keep the default when the default
        # assumption already covers every material and gender the text states
        assumed = set(re.findall(r"[a-z]+", (entry.get("default_assumption") or "").lower().replace("'", "")))
        assumed = {GENDER.get(w, w) for w in assumed}
        stated = {x for x in toks if cat(x) in ("g", "m")}
        matched = set(re.findall(r"[a-z]+", best.get("when", "").lower().replace("'", ""))) & toks
        if stated and stated <= assumed and matched <= stated:
            return None
    return best


class Matcher:
    def __init__(self, dist):
        self.entries = json.load(open(os.path.join(dist, "lexicon.json")))
        self.alias = collections.defaultdict(set)
        self.kind = {}
        for r in csv.DictReader(open(os.path.join(dist, "aliases.csv"))):
            self.alias[r["alias"]].add(r["entry_id"])
            if r["kind"] == "term":
                self.kind[(r["alias"], r["entry_id"])] = "term"
        self.miss = {r["misspelling"]: r["correct_word"] for r in csv.DictReader(open(os.path.join(dist, "misspellings.csv")))}
        self.vocab = {w for a in self.alias for w in a.split()}
        self.freq = collections.Counter(w for a in self.alias for w in a.split())
        self.final_words = {a.split()[-1] for a in self.alias} | {sg(a.split()[-1]) for a in self.alias}
        self.alias_sg = collections.defaultdict(set)  # word order and number tolerant index
        for a, ids in self.alias.items():
            self.alias_sg[" ".join(sg(w) for w in a.split())] |= ids
        self.maxlen = max(len(a.split()) for a in self.alias)

    def fix(self, words):
        out = []
        for w in words:
            if w in self.vocab:
                out.append(w)
            elif w in self.miss:
                out.append(self.miss[w])
            elif len(w) >= 5:
                cands = [c for c in edits1(w) if c in self.vocab]
                if not cands and len(w) >= 8:
                    cands = list({c2 for c1 in edits1(w) for c2 in edits1(c1) if c2 in self.vocab})
                out.append(self.best_candidate(w, cands) if cands else w)
            else:
                out.append(w)
        return out

    def best_candidate(self, w, cands):
        """Prefer a candidate that keeps the first letter, then the most common word in the aliases."""
        return sorted(cands, key=lambda c: (c[0] != w[0], -self.freq.get(c, 0), c))[0]

    def head_index(self, words):
        """Index of the head noun: last plain word before the first preposition, skipping materials,
        genders, generic words and descriptors that no alias uses as its final word."""
        end = len(words)
        for k, w in enumerate(words):
            if k > 0 and w in PREP:
                end = k
                break
        for k in range(end - 1, -1, -1):
            w = words[k]
            if w in GENERIC or w in GENDER or w in MATERIAL or sg(w) in MATERIAL:
                continue
            if k > 0 and words[k - 1] in MATERIAL and sg(w) in PARTWORDS:
                continue
            if w in self.final_words or sg(w) in self.final_words:
                return k
        return None

    def match(self, text):
        words = self.fix(norm(text).split())
        t = " ".join(words)
        head = self.head_index(words)
        scores = collections.Counter()
        hits = collections.defaultdict(list)
        for n in range(min(self.maxlen, len(words)), 0, -1):
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i:i + n])
                ids = self.alias.get(phrase) or self.alias_sg.get(" ".join(sg(w) for w in words[i:i + n]), ())
                for eid in ids:
                    s = sum(1 if w in GENERIC else 3 for w in words[i:i + n])
                    if head is not None and i <= head < i + n:
                        s += 2.5
                    if self.kind.get((phrase, eid)) == "term":
                        s += 0.5
                    if n == 1 and phrase in GENERIC:
                        s -= 1
                    if s > scores[eid]:
                        scores[eid] = s
                    hits[eid].append(phrase)
        # a non-electric material with no power cue means a houseware, not an appliance
        if set(words) & NONELECTRIC and not set(words) & POWERCUE:
            for eid in list(scores):
                if self.entries[eid].get("category") in ("appliances", "electronics"):
                    scores[eid] -= 4
        if not scores:
            return {"input": text, "normalized": t, "confidence": "none"}
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))  # score, then id for stable ties
        eid, best = ranked[0]
        e = self.entries[eid]
        longest = max(len(h.split()) for h in hits[eid])
        conf = "exact" if t in hits[eid] else ("strong" if longest >= 2 else "weak")
        hts, assumption, applied = e["hts10"], e.get("default_assumption", ""), []
        v = pick_variant(e, words)
        if v:
            hts, assumption = v["hts10"], v.get("note", "") or "Matched stated attribute: " + v["when"]
            applied.append(v["when"])
        runners = [x for x, s in ranked[1:4] if s >= best - 1]
        return {"input": text, "normalized": t, "entry_id": eid, "term": e["term"], "hts10": hts,
                "assumption": assumption, "applied_variants": applied, "confidence": conf,
                "matched_phrases": sorted(set(hits[eid]), key=len, reverse=True)[:3],
                "close_alternatives": [{"entry_id": r, "hts10": self.entries[r]["hts10"]} for r in runners]}


if __name__ == "__main__":
    import sys
    m = Matcher(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist"))
    for q in sys.argv[1:]:
        print(json.dumps(m.match(q), indent=1))
