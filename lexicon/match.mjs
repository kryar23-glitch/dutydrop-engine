// DutyDrop lexicon matcher, JavaScript port of match.py. Same input, same output.
// Node 18+ or any bundler. No dependencies.
//
//   import { Matcher } from "./match.mjs";
//   const m = Matcher.fromDir("dist");          // Node: reads dist/lexicon.json, aliases.csv, misspellings.csv
//   m.match("Ceramic cofee mugs, 12oz");        // { entry_id, term, hts10, assumption, confidence, ... }
//
// In a browser or edge runtime, load the three files yourself and call new Matcher(entries, aliasRows, missRows).

const SIZE = /\b\d+(\.\d+)?\s*(oz|ml|l|cm|mm|m|in|inch|inches|ft|lb|lbs|kg|g|pcs|pc|pack|count|ct|set|x)\b/g;
const NUM = /\b\d+\b/g;
const GENERIC = new Set(["set", "kit", "pack", "case", "cover", "holder", "stand", "bag", "box", "tool", "accessory",
  "accessories", "for", "with", "and", "the", "a", "of", "new", "premium", "best", "pro"]);
const GENDER = {
  men: "men", mens: "men", man: "men", male: "men", gents: "men",
  women: "women", womens: "women", woman: "women", ladies: "women", lady: "women", female: "women",
  boy: "boys", boys: "boys", girl: "girls", girls: "girls",
  kid: "kids", kids: "kids", child: "kids", children: "kids", childrens: "kids", youth: "kids",
  baby: "baby", babies: "baby", infant: "baby", infants: "baby", toddler: "baby", newborn: "baby",
};
const MATERIAL = new Set(`cotton polyester leather plastic plastics textile synthetic wood wooden metal steel nylon wool bamboo stainless
glass rayon aluminum aluminium acrylic rubber pu silk silicone paper ceramic viscose spandex denim canvas pvc jute linen
porcelain rattan gold silver teak fleece fabric cashmere iron sterling marble felt straw reptile brass carbon vegan resin
crystal foam wicker lace seagrass stone vinyl titanium copper pearl enamel modal microfiber melamine borosilicate mdf
particleboard stoneware faux satin velvet nitrile cork merino concrete latex elastane lycra polypropylene polyethylene
cardboard suede fur down feather hemp acetate tpu abs zinc chrome tungsten platinum bone earthenware terracotta
cast nonstick tempered gemstone pewter tin slate quartz granite coir sisal alloy`.split(/\s+/));
const MATSYN = { poly: "polyester", elastane: "spandex", lycra: "spandex", aluminium: "aluminum", wooden: "wood",
  pleather: "pu", plastics: "plastic", inox: "stainless", ss: "stainless" };
const VSTOP = new Set(["or", "and", "with", "other", "only", "of", "for", "by", "in", "on", "the", "a", "an", "type", "style",
  "like", "material", "part", "over", "under", "less", "more", "to", "per", "valued", "cents", "dozen", "up", "w", "kw",
  "va", "g", "cm", "mm", "inch", "liters", "years", "sizes", "size", "made", "well"]);
const NEG = new Set(["not", "no", "without", "non"]);
const PREP = new Set(["with", "for", "from", "in", "to", "by", "compatible", "fits", "fit", "made", "includes", "including"]);
const SOFT = new Set(["upper", "sole", "genuine", "collapsible", "natural", "solid", "real", "pure", "blend", "garment", "shell",
  "frame", "base", "cover", "covering", "fiber", "fibers", "yarn", "man", "sewn", "lined", "printed", "knit",
  "woven", "textile", "molded", "moulded", "wickerwork", "fine", "quality", "body", "outer", "soft", "sided",
  "hard", "structured", "surface", "sheeting", "rigid", "plain", "regular", "standard", "household", "blue", "black",
  "colored", "waterproof", "mesh", "covering", "power", "loomed", "machine", "made"]);
const NONELECTRIC = new Set(["ceramic", "porcelain", "stoneware", "earthenware", "glass", "wood", "wooden", "bamboo", "enamel",
  "enameled", "terracotta", "clay"]);
const POWERCUE = new Set(["electric", "electrical", "electronic", "plug", "plugin", "cordless", "rechargeable", "usb", "battery",
  "powered", "watt", "watts", "automatic", "smart", "digital", "heated", "heating", "motor", "machine"]);
const PARTWORDS = new Set(["frame", "base", "top", "leg", "finish", "handle", "sole", "upper", "lining", "shell", "body", "strap",
  "band", "lid", "cover", "construction", "seat", "back", "trim", "tip", "blade", "head"]);
const MATFALL = {
  textile: ["fabric", "polyester", "nylon", "synthetic"], fabric: ["textile", "polyester", "nylon"],
  plastic: ["pu", "pvc", "vinyl", "acrylic", "synthetic", "abs", "polycarbonate"],
  metal: ["steel", "iron", "aluminum"], steel: ["metal", "iron"], stainless: ["steel", "metal"],
  aluminum: ["metal"], iron: ["metal", "steel"], ceramic: ["stoneware", "earthenware"], porcelain: ["china", "ceramic"],
  brass: ["metal"], copper: ["metal"], zinc: ["metal"], alloy: ["metal"], cotton: ["denim"], denim: ["cotton"],
};
const FIBERS = ["cotton", "polyester", "nylon", "wool", "silk", "linen", "rayon", "viscose", "acrylic", "spandex", "jute"];
const LETTERS = "abcdefghijklmnopqrstuvwxyz";

const gmap = (w) => GENDER[w] ?? MATSYN[w] ?? w;
const intersects = (a, b) => { for (const x of a) if (b.has(x)) return true; return false; };

export function norm(s) {
  s = s.toLowerCase().replaceAll("&", " and ");
  s = s.replace(SIZE, " ");
  s = s.replace(/[^a-z0-9' ]+/g, " ");
  s = s.replace(NUM, " ");
  return s.replace(/\s+/g, " ").trim();
}

export function sg(w) {
  if (w.endsWith("ies") && w.length > 4) return w.slice(0, -3) + "y";
  if (["ches", "shes", "xes", "sses"].some((e) => w.endsWith(e))) return w.slice(0, -2);
  if (w.endsWith("s") && !["ss", "us", "is"].some((e) => w.endsWith(e)) && w.length > 3) return w.slice(0, -1);
  return w;
}

function edits1(w) {
  const out = new Set();
  for (let i = 0; i <= w.length; i++) {
    const a = w.slice(0, i), b = w.slice(i);
    if (b) out.add(a + b.slice(1));
    if (b.length > 1) out.add(a + b[1] + b[0] + b.slice(2));
    for (const c of LETTERS) {
      if (b) out.add(a + c + b.slice(1));
      out.add(a + c + b);
    }
  }
  return out;
}

function vtokens(s) {
  s = s.toLowerCase().replaceAll("'", "").replaceAll("-", " ");
  s = s.replace(/\(([^)]*)\)/g, " $1 ");
  s = s.replaceAll(",", " , ");
  return s.split(/\s+/).filter(Boolean);
}

function cat(tok) {
  if (tok in GENDER) return "g";
  if (MATERIAL.has(tok)) return "m";
  return "d";
}

const whenCache = new Map();
function parseWhen(when) {
  if (whenCache.has(when)) return whenCache.get(when);
  const groups = [];
  let conn = null, neg = false;
  for (let tok of vtokens(when)) {
    if (tok === ",") { conn = ","; continue; }
    if (tok === "or") { conn = "or"; continue; }
    if (NEG.has(tok)) { neg = true; continue; }
    if (/\d/.test(tok) || tok.includes("$") || tok.includes("%") || VSTOP.has(tok)) continue;
    tok = gmap(tok);
    if (tok.endsWith("s") && MATERIAL.has(tok.slice(0, -1))) tok = tok.slice(0, -1);
    const c = cat(tok);
    const last = groups[groups.length - 1];
    if (last && !neg && !last.neg && (conn === "or" || (conn === "," && last.c === c && c === "m"))) {
      last.alts.add(tok);
      if (last.c === "d") last.c = c;
    } else {
      groups.push({ c, alts: new Set([tok]), neg });
    }
    conn = null; neg = false;
  }
  whenCache.set(when, groups);
  return groups;
}

function textAttrs(input) {
  let t = input.join(" ");
  t = t.replace(/\bflat weave\b/g, "flatweave");
  t = t.replace(/\b(rubber|plastic|tpr|eva|synthetic|foam|pu) (out)?soles?\b/g, "$1");
  t = t.replace(/\b(gold|silver|rose gold|rhodium|chrome) (plated|plate|tone|toned|finish)\b/g, "plated");
  const toks = new Set();
  let skip = false;
  for (let w of t.split(" ").filter(Boolean)) {
    if (NEG.has(w)) { skip = true; continue; }
    if (skip) { skip = false; continue; } // "not upholstered": ruled out, not stated
    w = gmap(w.replaceAll("'", ""));
    toks.add(w);
    if (w.endsWith("s") && MATERIAL.has(w.slice(0, -1))) toks.add(w.slice(0, -1));
  }
  if (/\b(faux|vegan|synthetic|pu|imitation|artificial) leather\b|\bpleather\b/.test(t)) {
    for (const x of ["pu", "synthetic", "plastic", "vegan", "faux"]) toks.add(x);
  }
  if (/\b(bed|table|kitchen|bath|household) linens?\b/.test(t)) toks.delete("linen");
  if (["textile", "fabric", "cloth"].some((x) => toks.has(x)) && !FIBERS.some((x) => toks.has(x))) {
    for (const x of ["polyester", "nylon", "synthetic"]) toks.add(x);
  }
  if (toks.has("kids")) toks.add("boys");
  return toks;
}

const words = (s) => new Set((s || "").toLowerCase().match(/[a-z]+/g) || []);

function cmpKey(a, b) { // lexicographic compare of [from_text, -missing, total, -idx]
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] - b[i];
  return 0;
}

function pickVariantInner(entry, toksIn) {
  const vs = entry.variants || [];
  if (!vs.length) return null;
  // the product's own name words ("desk" in "office desk") never count as a stated attribute
  const termWords = entry.term.toLowerCase().split(/\s+/).filter((w) => cat(w) === "d");
  const name = new Set([...termWords, ...termWords.map(sg)]);
  const toks = toksIn;
  const textCats = new Set([...toks].map(cat));
  const fill = {};
  for (const v of vs) {
    if (v.hts10 === entry.hts10) {
      for (const g of parseWhen(v.when || "")) {
        if ((g.c === "g" || g.c === "m") && !g.neg && !textCats.has(g.c) && !(g.c in fill)) fill[g.c] = g.alts;
      }
      break;
    }
  }
  let best = null, bestKey = null;
  const lenient = [];
  vs.forEach((v, idx) => {
    const groups = parseWhen(v.when || "");
    if (!groups.length) return;
    const hasKey = groups.some((g) => (g.c === "g" || g.c === "m") && !g.neg);
    let ok = true, fromText = 0, total = 0, missing = 0, hardMiss = 0, descHit = 0;
    const covered = new Set();
    for (const g of groups) {
      if (g.neg) { if (intersects(g.alts, toks)) { ok = false; break; } continue; }
      if (intersects(g.alts, toks)) {
        fromText++; total++;
        for (const a of g.alts) if (toks.has(a)) covered.add(a);
        if (g.c === "d" && !intersects(g.alts, SOFT) && ![...g.alts].every((x) => name.has(x))) descHit++;
      } else if (fill[g.c] && intersects(g.alts, fill[g.c])) { total++; }
      else if (g.c === "d" && intersects(g.alts, SOFT)) { missing++; }
      else if (g.c === "d" && hasKey) { hardMiss++; }
      else { ok = false; break; }
    }
    if (!ok || fromText === 0) return;
    if (hardMiss) {
      if (!descHit) return;
      lenient.push([[covered.size, fromText, -hardMiss - missing, total, -idx], v]);
      return;
    }
    const key = [covered.size, fromText, -missing, total, -idx];
    if (bestKey === null || cmpKey(key, bestKey) > 0) { best = v; bestKey = key; }
  });
  if (lenient.length) {
    let [lk, lv] = lenient[0];
    for (const [k, x] of lenient) if (cmpKey(k, lk) > 0) { lk = k; lv = x; }
    if (bestKey === null || lk[0] > bestKey[0]) { best = lv; bestKey = lk; }
  }
  if (best && bestKey[2] < 0) {
    const assumed = new Set([...words((entry.default_assumption || "").replaceAll("'", ""))].map((w) => GENDER[w] ?? w));
    const stated = [...toks].filter((x) => cat(x) === "g" || cat(x) === "m");
    const matched = [...words((best.when || "").replaceAll("'", ""))].filter((x) => toks.has(x));
    if (stated.length && stated.every((x) => assumed.has(x)) && matched.every((x) => stated.includes(x))) return null;
  }
  return best;
}

function pickVariant(entry, ws) {
  let v = pickVariantInner(entry, textAttrs(ws));
  if (v === null) {
    const toks = textAttrs(ws);
    const wide = new Set(toks);
    for (const t of toks) for (const x of MATFALL[t] || []) wide.add(x);
    if (wide.size !== toks.size) v = pickVariantInner(entry, wide);
  }
  return v;
}

function parseCsv(text) { // small CSV reader: quoted fields, commas, newlines
  const rows = []; let row = [], f = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += ch;
    } else if (ch === '"') q = true;
    else if (ch === ",") { row.push(f); f = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(f); rows.push(row); row = []; f = "";
    } else f += ch;
  }
  if (f || row.length) { row.push(f); rows.push(row); }
  const head = rows.shift();
  return rows.filter((r) => r.length === head.length).map((r) => Object.fromEntries(head.map((h, i) => [h, r[i]])));
}

export class Matcher {
  constructor(entries, aliasRows, missRows) {
    this.entries = entries;
    this.alias = new Map();
    this.kind = new Set();
    for (const r of aliasRows) {
      if (!this.alias.has(r.alias)) this.alias.set(r.alias, new Set());
      this.alias.get(r.alias).add(r.entry_id);
      if (r.kind === "term") this.kind.add(r.alias + "\u0000" + r.entry_id);
    }
    this.miss = new Map(missRows.map((r) => [r.misspelling, r.correct_word]));
    this.vocab = new Set();
    this.freq = new Map();
    this.finalWords = new Set();
    this.aliasSg = new Map();
    this.maxlen = 1;
    for (const [a, ids] of this.alias) {
      const ws = a.split(" ");
      for (const w of ws) { this.vocab.add(w); this.freq.set(w, (this.freq.get(w) || 0) + 1); }
      const last = ws[ws.length - 1];
      this.finalWords.add(last); this.finalWords.add(sg(last));
      const key = ws.map(sg).join(" ");
      if (!this.aliasSg.has(key)) this.aliasSg.set(key, new Set());
      for (const id of ids) this.aliasSg.get(key).add(id);
      this.maxlen = Math.max(this.maxlen, ws.length);
    }
  }

  static async fromDir(dir) {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const read = (f) => fs.readFileSync(path.join(dir, f), "utf8");
    return new Matcher(JSON.parse(read("lexicon.json")), parseCsv(read("aliases.csv")), parseCsv(read("misspellings.csv")));
  }

  fix(ws) {
    return ws.map((w) => {
      if (this.vocab.has(w)) return w;
      if (this.miss.has(w)) return this.miss.get(w);
      if (w.length >= 5) {
        let c = [...edits1(w)].filter((x) => this.vocab.has(x));
        if (!c.length && w.length >= 8) {
          const two = new Set();
          for (const a of edits1(w)) for (const b of edits1(a)) if (this.vocab.has(b)) two.add(b);
          c = [...two];
        }
        if (!c.length) return w;
        // keep the first letter if possible, then the most common alias word, then alphabetical
        c.sort((a, b) => ((a[0] !== w[0]) - (b[0] !== w[0])) || ((this.freq.get(b) || 0) - (this.freq.get(a) || 0)) || (a < b ? -1 : a > b ? 1 : 0));
        return c[0];
      }
      return w;
    });
  }

  headIndex(ws) {
    let end = ws.length;
    for (let k = 1; k < ws.length; k++) if (PREP.has(ws[k])) { end = k; break; }
    for (let k = end - 1; k >= 0; k--) {
      const w = ws[k];
      if (GENERIC.has(w) || w in GENDER || MATERIAL.has(w) || MATERIAL.has(sg(w))) continue;
      if (k > 0 && MATERIAL.has(ws[k - 1]) && PARTWORDS.has(sg(w))) continue;
      if (this.finalWords.has(w) || this.finalWords.has(sg(w))) return k;
    }
    return null;
  }

  match(text) {
    const ws = this.fix(norm(text).split(" ").filter(Boolean));
    const t = ws.join(" ");
    const head = this.headIndex(ws);
    const scores = new Map(), hits = new Map();
    for (let n = Math.min(this.maxlen, ws.length); n >= 1; n--) {
      for (let i = 0; i + n <= ws.length; i++) {
        const slice = ws.slice(i, i + n), phrase = slice.join(" ");
        const ids = this.alias.get(phrase) || this.aliasSg.get(slice.map(sg).join(" ")) || [];
        for (const eid of ids) {
          let s = slice.reduce((acc, w) => acc + (GENERIC.has(w) ? 1 : 3), 0);
          if (head !== null && i <= head && head < i + n) s += 2.5;
          if (this.kind.has(phrase + "\u0000" + eid)) s += 0.5;
          if (n === 1 && GENERIC.has(phrase)) s -= 1;
          if (s > (scores.get(eid) ?? 0)) scores.set(eid, s);
          if (!hits.has(eid)) hits.set(eid, []);
          hits.get(eid).push(phrase);
        }
      }
    }
    // a non-electric material with no power cue means a houseware, not an appliance
    if (ws.some((w) => NONELECTRIC.has(w)) && !ws.some((w) => POWERCUE.has(w))) {
      for (const [eid, s] of scores) {
        const c = this.entries[eid].category;
        if (c === "appliances" || c === "electronics") scores.set(eid, s - 4);
      }
    }
    if (!scores.size) return { input: text, normalized: t, confidence: "none" };
    const ranked = [...scores].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
    const [eid, best] = ranked[0];
    const e = this.entries[eid];
    const h = hits.get(eid);
    const longest = Math.max(...h.map((x) => x.split(" ").length));
    const confidence = h.includes(t) ? "exact" : longest >= 2 ? "strong" : "weak";
    let hts10 = e.hts10, assumption = e.default_assumption || "";
    const applied = [];
    const v = pickVariant(e, ws);
    if (v) { hts10 = v.hts10; assumption = v.note || "Matched stated attribute: " + v.when; applied.push(v.when); }
    const runners = ranked.slice(1, 4).filter(([, s]) => s >= best - 1).map(([r]) => ({ entry_id: r, hts10: this.entries[r].hts10 }));
    return {
      input: text, normalized: t, entry_id: eid, term: e.term, hts10, assumption, applied_variants: applied, confidence,
      matched_phrases: [...new Set(h)].sort((a, b) => b.length - a.length).slice(0, 3), close_alternatives: runners,
    };
  }
}
