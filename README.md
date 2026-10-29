# DutyDrop AI Engine v1

Photo or description in, tariff receipt out, for goods imported into the United States. Built to
DutyDrop AI Engine Spec v1 (2026-10-29). Every output is an estimate and carries the disclaimer:
"Estimate only. Check this with a customs broker. DutyDrop is not a customs broker."

## Run it

Requirements: Python 3.9 or newer, Pillow (`pip install -r requirements.txt`). Nothing else.

```
export DUTYDROP_DATA_DIR=~/Claude/hts          # folder holding the HTS and overlay CSVs
export DEEPSEEK_API_KEY=...                     # set in the shell, never in a file in this repo
python3 -m unittest -v tests.test_acceptance    # Spec section 6 suite; writes reports/cost_report.md
python3 -m tools.live_smoke                     # real provider calls; writes reports/live/cost_report.md
python3 -m dutydrop.server --port 8080          # endpoints below
```

The test suite needs no API key. It uses a scripted adapter and reports simulated usage. The live
smoke test needs the key and reports real tokens and cost.

## Data files (DUTYDROP_DATA_DIR)

| File | Built by |
|---|---|
| US_HTS_Database_{REV}_database.csv | tools/data_build/build_hts.py |
| US_Tariff_Overlays_{REV}_catalog.csv, _coverage.csv, _active_by_hts.csv | tools/data_build/build_overlays.py |
| US_General_Note3b_Column2_{REV}.csv | tools/build_column2.py (Column 2 origins from General Note 3(b)) |

REV looks like `2026_Rev21`. Rates and codes come only from these files. If a rate is not in them,
the engine says so and gives no number.

## Drop in a new HTS revision

1. Run build_hts.py and build_overlays.py for the new release; put the outputs in DUTYDROP_DATA_DIR.
2. Run tools/build_column2.py against that release's General Notes text.
3. Run `python3 -m tools.make_manifest 2027_Rev1`, check the printed counts against the build output,
   and commit `dutydrop/manifests/2027_Rev1.json`. The loader refuses a revision with no manifest.
4. Run the test suite. Tests that pin Rev 21 values (counts, list sizes, sample codes) need their
   expected values updated for the new revision; that is the only change, and it is in tests, not code.

The loader picks the newest revision in the folder, or the one in DUTYDROP_DATA_REVISION.

## Endpoints

```
POST /identify  {images[], user_text?}                                   -> ProductDescription
POST /classify  {description?, answers?, audit_id?, images?, user_text?}  -> assigned_code | candidates, questions[], audit_id
POST /estimate  {code, origin, value, entry_date?, mode?, quantity?, quantity_unit?} -> line_items, total | provisional_total, flags
POST /receipt   {images? | description_text?, origin?, value?, tier?, answers?, audit_id?} -> Receipt JSON or needs_input
GET  /hts/{code}
GET  /health
```

Images are base64 strings or data URLs. Follow ups are conversational: when /receipt or /classify
returns questions, send the answers keyed by question id (plus `description` text or new `images`
when asked) with the same audit_id. Origin and customs value are always asked if missing.
`mode` is `current` or `historical` (recovery mode). `tier` is `anonymous` or `free_account`.
No endpoint guesses when no provider key is set; it returns 503 with the reason.

## How it works

| Stage | Module | Model call |
|---|---|---|
| A Identify | adapters/openai_compat.py, imaging.py | one vision call per round, all photos together, downscaled to 1024 px JPEG |
| B Retrieve | retrieval.py | none; BM25 over the local index, narrowed chapter to heading to subheading, diversified |
| C Decide | decide.py | one call over the top 10 shortlist; validation gate rejects any code not in the shortlist and base table |
| D Calculate | calculator.py, status.py | none |
| E Receipt | receipt.py | none |

engine.py runs the stages; store.py writes the audit record (every input, model output, candidate
with evidence and scores, question, answer, decision, data row, and cost) and the result cache.

Decision outcomes: strong assigns the code; marginal asks only discriminating questions; weak asks
for the user's own description and another photo. Two loop rounds at most, then candidates and the
broker route with no assigned code.

## Cost controls (Spec 3A)

* Hard max_tokens: identify 500, decide 400. JSON mode on; DeepSeek thinking disabled (it spent
  about 220 output tokens on a trivial call when left on).
* Fixed system prompts first in every request, byte identical, for the provider cache.
* The model never reads the database; it sees ten truncated candidate lines.
* Cache by photo hash plus description hash: a repeat product costs nothing.
* Per receipt cap of $0.02 checked before every call; on hit the engine returns its best result
  with a cost_cap flag.
* Every call's provider, model, tokens, cached tokens, images, and cost go in the audit record.

Measured on the live provider, 2026-10-29: about $0.0003 per receipt round (identify plus decide),
against the $0.005 target. Prices are the spec's reference figures ($0.14 per M input, $0.28 per M
output). DeepSeek's official pricing page did not render for verification; set
DUTYDROP_PRICE_INPUT_PER_M, DUTYDROP_PRICE_OUTPUT_PER_M, DUTYDROP_PRICE_INPUT_CACHED_PER_M from it and
DUTYDROP_PRICES_VERIFIED=1. The cost report prints whether prices are verified.

## Status by entry date

Program windows are in config.STATUS_RULES: IEEPA ends 2026-02-24, Section 122 runs 2026-02-24 to
2026-07-24, Section 301 forced labor starts 2026-07-24. Line dates come from the data where present
(compiler's notes, "effective through", "on or after"). When a date is missing the line is flagged.

Interpretation used for test 4, flag for review: current mode prices overlays in effect on the entry
date and not ended as of today, so an IEEPA line is excluded from a current estimate even for a
January 2026 entry, and is listed under excluded_overlays. Historical mode prices what was in effect
on the entry date and flags IEEPA and Section 122 lines as refund eligibility candidates, eligibility
language only.

## Where the OPEN items live

| OPEN item | Where | Current behavior |
|---|---|---|
| 1 Vision quality on DeepSeek flash | adapters/openai_compat.py, config.PROVIDER | DeepSeek primary; OpenRouter (Qwen Flash class) and Gemini Flash class wired through the same adapter by env vars |
| 2 Stacking rules table | calculator.estimate, section "5: stacking guardrail" | every overlay itemized; exemptions, in lieu, and conditional overlays listed as alternatives; a total only when one overlay or none applies; otherwise a provisional total labeled config.PROVISIONAL_LABEL |
| 3 Word defined exemptions | calculator._word_exemptions, country_wide_kind | flagged "may be exempt, verify"; overlays limited to goods described in words are flagged, not priced |
| 4 Notes 43, 50, 51 labels | data as published | label kept generic, item carries authority_label_note |
| 5 Thresholds | config.STRONG_SCORE, STRONG_MARGIN, MARGINAL_SCORE, ATTRIBUTE_WEIGHTS | defaults; tune on the golden set |

Other judgment calls to review:
* PROVISIONAL_LABEL reads "Provisional total, before stacking rules. May overstate." The spec's
  wording uses a dash; change the constant if the exact wording matters.
* A marginal match still unresolved after two rounds ends like a weak one: candidates, no code.
* EU member list and origin aliases (config.EU_MEMBERS, ORIGIN_ALIASES) map an origin to overlay
  labels such as "European Union". They are geography, not rates.
* retrieval.SYNONYMS maps a few consumer words to tariff wording (lamp to luminaire). Extend it from
  the golden set.

## Known quality findings from the live run

* Whisk, cotton T-shirt, and LED desk lamp each landed the right heading in the top two, then asked
  discriminating questions rather than assigning (marginal). That is the intended safe behavior at the
  default thresholds.
* The flash model kept favoring the "all white" T-shirt line after the user said navy with a logo.
  Conditions written into a line (color, trim) are not reliably enforced by the model. This belongs in
  the golden set work under OPEN item 1 and 5 before thresholds are loosened.
