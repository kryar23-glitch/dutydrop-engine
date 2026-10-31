# DutyDrop product lexicon: entry schema

One JSON object per line (JSONL) in /home/claude/lexicon/parts/<group>.jsonl

Fields
- id: kebab-case unique slug, e.g. "ceramic-mug"
- term: canonical consumer name, lowercase singular, e.g. "ceramic mug"
- category: one of the group categories you were given
- aliases: list of other ways sellers and shoppers say it. Include synonyms, plurals, regional terms (US/UK), marketplace listing phrasing ("coffee cup with handle"), generic names for brand terms ("airpods" -> earbuds, "crocs" -> clogs, "yeti" -> insulated tumbler, "kleenex" -> facial tissue), common compound forms ("phone case", "cell phone case", "iphone case", "mobile cover"). 5 to 25 per entry. Lowercase. No misspellings here (generated separately).
- hts10: the default 10 digit statistical line, dotted "6912.00.44.00". It MUST exist in data/hts.csv with Level "Statistical (10)". Pick the line a customs broker would pick for the most common version of this product as sold on Amazon or Shopify.
- default_assumption: short plain sentence printed when the default relies on an unstated fact, e.g. "Assumes stoneware or earthenware, not porcelain." Empty string if none.
- variants: list of {"when": "<attribute word or phrase>", "hts10": "<code>", "note": "<short>"} for stated attributes that change the line: material (cotton, polyester, leather, plastic, stainless steel, porcelain, glass, wood, bamboo, silicone), gender/age (men's, women's, boys', girls', baby), power (battery, corded, electric), set vs single, etc. Each hts10 must also exist as a Statistical (10) line. Include the main material and gender splits that a seller is likely to state. 0 to 12 per entry.
- attributes_words: list of words that, if present in user text, indicate this product even without the term, optional.
- notes: optional short broker note (e.g. "Kits classified by essential character, GRI 3(b)").

Rules
- Every code you write must be copied from data/hts.csv. Use grep/python to look it up. Never guess a code.
- Prefer specific named lines over "Other" when the named line fits the common product.
- Consumer goods only. Skip agricultural bulk commodities, live animals, chemicals in bulk, aircraft parts, etc.
- No duplicate ids within your file.
- Aim for breadth: the long tail of what small importers and marketplace sellers actually bring in.
