import json, re, sys, csv, collections, datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

JSON, TXT, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
RELEASE = "2026 HTS Revision 21 (effective 10/09/2026)"
PULLED = datetime.date.today().isoformat()
NOTES_START, NOTES_END = 12725, 39972   # Subchapter III U.S. notes in ch99.txt (1 based)

data = json.load(open(JSON))
txt = open(TXT, encoding="utf-8", errors="replace").read().split("\n")

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()

def digits(c):
    return c.replace(".", "")

# ---------------- Base lines ----------------
base = {}          # digits -> dict
order = []
desc_stack, rate_stack = {}, {}
for r in data:
    code = clean(r["htsno"]); ind = int(r["indent"] or 0)
    if code and len(digits(code)) == 4:
        desc_stack, rate_stack = {}, {}
    for k in [k for k in desc_stack if k >= ind]: del desc_stack[k]
    for k in [k for k in rate_stack if k >= ind]: del rate_stack[k]
    g = clean(r["general"])
    ig = g
    if code and not g:
        for k in sorted(rate_stack, reverse=True):
            if rate_stack[k]:
                ig = rate_stack[k]; break
    desc = clean(r["description"])
    if code and not code.startswith("99"):
        d = digits(code)
        base[d] = dict(code=code, desc=desc, path=" > ".join([desc_stack[k] for k in sorted(desc_stack)] + [desc]),
                       general=ig, fn=" ".join(clean(x.get("value")) for x in (r["footnotes"] or [])))
        order.append(d)
    desc_stack[ind] = desc.rstrip(":")
    if code and g:
        rate_stack[ind] = g

PCT = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*%\s*$")
def av(rate):
    t = clean(rate).lower()
    if t == "free": return 0.0
    m = PCT.match(t)
    return float(m.group(1)) / 100 if m else None

# leaf lines: 10 digit, or 8 digit with no 10 digit children
tens = {d[:8] for d in base if len(d) == 10}
leaves = [d for d in order if len(d) == 10 or (len(d) == 8 and d not in tens)]
leaf_set = set(leaves)

# ---------------- Parse Subchapter III notes ----------------
nl = txt[NOTES_START - 1:NOTES_END]
JUNK = re.compile(r"Harmonized Tariff Schedule of the United States|Annotated for Statistical|^\s*U\.S\. Notes|^\s*XXII\s*$|^\s*99-III-\d+\s*$")
nl = ["" if JUNK.search(l) else l for l in nl]
NOTE_RE = re.compile(r"^\s{0,4}(\d{1,2})\.(\s|$)")
notes = {}       # n -> (start, end) indices into nl
expect, cur, cur_start = 1, None, None
for i, l in enumerate(nl):
    m = NOTE_RE.match(l)
    if m and expect <= int(m.group(1)) <= expect + 10:
        n = int(m.group(1))
        if cur is not None: notes[cur] = (cur_start, i)
        cur, cur_start, expect = n, i, n + 1
if cur is not None: notes[cur] = (cur_start, len(nl))

LABEL_RE = re.compile(r"^(\s*(?:\d{1,2}\.\s+)?)((?:\([A-Za-z0-9]{1,5}\)\s*)+)")
def line_labels(l):
    m = LABEL_RE.match(l)
    if not m: return []
    col = len(m.group(1))
    out = []
    for lm in re.finditer(r"\(([A-Za-z0-9]{1,5})\)", m.group(2)):
        out.append((lm.group(1), col + lm.start()))
    return out

ROMANS = ["i","ii","iii","iv","v","vi","vii","viii","ix","x","xi","xii","xiii","xiv","xv","xvi","xvii","xviii","xix","xx",
          "xxi","xxii","xxiii","xxiv","xxv","xxvi","xxvii","xxviii","xxix","xxx","xxxi","xxxii","xxxiii","xxxiv","xxxv"]
def letter_seq():
    out = []
    for rep in range(1, 4):
        for ch in "abcdefghijklmnopqrstuvwxyz":
            out.append(ch * rep)
    return out
LETTERS = letter_seq()
UPPER = [x.upper() for x in LETTERS]
def seq_for(label, depth):
    if label.isdigit(): return [str(i) for i in range(1, 200)]
    if label.isupper(): return UPPER
    if depth % 2 == 1 and label in ROMANS: return ROMANS
    if label in LETTERS: return LETTERS
    if label in ROMANS: return ROMANS
    return None

line_lab_cache = {}
def labs_at(i):
    if i not in line_lab_cache:
        line_lab_cache[i] = [x for x, _ in line_labels(nl[i])]
    return line_lab_cache[i]

def next_occ(label, s, e):
    for i in range(s, e):
        if label in labs_at(i): return i
    return None

def find_block(label, depth, s, e):
    seq = seq_for(label, depth)
    if not seq or label not in seq: return None
    k = seq.index(label)
    pos = s
    for lab in seq[:k]:
        t = next_occ(label, pos, e)
        if t is None: return None
        q = next_occ(lab, pos, t)
        if q is not None: pos = q + 1
    i0 = next_occ(label, pos, e)
    if i0 is None: return None
    succ = seq[k + 1] if k + 1 < len(seq) else None
    i1 = next_occ(succ, i0 + 1, e) if succ else None
    return (i0, i1 if i1 else e)

block_cache = {}
def resolve(note, path):
    key = (note, tuple(path))
    if key in block_cache: return block_cache[key]
    if note not in notes: block_cache[key] = None; return None
    s, e = notes[note]
    for depth, lab in enumerate(path):
        b = find_block(lab, depth, s, e)
        if not b: block_cache[key] = None; return None
        s, e = b
    block_cache[key] = (s, e)
    return (s, e)

CODE_RE = re.compile(r"(?<![\d.])(\d{4}\.\d{2}(?:\.\d{2}(?:\d{2})?)?)(?![\d])")
HEAD_LIST = re.compile(r"\bheadings?\s+((?:\d{4}(?:\s*,\s*|\s*,?\s*(?:and|or|through|to)\s+))*\d{4})\b")
def codes_in(lines):
    t = " ".join(lines)
    t = re.sub(r"(\d)-\s+(\d)", r"\1\2", t)
    out = set()
    for c in CODE_RE.findall(t):
        if not c.startswith("99"): out.add(digits(c))
    for m in HEAD_LIST.finditer(t):
        seg = m.group(1)
        parts = re.split(r"(\s*,\s*|\s*,?\s*(?:and|or|through|to)\s+)", seg)
        nums = [p for p in parts if re.fullmatch(r"\d{4}", p.strip())]
        seps = [p.strip(" ,") for p in parts if not re.fullmatch(r"\d{4}", p.strip())]
        for k, n in enumerate(nums):
            if not n.startswith("99"): out.add(n)
            if k < len(seps) and seps[k] in ("through", "to") and k + 1 < len(nums):
                a, b = int(n), int(nums[k + 1])
                if 0 < b - a < 60:
                    for x in range(a + 1, b): out.add(f"{x:04d}")
    return out

AUTH = [("Section 232", re.compile(r"section 232", re.I)),
        ("Section 301", re.compile(r"section 301", re.I)),
        ("Section 122", re.compile(r"section 122", re.I)),
        ("Section 201 safeguard", re.compile(r"section 201|safeguard", re.I)),
        ("IEEPA", re.compile(r"International Emergency Economic Powers", re.I))]
note_expired = {}
for n, (s, e) in notes.items():
    head = " ".join(nl[s:min(e, s + 25)])
    m = re.search(r"(expired at the close of [A-Z][a-z]+\.? \d{1,2}, \d{4})", head)
    if m and (e - s) < 40: note_expired[n] = m.group(1)
note_auth = {}
for n, (s, e) in notes.items():
    t = " ".join(nl[s:e])
    hits = [name for name, rx in AUTH if rx.search(t)]
    note_auth[n] = hits

# ---------------- Chapter 99 catalog ----------------
COUNTRY_RE = re.compile(r"products? of (?:the )?((?:[A-Z][\w’'\.\-]*)(?:\s+(?:and\s+)?[A-Z][\w’'\.\-]*)*)")
NOTE_CITE = re.compile(r"(?:U\.S\.\s+)?notes?\s+(\d{1,2})\s*((?:\([A-Za-z0-9]{1,5}\))*)")
SUBDIV_CITE = re.compile(r"subdivisions?\s+((?:\([A-Za-z0-9]{1,5}\))+(?:\s*(?:,|and|or|through)\s*(?:\([A-Za-z0-9]{1,5}\))+)*)\s+(?:of|to|in)\s+(?:U\.S\.\s+)?note\s+(\d{1,2})")

def group_program(code, note_refs, desc):
    h = code[:7]
    if h in ("9903.01", "9903.02"): return "IEEPA"
    if h == "9903.03" and code <= "9903.03.11": return "Section 122"
    if (h == "9903.05" and code >= "9903.05.20") or h == "9903.06" or 52 in note_refs: return "Section 301 forced labor"
    if code.startswith("9902"): return "Temporary duty reduction (MTB)"
    if code.startswith("9904"): return "Section 22 / quota"
    if code.startswith("9901"): return "Ethyl alcohol additional duty"
    if not code.startswith("9903"): return "Trade agreement / quota provision"
    auths = []
    for n in note_refs:
        for a in note_auth.get(n, []):
            if a not in auths: auths.append(a)
    d = desc.lower()
    if re.search(r"forced.labor", d) or "Section 301" in auths and h == "9903.05": return "Section 301 forced labor"
    if h in ("9903.88", "9903.91", "9903.92"): return "Section 301 China"
    S232 = {16: "Section 232 metals (steel, aluminum, copper)", 33: "Section 232 autos and parts", 37: "Section 232 timber and lumber",
            38: "Section 232 medium and heavy trucks", 39: "Section 232 semiconductors", 40: "Section 232 pharmaceuticals"}
    for n in note_refs:
        if n in S232: return S232[n]
    if h in ("9903.82", "9903.85", "9903.94", "9903.76", "9903.74", "9903.79"):
        return "Section 232"
    if auths: return auths[0]
    if re.search(r"quota|quantitative", d): return "Quota provision"
    return f"Other: U.S. note {note_refs[0]}" if note_refs else "Other (see heading text)"

TODAY = datetime.date.today()
def through_date(desc):
    m = re.search(r"through ([A-Z][a-z]+) (\d{1,2}), (\d{4})", desc)
    if not m: return None
    try: return datetime.datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y").date()
    except ValueError: return None
def status(code, desc, program, note_nums=()):
    for n in note_nums:
        if n in note_expired: return "Expired", f"U.S. note {n}: {note_expired[n]}"
    td = through_date(desc)
    if td and td < TODAY: return "Expired", f"Heading text: effective through {td.isoformat()}"
    m = re.search(r"\[Compiler.{0,3}s note:([^\]]*)\]", desc)
    note = clean(m.group(1)) if m else ""
    if re.search(r"terminat", note, re.I): return "Terminated", note
    if re.search(r"suspend", note, re.I): return "Suspended", note
    if program == "IEEPA": return "Ended 2/24/2026", "IEEPA tariffs invalidated (Learning Resources v. Trump); CBP CSMS 67834313 ended collection for entries on or after 2/24/2026"
    if program == "Section 122": return "Expired 7/24/2026", "Section 122 surcharge (Proclamation 11012) ran 2/24/2026 to 7/24/2026; refunds in litigation"
    if re.search(r"expir", note, re.I): return "Expired", note
    if td: return f"Active through {td.isoformat()}", note
    return "Active (per HTS Rev 21)", note

def effect(general):
    g = clean(general)
    gl = g.lower()
    m = re.search(r"(?:\+|plus)\s*(\d+(?:\.\d+)?)\s*%", g)
    if "applicable subheading" in gl and m: return "Additional ad valorem", float(m.group(1)) / 100
    if "applicable subheading" in gl or gl in ("no change",): return "Exemption / no additional duty", 0.0
    if not g: return "See heading text", None
    if PCT.match(g): return "Rate in lieu of base (combined or floor)", float(PCT.match(g).group(1)) / 100
    if gl == "free": return "Rate in lieu of base", 0.0
    return "Specific or compound", None

catalog, coverage = [], []
for r in data:
    code = clean(r["htsno"])
    if not code.startswith("99"): continue
    desc = clean(r["description"])
    refs = []
    for m in SUBDIV_CITE.finditer(desc):
        n = int(m.group(2))
        for grp in re.split(r"\s*(?:,|and|or|through)\s*", m.group(1)):
            labs = re.findall(r"\(([A-Za-z0-9]{1,5})\)", grp)
            if labs: refs.append((n, labs))
    for m in NOTE_CITE.finditer(desc):
        n = int(m.group(1)); labs = re.findall(r"\(([A-Za-z0-9]{1,5})\)", m.group(2))
        if (n, labs) not in refs and not (not labs and any(x[0] == n for x in refs)):
            refs.append((n, labs))
    note_nums = [n for n, _ in refs]
    prog = group_program(code, note_nums, desc)
    st, stnote = status(code, desc, prog, note_nums)
    eff, rate = effect(r["general"])
    cm = COUNTRY_RE.search(desc)
    country = clean(cm.group(1)) if cm else ("Any country" if re.search(r"any country", desc, re.I) else "")
    if not cm and re.search(r"European Union", desc): country = "European Union"
    if country.startswith("Côte") or country.startswith("Cote"): country = "Côte d’Ivoire"
    country = re.sub(r"\s+(?:that|which|as|classified|entered|provided)\b.*$", "", country)
    # coverage: codes cited directly in heading text
    direct = set(digits(c) for c in CODE_RE.findall(desc) if not c.startswith("99"))
    note_codes, resolved = set(), []
    if code.startswith("9903"):
        for n, labs in refs:
            if not labs and re.search(r"products? of", desc):
                continue
            b = resolve(n, labs)
            if b:
                blk = nl[b[0]:b[1]]
                head = " ".join(blk[:8])
                if country and re.search(r"all products of", head) and not re.search(r"all products of [^.]{0,90}?(classified|enumerated|described|listed|subheading)", head):
                    resolved.append(f"{n}{''.join('('+x+')' for x in labs)} (country wide)")
                    continue
                resolved.append(f"{n}{''.join('('+x+')' for x in labs)}")
                note_codes |= codes_in(blk)
    if not (direct or note_codes) and (rate is None or rate == 0) and code.startswith("9903"):
        scope = "Described goods (exemption or special case)"
    else:
        scope = None
    scope = scope or ("Product list" if (direct or note_codes) else ("All products of country" if country and country != "Any country" else ("All products" if country == "Any country" else "See heading text")))
    catalog.append(dict(code=code, d=digits(code), group=code[:7], prog=prog, country=country, eff=eff, rate=rate,
                        general=clean(r["general"]), special=clean(r["special"]), status=st, stnote=stnote,
                        refs="; ".join(f"note {n}{''.join('('+x+')' for x in l)}" for n, l in refs),
                        resolved="; ".join(resolved), scope=scope, ncodes=len(direct | note_codes), desc=desc))
    for c in sorted(direct):
        coverage.append([c, code, prog, country, eff, rate, st, "Cited in heading text", ""])
    for c in sorted(note_codes - direct):
        coverage.append([c, code, prog, country, eff, rate, st, "Listed in U.S. note", "; ".join(resolved)])

# base line footnote references to Chapter 99
cat_by = {c["code"]: c for c in catalog}
REF99 = re.compile(r"99\d\d\.\d\d\.\d\d")
for d, b in base.items():
    for ref in set(REF99.findall(b["fn"])):
        c = cat_by.get(ref)
        if c:
            coverage.append([d, ref, c["prog"], c["country"], c["eff"], c["rate"], c["status"], "Base line footnote", ""])

# dedupe coverage
seen, cov = set(), []
for row in coverage:
    k = (row[0], row[1])
    if k in seen: continue
    seen.add(k); cov.append(row)

# expanded: active additional duty overlays to leaf lines
by_prefix = collections.defaultdict(list)
for d in leaves:
    for L in (4, 6, 8, 10):
        if len(d) >= L: by_prefix[d[:L]].append(d)
expanded = []
for row in cov:
    cited, hd, prog, ctry, eff, rate, st = row[:7]
    if not st.startswith("Active"): continue
    for leaf in by_prefix.get(cited, []):
        b = base[leaf]
        expanded.append([leaf, b["code"], b["desc"], b["general"], av(b["general"]), hd, prog, ctry, eff, rate, row[7]])
# dedupe expanded by (leaf, heading)
seen, exp = set(), []
for e in expanded:
    k = (e[0], e[5])
    if k in seen: continue
    seen.add(k); exp.append(e)

country_wide = [c for c in catalog if c["scope"] in ("All products of country", "All products")]

# ---------------- Workbook ----------------
HF, HFont = PatternFill("solid", fgColor="1F3864"), Font(bold=True, color="FFFFFF")
def sheet(wb, name, hdr, rows, widths, tname, pct_cols=()):
    ws = wb.create_sheet(name)
    ws.append(hdr)
    for rw in rows: ws.append(rw)
    for i in range(1, len(hdr) + 1):
        c = ws.cell(row=1, column=i); c.fill, c.font = HF, HFont
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = widths[i - 1] if i - 1 < len(widths) else 14
    for pc in pct_cols:
        for rw in ws.iter_rows(min_row=2, min_col=pc, max_col=pc):
            for c in rw: c.number_format = "0.0%"
    ws.freeze_panes = "B2"
    t = Table(displayName=tname, ref=f"A1:{get_column_letter(len(hdr))}{len(rows) + 1}")
    t.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
    ws.add_table(t)
    return ws

wb = Workbook()
rd = wb.active; rd.title = "README"

cat_hdr = ["Ch99 Heading", "Ch99 Digits", "Heading Group", "Program", "Country of Origin", "Effect", "Duty Rate",
           "General Duty Text", "Special Duty Text", "Status", "Status Basis", "Note References", "Notes Resolved",
           "Scope", "Codes Mapped", "Description"]
cat_rows = [[c["code"], c["d"], c["group"], c["prog"], c["country"], c["eff"], c["rate"], c["general"], c["special"],
             c["status"], c["stnote"], c["refs"], c["resolved"], c["scope"], c["ncodes"], c["desc"]] for c in catalog]

# Receipt sheet placeholder (built after data sheets exist)
rc = wb.create_sheet("Receipt")

sheet(wb, "Overlay_Catalog", cat_hdr, cat_rows, [14, 12, 10, 26, 22, 30, 10, 40, 30, 22, 50, 30, 30, 22, 10, 100], "OverlayCatalog", (7,))
cov_hdr = ["Cited Base Code", "Ch99 Heading", "Program", "Country of Origin", "Effect", "Duty Rate", "Status", "Mapping Method", "Note Subdivision"]
sheet(wb, "Overlay_Coverage", cov_hdr, cov, [14, 14, 26, 22, 30, 10, 22, 22, 24], "OverlayCoverage", (6,))
exp_hdr = ["HTS Digits", "HTS Code", "Description", "Base General Rate", "Base Ad Valorem", "Ch99 Heading", "Program",
           "Country of Origin", "Effect", "Overlay Rate", "Mapping Method"]
sheet(wb, "Active_Overlays_by_HTS", exp_hdr, exp, [12, 14, 50, 18, 10, 14, 26, 22, 30, 10, 22], "ActiveByHTS", (5, 10))
cw_hdr = ["Ch99 Heading", "Program", "Country of Origin", "Effect", "Duty Rate", "Status", "Scope", "Description"]
cw_rows = [[c["code"], c["prog"], c["country"], c["eff"], c["rate"], c["status"], c["scope"], c["desc"]] for c in country_wide]
sheet(wb, "Country_Wide_Overlays", cw_hdr, cw_rows, [14, 26, 24, 30, 10, 22, 22, 100], "CountryWide", (5,))
br_rows = [[d, base[d]["code"], base[d]["desc"], base[d]["general"], av(base[d]["general"])] for d in leaves]
sheet(wb, "Base_Rates", ["HTS Digits", "HTS Code", "Description", "General Rate", "General Ad Valorem"], br_rows,
      [12, 14, 70, 20, 12], "BaseRates", (5,))
na_rows = [[n, ", ".join(note_auth[n]) or "", notes[n][1] - notes[n][0]] for n in sorted(notes)]
sheet(wb, "Note_Authority", ["Subchapter III Note", "Authorities Named in Note Text", "Text Lines"], na_rows, [18, 50, 12], "NoteAuthority")
ps = collections.Counter((c["prog"], c["status"]) for c in catalog)
sheet(wb, "Program_Status", ["Program", "Status", "Ch99 Lines"], [[p, s, n] for (p, s), n in sorted(ps.items())], [34, 30, 12], "ProgramStatus")

# Receipt calculator (Excel 365 dynamic arrays)
countries = sorted({c["country"] for c in catalog if c["country"] and c["status"].startswith("Active")})
lists = wb.create_sheet("Lists")
for i, c in enumerate(countries, 1): lists.cell(row=i, column=1, value=c)
lists.sheet_state = "hidden"
rc["A1"] = "Tariff Receipt Calculator"; rc["A1"].font = Font(bold=True, size=14)
rc["A3"], rc["B3"] = "HTS code (10 digit, dots optional)", "8504.40.9580"
rc["A4"], rc["B4"] = "Country of origin", "China"
rc["A5"], rc["B5"] = "Customs value (USD)", 10000
for c in ("B3", "B4", "B5"): rc[c].fill = PatternFill("solid", fgColor="FFF2CC")
dv = DataValidation(type="list", formula1=f"=Lists!$A$1:$A${len(countries)}", allow_blank=True)
rc.add_data_validation(dv); dv.add("B4")
rc["A7"], rc["B7"] = "Description", '=IFERROR(XLOOKUP(SUBSTITUTE($B$3,".",""),BaseRates[HTS Digits],BaseRates[Description]),"Not found")'
rc["A8"], rc["B8"] = "Base general rate", '=IFERROR(XLOOKUP(SUBSTITUTE($B$3,".",""),BaseRates[HTS Digits],BaseRates[General Rate]),"")'
rc["A9"], rc["B9"] = "Base ad valorem", '=IFERROR(XLOOKUP(SUBSTITUTE($B$3,".",""),BaseRates[HTS Digits],BaseRates[General Ad Valorem]),"")'
rc["A10"], rc["B10"] = "Base duty", '=IF(ISNUMBER(B9),B9*$B$5,"Specific or compound rate: compute manually")'
rc["A12"] = "Product specific overlays matching this code and country (active only)"
rc["A12"].font = Font(bold=True)
rc["A13"] = ('=IFERROR(FILTER(CHOOSE({1,2,3,4,5},ActiveByHTS[Ch99 Heading],ActiveByHTS[Program],ActiveByHTS[Country of Origin],'
             'ActiveByHTS[Effect],ActiveByHTS[Overlay Rate]),(ActiveByHTS[HTS Digits]=SUBSTITUTE($B$3,".",""))*'
             '((ActiveByHTS[Country of Origin]=$B$4)+(ActiveByHTS[Country of Origin]="Any country")+(ActiveByHTS[Country of Origin]=""))),"None found")')
rc["G12"] = "Country wide overlays for this origin (active only)"; rc["G12"].font = Font(bold=True)
rc["G13"] = ('=IFERROR(FILTER(CHOOSE({1,2,3,4},CountryWide[Ch99 Heading],CountryWide[Program],CountryWide[Effect],CountryWide[Duty Rate]),'
             '(CountryWide[Country of Origin]=$B$4)*(LEFT(CountryWide[Status],6)="Active")),"None found")')
rc["A40"] = ("How to read: Base duty plus each additional ad valorem overlay that applies gives the indicative total. Exemption lines "
             "(rate 0) override the overlay they except. Rate in lieu lines replace the base rate. Stacking rules in the U.S. notes "
             "govern final treatment; confirm with a licensed customs broker.")
rc["A40"].alignment = Alignment(wrap_text=True)
rc.merge_cells("A40:K42")
for col, w in zip("ABCDEFGHIJK", [40, 22, 26, 22, 30, 4, 16, 26, 30, 10, 10]):
    rc.column_dimensions[col].width = w
for cell in ("B9",): rc[cell].number_format = "0.0%"
rc["B10"].number_format = '"$"#,##0.00'

active = sum(1 for c in catalog if c["status"].startswith("Active"))
lines = [
    ("U.S. Tariff Overlay Database (Chapter 99 mapped to HTS)", True),
    ("Source: USITC HTS JSON export and Chapter 99 PDF (hts.usitc.gov); program status from CBP CSMS 67834313 and public reporting", False),
    (f"Release: {RELEASE}    Pulled: {PULLED}", False),
    (f"Chapter 99 lines: {len(catalog):,}   Active: {active:,}   Coverage links: {len(cov):,}   Active links expanded to HTS lines: {len(exp):,}   Country wide overlays: {len(country_wide):,}", False),
    ("", False),
    ("Sheets", True),
    ("Receipt: enter HTS code, origin, and value. Returns base duty and every active overlay that matches. Needs Excel 365 or Google Sheets.", False),
    ("Overlay_Catalog: every Chapter 99 line with program, country, effect, rate, status, note references, and scope.", False),
    ("Overlay_Coverage: each base code cited for each Chapter 99 heading, with mapping method. Codes at 4, 6, 8, or 10 digits.", False),
    ("Active_Overlays_by_HTS: active product specific overlays expanded to every 10 digit line (or 8 digit leaf) they reach. Primary join table.", False),
    ("Country_Wide_Overlays: overlays that reach all products of an origin rather than a code list (for example Section 301 forced labor).", False),
    ("Base_Rates: base Column 1 general rate for every leaf line.", False),
    ("Note_Authority and Program_Status: audit tables for how programs and statuses were assigned.", False),
    ("", False),
    ("Method", True),
    ("Mapping methods: codes cited in the heading text; codes listed in the U.S. note subdivision the heading cites; and Chapter 99 references in base line footnotes.", False),
    ("Note subdivisions are parsed from the PDF text by label and indentation. Lists that the PDF lays out irregularly may map incompletely. Codes Mapped in the catalog shows the count per heading.", False),
    ("A cited 4, 6, or 8 digit code expands to every leaf line beneath it.", False),
    ("", False),
    ("Status rules", True),
    ("IEEPA lines (9903.01, 9903.02): ended for entries on or after 2/24/2026. HTS Rev 21 still prints many of them; this file overrides that.", False),
    ("Section 122 lines (9903.03): 10% worldwide surcharge, expired 7/24/2026.", False),
    ("Lines with a compiler's note saying terminated, suspended, or expired carry that status.", False),
    ("All other lines are marked Active as published in Rev 21. Exclusions with end dates inside heading text are not yet parsed.", False),
    ("", False),
    ("Cautions", True),
    ("Overlay stacking is governed by the U.S. notes. Some programs exempt goods covered by others (for example Section 232 goods from certain Section 301 forced labor duties). The Receipt lists candidates; it does not resolve stacking.", False),
    ("Exemption headings describe goods in words (steel derivatives, civil aircraft, pharmaceuticals). Those are flagged but not mapped to codes.", False),
    ("AD/CVD orders, MPF, and HMF are excluded.", False),
    ("Refund status for IEEPA and Section 122 duties is in litigation. Verify before advising any client.", False),
    ("Classification and duty liability rest with the importer of record. Confirm with a licensed customs broker.", False),
]
for i, (t, b) in enumerate(lines, 1):
    rd.cell(row=i, column=1, value=t).font = Font(bold=b, size=14 if i == 1 else 11)
rd.column_dimensions["A"].width = 150
wb.move_sheet("Receipt", offset=-(wb.sheetnames.index("Receipt") - 1))
wb.save(OUT)

stem = OUT.replace(".xlsx", "")
for name, hdr, rows in [("catalog", cat_hdr, cat_rows), ("coverage", cov_hdr, cov), ("active_by_hts", exp_hdr, exp)]:
    with open(f"{stem}_{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(hdr); w.writerows(rows)

print("notes parsed", len(notes), "catalog", len(catalog), "coverage", len(cov), "expanded", len(exp), "countrywide", len(country_wide))
print(collections.Counter((c["prog"], c["status"]) for c in catalog).most_common())
top = sorted(catalog, key=lambda c: -c["ncodes"])[:15]
for c in top: print(c["code"], c["prog"], c["country"], c["ncodes"], c["resolved"])
unres = [c for c in catalog if c["code"].startswith("9903") and c["refs"] and not c["resolved"]]
print("unresolved refs", len(unres), [ (c["code"], c["refs"]) for c in unres[:12]])
