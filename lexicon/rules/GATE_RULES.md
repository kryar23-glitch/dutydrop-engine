# Duty stacking rules for the receipt gate

Objective: price every common consumer import with a firm total, so the curated list reaches 200 of 200 products, each with its assumptions printed.

Source: HTSUS 2026 Revision 21, Chapter 99 U.S. notes (notes 16, 20, 52 and subchapter I notes), as loaded in the overlay catalog. Presidential proclamations and executive orders behind these headings are summarized in STACKING_RULES.md. Where the two differ, the HTS note text governs, because CBP enforces the published heading.

## Why 103 products dropped

I ran the engine's own calculator on all 200 curated products for China, Vietnam and Mexico (600 receipts). 175 produced a firm total. 425 were marked provisional. The causes, in order of size:

1. Exemption headings that cannot apply to consumer goods were attached as live alternatives. The worst offenders are civil aircraft exemptions (9903.05.88, 9903.96.01, 9903.96.02, 9903.05.05) and pharmaceutical end-use exemptions. They hit every product.
2. Duties written for other countries were attached because the catalog row has a blank country. Examples are the 100 percent EU and UK retaliation lines in 9903.08 and 9903.27 (handbags, coffee makers, printed bed linen, leather footwear), the 9903.41 footwear lines and the quartz surface lines in 9903.45.
3. USTR Section 301 product exclusions (9903.88.10 through 9903.88.69) were treated as open alternatives. Each covers only the exact product described in note 20, by narrative, not the whole subheading.
4. More than one additional duty on a line set the "stacking open" flag, even where note 52 says the duties stack.
5. Section 232 metal duty on derivative articles needs the value of the steel, aluminum or copper content.
6. Compound rates (cents per unit plus percent) need a quantity.

Causes 1 to 4 are rule gaps, not missing facts. Fixing them resolves 552 of 600 receipts and 184 of 200 products on all three origins.

## Rules

R1. Exemptions limited by end use or industry do not apply by default. Civil aircraft, pharmaceutical use, seeds for sowing and similar headings stay off the receipt. Show them only if the seller states that use.

R2. A Chapter 99 heading applies only to the origins its own text names. When the catalog country is blank, read the heading text or its group header. If it names other countries (for example the EU and UK list above 9903.08, or Japan, Brazil, Jordan, the United Kingdom), it does not apply to China, Vietnam or Mexico. Fix this in the overlay build so the country column is never blank for a country-limited heading.

R3. Section 301 USTR exclusions are not applied by default. Print the full Section 301 duty and add one line: "A USTR product exclusion may apply if your product matches the exclusion text exactly." The total stays firm.

R4. The country-wide duties in headings 9903.05.20 to 9903.05.84 (U.S. note 52) stack. Note 52(a) says goods subject to them "shall also be subject to any additional duty provided for in this subchapter or in subchapter IV." So base duty plus Section 301 plus the note 52 duty is the correct total for China. Do not mark stacking open for this combination. The current rates in the catalog are China 12.5 percent (9903.05.31), Vietnam 12.5 percent (9903.05.84) and Mexico 10 percent (9903.05.55). These are the Section 301 Forced Labor duties in force since July 24, 2026 (91 FR 47318, CSMS 69326983). They replaced the Section 122 surcharge, which itself replaced the IEEPA duties the Supreme Court struck on February 20, 2026. No IEEPA or Section 122 duty applies to entries today. See STACKING_RULES.md.

R5. Note 52 duties do not apply to goods under the Section 232 programs listed in note 52(f): steel, aluminum and copper articles and derivatives (9903.82 and related headings), passenger vehicles and parts, wood products in 9903.76 (including kitchen cabinets and vanities), medium and heavy trucks and parts, semiconductors (9903.79.01) and patented pharmaceuticals (9903.04.60 to 9903.04.66). For those goods, print the Section 232 duty instead of the note 52 duty, never both.

R6. Mexico. The 9903.05.55 duty does not apply to goods entered free under USMCA (note 52(h)). The default receipt assumes the goods do not qualify and shows the duty. A second line shows "If USMCA qualifying" with that duty removed. This is a scenario, not an open stack, so the total stays firm.

R7. Section 232 metals. Note 16(a) allows exactly one 9903.82 heading per article. Pick it by the note 16(c) list that names the code (parsed into `dutydrop/manifests/note16_lists_2026_Rev21.json`): lists (i) to (v) take 9903.82.02 at 50 percent; lists (vi) to (viii) and (xi) take 9903.82.09 at 25 percent; lists (ix) and (x) take a 15 percent floor, 9903.82.10 for the difference when the base rate is under 15 percent, else 9903.82.11 at zero. Since April 6, 2026 the duty runs on the full customs value. A code on no list owes no metals duty, whatever the overlay join attached. Outside chapters 72, 73, 74 and 76, assume the metal is at least 15 percent of the weight, print that assumption and add the scenario "If metal is under 15% of weight". Section 301 China stacks on top; the note 52 duty does not (R5).

R8. Compound rates. Receipts ask for quantity in the unit the HTS line uses (each, dozen, gross). SEO page examples state the quantity they assume, for example "100 pens at $1.00 each", and price the specific part from it.

R9. Quartz surface safeguard (9903.45.30 and .31, note 41). It covers only quartz surface products: silica and resin slabs, countertops, tiles and similar. Code 7020.00.60 also holds ordinary glass articles, so drop these headings unless the seller says the product is a quartz surface, and print one note.

R10. A heading whose note subdivision enumerates codes applies only to the codes it lists. Example: 9903.91.08 (note 31(i)) covers 4015.12.10 gloves only, not every China product the join touched.

R11. Transitional headings for goods "exported to the United States before" a past date (9903.88.09, May 2019) never apply to a new entry.

R1 also covers overlay lines that need an importer certification of end use: 9903.94.07 (note 33(p), parts certified for U.S. auto production or repair).

## Result on the curated 200

`dutydrop/gate.py` implements R1 to R11. On the 200 curated products for China, Vietnam and Mexico at $100 and $1.00 a unit, 600 of 600 receipts are firm and 200 of 200 products pass, each with its assumptions printed. Per receipt lines in `gate_results.json`. Tests in `tests/test_gate.py`.

Open question for a broker: lithium ion batteries (8507.60) carry the Section 232 auto parts duty 9903.94.05 because 8507.60 is on the note 33(g) list. Whether CBP applies it to batteries not meant for vehicles is not settled in the note text; the gate keeps it, the conservative choice.

The per-receipt analysis is in gate_analysis.json and engine_run.json in this folder. STACKING_RULES.md holds the legal history, the full precedence order and the open questions, including the China exclusions that expire November 9, 2026 unless extended.
