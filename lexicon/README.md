# DutyDrop product lexicon

The lexicon turns product words into a 10 digit HTS line before the existing search runs. It covers what small importers actually type: synonyms, plurals, US and UK names, marketplace titles, brand names that mean a generic product (airpods, yeti, crocs, kleenex, lego), typos, and stated materials and genders that change the line.

## What is in it

| | Count |
|---|---|
| Product entries | 2,706 |
| Aliases, including plurals and singulars | 43,807 |
| Misspellings (typo to correct word) | 294,613 |
| Variant rules (material, gender, power, value) | 6,566 |
| Distinct 10 digit HTS lines | 2,432 |

Categories: kitchen, home, furniture, apparel, footwear, accessories, beauty, office, packaging, electronics, appliances, lighting, tools, auto, garden, toys, sports, baby, pet, and misc.

Every main code and every variant code has been checked: each one is a Statistical (10) line in HTS 2026 Rev 21 (`data/hts.csv`), or an 8 digit tariff line with no statistical split, written with the suffix 00 (wall clocks, analog watches). `validate.py` enforces this and reports 0 errors.

## Test results

| Test | Result |
|---|---|
| The 200 curated SEO products (`eval/diego200.txt`) | 200 of 200 resolve to an HTS line. Line by line in `eval/diego200_results.csv` |
| Seller-style query set (`eval/eval_set.csv`, 211 queries, 6 digit check) | 210 of 211 |
| Blind set: 300 queries written by a separate agent that never saw the dictionary (`eval/blind_set.csv`) | 277 of 300 (92%) on first run (`eval/blind_report.txt`). After fixing the matcher bugs it exposed: 293 of 300 (`eval/blind_report_after_fixes.txt`). After James's code review (126 lines, decisions applied in patches/): 300 of 300 (`eval/blind_report_after_review.txt`); two blind answers were overridden by his rulings (infant car seat 9401.80, flannel pajama pants 6207.91) |

Speed: under 1 ms per query in Python and in Node. Loading takes about 1.5 s, so load once at startup.

## Files

```
dist/lexicon.json        entries keyed by id: term, aliases, hts10, default_assumption, variants, notes
dist/aliases.csv         alias,entry_id,kind  (kind = term | alias | plural)
dist/misspellings.csv    misspelling,correct_word
dist/stats.json          counts
match.py                 reference matcher, Python, no dependencies (same stack as the engine)
match.mjs                the same matcher in JavaScript for the TypeScript app; gives identical results on all 719 test queries
parts/*.jsonl            source entries, one file per category group
patches/                 broker resolutions: code overrides, extra aliases, removed aliases, extra entries and variants
validate.py build.py score.py
eval/                    test sets and results
```

## How to wire it in

One function goes in front of every place a product description becomes an HTS code.

```python
from lexicon.match import Matcher
LEX = Matcher("lexicon/dist")          # load once at startup

def classify(text):
    hit = LEX.match(text)
    if hit["confidence"] in ("exact", "strong"):
        return hit                     # use hit["hts10"]; print hit["assumption"] on the receipt
    old = existing_search(text)        # today's retrieval
    if hit["confidence"] == "weak" and (not old or old.score < WEAK_THRESHOLD):
        return hit
    return old or hit
```

JavaScript is the same: `const LEX = await Matcher.fromDir("lexicon/dist"); LEX.match(text)`.

Where to call it:

1. **Free search.** Call it on the typed text before retrieval.
2. **Photo receipt.** The vision step already returns a product name and material. Pass `"<material> <product name>"` (for example "stainless steel water bottle") to `match`. Pass the model's free-text description too, and keep whichever result has the higher confidence.
3. **Bulk receipts.** Call it on `product_description` for every row that has no `hts_code`. The bulk auto-resolve rules (3088542) still run afterwards.
4. **SEO pages.** Regenerate each `/tariff/<product>-from-<country>` page from the matched `hts10`. All 200 curated products now resolve.

What `match` returns:

```json
{
 "entry_id": "ceramic-mug",
 "term": "ceramic mug",
 "hts10": "6912.00.44.00",
 "assumption": "Assumes stoneware or earthenware, not porcelain.",
 "applied_variants": [],
 "confidence": "strong",
 "matched_phrases": ["ceramic mug"],
 "close_alternatives": [{"entry_id": "...", "hts10": "..."}]
}
```

Receipt rules:

- When `applied_variants` is not empty, print "Matched what you told us: <variant>".
- Otherwise print `assumption` as the line's assumption, because the default depends on facts the seller did not state, such as material, gender or value.
- Show `close_alternatives` as "Also possible" lines.
- Rates still come only from the HTS and overlay files. The lexicon picks the line and never the rate.

## How matching works

1. **Normalize.** Lowercase the text and strip sizes, counts and punctuation ("12oz", "2-pack" and "30cm" go).
2. **Fix spelling.** Look each word up in the misspellings table. If that fails, try a one-letter fuzzy fix against the vocabulary, for words of 5 or more letters.
3. **Find aliases.** Search phrases longest first, ignoring word order and plurals. Three things raise a phrase's score: covering more words, covering the head noun (the last real noun before "for" or "with", so "christmas tree ornaments" is an ornament, not a tree), and being the canonical term.
4. **Pick a variant.** Read the materials and genders the text states. Fill in anything unstated from the default line, so "women's polyester t-shirt" lands on the women's polyester line. Broad words widen to their usual meaning: "textile" becomes polyester or nylon, and "plastic" becomes PU or PVC. Negations count, so "not upholstered" rules out upholstered lines.
5. **Return** the line, the assumption, the confidence and the alternatives.

## Updating

The build scripts read the HTS file from `data/hts.csv`. Copy `US_HTS_Database_2026_Rev21_database.csv` there first. It is not committed.


- To add an alias, add a row to `patches/aliases_extra.csv`.
- To change a default code, edit `patches/overrides.json`.
- To add a product, add a line to `patches/entries_extra.jsonl` using the schema in `SCHEMA.md`.
- Then run `python3 validate.py && python3 validate.py patches && python3 build.py && python3 score.py`. Keep `score.py` at or above its current result before you ship.
- For a new HTS revision, rerun `validate.py` against the new `hts.csv`. It lists every code that moved.

## Broker review list

These are estimates, not rulings. Before high volume, a licensed broker should look at three things:

- **33 cross-file conflicts.** Two builders picked different lines for the same product. Each entry keeps the losing code under `conflicts`, and the chosen code is in `patches/overrides.json` or is the first file's pick.
- **88 entries marked "check".** Their `notes` or variant notes say why. Examples: air fryers, wireless chargers, UV nail lamps, staple guns, pet carriers, and car seats against 9401.20.
- **Antidumping or countervailing duty exposure.** Candles, mattresses, wooden cabinets, boltless steel shelving, lined paper and notebooks, and PE retail carrier bags carry a note.

Wall clocks, alarm clocks and analog watches use 8 digit lines plus 00, because Rev 21 has no statistical split for them. Their duty is compound (per item plus percent), so check how the receipt prints it.
