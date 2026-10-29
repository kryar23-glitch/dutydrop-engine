import json, re, sys, collections, datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

SRC = sys.argv[1]
OUT = sys.argv[2]
RELEASE = "2026 HTS Revision 21 (effective 10/09/2026)"
PULLED = datetime.date.today().isoformat()

data = json.load(open(SRC))

PROGRAMS = {
    "A": "GSP (Generalized System of Preferences)",
    "A*": "GSP, certain countries excluded for this line",
    "A+": "GSP, least developed beneficiary countries only",
    "AU": "U.S. Australia Free Trade Agreement",
    "B": "Automotive Products Trade Act",
    "BH": "U.S. Bahrain Free Trade Agreement",
    "C": "Agreement on Trade in Civil Aircraft",
    "CL": "U.S. Chile Free Trade Agreement",
    "CO": "U.S. Colombia Trade Promotion Agreement",
    "D": "African Growth and Opportunity Act (AGOA)",
    "E": "Caribbean Basin Economic Recovery Act (CBERA)",
    "IL": "U.S. Israel Free Trade Area",
    "JO": "U.S. Jordan Free Trade Area",
    "JP": "U.S. Japan Trade Agreement",
    "K": "Agreement on Trade in Pharmaceutical Products",
    "KR": "U.S. Korea Free Trade Agreement (KORUS)",
    "L": "Uruguay Round concessions on intermediate chemicals for dyes",
    "MA": "U.S. Morocco Free Trade Agreement",
    "OM": "U.S. Oman Free Trade Agreement",
    "P": "CAFTA DR (Dominican Republic Central America FTA)",
    "P+": "CAFTA DR, specified lines",
    "PA": "U.S. Panama Trade Promotion Agreement",
    "PE": "U.S. Peru Trade Promotion Agreement",
    "R": "U.S. Caribbean Basin Trade Partnership Act (CBTPA)",
    "S": "USMCA (United States Mexico Canada Agreement)",
    "S+": "USMCA, specified lines",
    "SG": "U.S. Singapore Free Trade Agreement",
}
FLAG_COLS = [("USMCA (S,S+)", {"S", "S+"}), ("KORUS (KR)", {"KR"}),
             ("CAFTA DR (P,P+)", {"P", "P+"}), ("Australia (AU)", {"AU"}),
             ("Singapore (SG)", {"SG"}), ("Chile (CL)", {"CL"}),
             ("Colombia (CO)", {"CO"}), ("Peru (PE)", {"PE"}),
             ("Japan (JP)", {"JP"}), ("GSP (A,A*,A+)", {"A", "A*", "A+"}),
             ("AGOA (D)", {"D"})]

GRP = re.compile(r'([^()]+?)\s*\(([^()]*)\)')
PCT = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*%\s*$')

def clean(s):
    return re.sub(r'\s+', ' ', s or '').strip()

def rate_type(r):
    t = clean(r).lower()
    if not t:
        return "", None
    if t == "free":
        return "Free", 0.0
    m = PCT.match(t)
    if m:
        return "Ad valorem", float(m.group(1)) / 100
    has_pct = "%" in t
    has_spec = ("¢" in t) or ("$" in t) or ("/kg" in t) or ("each" in t) or ("/doz" in t) or ("/liter" in t)
    if has_pct and has_spec:
        return "Compound", None
    if has_spec:
        return "Specific", None
    return "Other / see text", None

def parse_special(s):
    s = clean(s)
    out = {}
    for rate, codes in GRP.findall(s):
        rate = clean(rate).strip(',;')
        for c in codes.split(','):
            c = c.strip()
            if re.fullmatch(r'[A-Z]{1,2}[+*]?', c):
                out[c] = rate
    return out

def footnote_text(f):
    if not f:
        return ""
    return " | ".join(clean(x.get("value", "")) for x in f if x.get("value"))

def digits(code):
    return code.replace(".", "")

def level(code):
    n = len(digits(code))
    return {4: "Heading (4)", 6: "Subheading (6)", 8: "Tariff line (8)", 10: "Statistical (10)"}.get(n, f"{n} digit")

# Walk hierarchy
desc_stack = {}
rate_stack = {}   # indent -> (code, general, special, other)
full_rows = []
for r in data:
    ind = int(r.get("indent") or 0)
    code = clean(r.get("htsno"))
    desc = clean(r.get("description"))
    if code and len(digits(code)) == 4:
        desc_stack = {}
        rate_stack = {}
    for k in [k for k in desc_stack if k >= ind]:
        del desc_stack[k]
    for k in [k for k in rate_stack if k >= ind]:
        del rate_stack[k]
    path = " > ".join([desc_stack[k] for k in sorted(desc_stack)] + [desc])
    g, sp, o = clean(r.get("general")), clean(r.get("special")), clean(r.get("other"))
    src = "Stated" if g else ""
    ig, isp, io = g, sp, o
    if code and not g:
        for k in sorted(rate_stack, reverse=True):
            pc, pg, psp, po = rate_stack[k]
            if pg:
                ig, isp, io = pg, psp, po
                src = f"Inherited from {pc}"
                break
    units = ", ".join(clean(u) for u in (r.get("units") or []) if u)
    full_rows.append(dict(code=code, ind=ind, desc=desc, path=path, units=units,
                          g=ig, sp=isp, o=io, src=src,
                          addl=clean(r.get("additionalDuties")),
                          quota=clean(r.get("quotaQuantity")),
                          fn=footnote_text(r.get("footnotes"))))
    desc_stack[ind] = desc.rstrip(':')
    if code and g:
        rate_stack[ind] = (code, g, sp, o)

HDR_FILL = PatternFill("solid", fgColor="1F3864")
HDR_FONT = Font(bold=True, color="FFFFFF")

def style_header(ws, ncol, widths=None):
    for c in range(1, ncol + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.font = HDR_FILL, HDR_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    ws.freeze_panes = "B2"
    if widths:
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w

def add_table(ws, name, nrow, ncol):
    ref = f"A1:{get_column_letter(ncol)}{nrow}"
    t = Table(displayName=name, ref=ref)
    t.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
    ws.add_table(t)

wb = Workbook()
readme = wb.active
readme.title = "README"

# Main database
db = wb.create_sheet("HTS_Database")
cols = ["HTS Code", "HTS Digits", "Level", "Chapter", "Heading (4)", "Subheading (6)",
        "Tariff Line (8)", "Indent", "Description", "Full Description Path", "Unit of Quantity",
        "General Rate (Col 1)", "General Rate Source", "General Rate Type", "General Ad Valorem",
        "Special Rate (raw)", "Special Program Codes", "USMCA Rate"] + [f[0] for f in FLAG_COLS] + [
        "Column 2 Rate", "Column 2 Type", "Column 2 Ad Valorem", "Additional Duties",
        "Quota Quantity", "Footnotes", "Chapter 99 Line"]
db.append(cols)
code_counter = collections.Counter()
chap = collections.defaultdict(lambda: {"lines": 0, "stat": 0, "rate8": 0, "free": 0, "av": [], "first": ""})
rate8 = []
ch99 = []
n = 0
for r in full_rows:
    code = r["code"]
    if not code:
        continue
    d = digits(code)
    gt, gav = rate_type(r["g"])
    ot, oav = rate_type(r["o"])
    spm = parse_special(r["sp"])
    for c in spm:
        code_counter[c] += 1
    usmca = spm.get("S") or spm.get("S+") or ""
    flags = ["Y" if (set(spm) & s) else "" for _, s in FLAG_COLS]
    row = [code, d, level(code), d[:2], d[:4], d[:6] if len(d) >= 6 else "",
           d[:8] if len(d) >= 8 else "", r["ind"], r["desc"], r["path"], r["units"],
           r["g"], r["src"], gt, gav, r["sp"], ", ".join(sorted(spm)), usmca] + flags + [
           r["o"], ot, oav, r["addl"], r["quota"], r["fn"], "Y" if d.startswith("99") else ""]
    db.append(row)
    n += 1
    c = chap[d[:2]]
    c["lines"] += 1
    if not c["first"] and len(d) == 4:
        c["first"] = r["desc"]
    if len(d) == 10:
        c["stat"] += 1
    if r["src"] == "Stated" and not d.startswith("99"):
        c["rate8"] += 1
        if gt == "Free":
            c["free"] += 1
        if gav is not None:
            c["av"].append(gav)
        rate8.append([code, d, d[:2], r["desc"], r["path"], r["units"], r["g"], gt, gav,
                      r["sp"], usmca, r["o"], ot, oav, r["addl"]])
    if d.startswith("99"):
        ch99.append([code, d, d[:4], r["desc"], r["g"], r["sp"], r["o"], r["fn"]])

for row in db.iter_rows(min_row=2, min_col=15, max_col=15):
    for cell in row:
        cell.number_format = "0.0%"
c2col = cols.index("Column 2 Ad Valorem") + 1
for row in db.iter_rows(min_row=2, min_col=c2col, max_col=c2col):
    for cell in row:
        cell.number_format = "0.0%"
style_header(db, len(cols), [14, 12, 16, 8, 10, 12, 12, 7, 50, 70, 12, 22, 22, 14, 11, 40, 30, 14] +
             [11] * len(FLAG_COLS) + [22, 14, 11, 30, 14, 40, 10])
add_table(db, "HTS", n + 1, len(cols))

# 8 digit legal rate lines
r8 = wb.create_sheet("Rate_Lines")
h8 = ["HTS Code", "HTS Digits", "Chapter", "Description", "Full Description Path", "Unit of Quantity",
      "General Rate", "General Type", "General Ad Valorem", "Special Rate (raw)", "USMCA Rate",
      "Column 2 Rate", "Column 2 Type", "Column 2 Ad Valorem", "Additional Duties"]
r8.append(h8)
for row in rate8:
    r8.append(row)
for col in (9, 14):
    for row in r8.iter_rows(min_row=2, min_col=col, max_col=col):
        for cell in row:
            cell.number_format = "0.0%"
style_header(r8, len(h8), [14, 12, 8, 50, 70, 12, 22, 14, 11, 40, 14, 22, 14, 11, 30])
add_table(r8, "RateLines8", len(rate8) + 1, len(h8))

# Chapter 99
s99 = wb.create_sheet("Chapter99_Overlays")
h99 = ["HTS Code", "HTS Digits", "Heading", "Description", "General (Col 1) Duty", "Special Duty",
       "Column 2 Duty", "Footnotes"]
s99.append(h99)
for row in ch99:
    s99.append(row)
style_header(s99, len(h99), [14, 12, 10, 90, 40, 40, 20, 40])
add_table(s99, "Ch99", len(ch99) + 1, len(h99))

# Chapter summary
cs = wb.create_sheet("Chapter_Summary")
hcs = ["Chapter", "First Heading Description", "Coded Lines", "Statistical (10) Lines",
       "Rate Lines", "Free Rate Lines", "Share Free", "Avg Ad Valorem (pure % lines)",
       "Max Ad Valorem"]
cs.append(hcs)
for ch in sorted(chap):
    c = chap[ch]
    share = c["free"] / c["rate8"] if c["rate8"] else None
    avg = sum(c["av"]) / len(c["av"]) if c["av"] else None
    mx = max(c["av"]) if c["av"] else None
    cs.append([ch, c["first"], c["lines"], c["stat"], c["rate8"], c["free"], share, avg, mx])
for col in (7, 8, 9):
    for row in cs.iter_rows(min_row=2, min_col=col, max_col=col):
        for cell in row:
            cell.number_format = "0.0%"
style_header(cs, len(hcs), [9, 60, 12, 14, 14, 14, 11, 16, 14])
add_table(cs, "ChapterSummary", len(chap) + 1, len(hcs))

# Program codes
pc = wb.create_sheet("Special_Program_Codes")
pc.append(["Code", "Program", "Lines Citing Code"])
for c, k in sorted(code_counter.items(), key=lambda x: -x[1]):
    pc.append([c, PROGRAMS.get(c, "See HTS General Note 3(c)(i)"), k])
style_header(pc, 3, [10, 60, 18])
add_table(pc, "ProgramCodes", len(code_counter) + 1, 3)

# Lookup tool
lk = wb.create_sheet("Lookup")
lk["A1"] = "HTS Lookup and Duty Estimate"
lk["A1"].font = Font(bold=True, size=14)
lk["A3"], lk["B3"] = "Enter HTS code (dots optional)", "8471.30.0100"
lk["A4"], lk["B4"] = "Customs value (USD)", 10000
lk["B3"].fill = lk["B4"].fill = PatternFill("solid", fgColor="FFF2CC")
key = 'SUBSTITUTE($B$3,".","")'
def look(colname):
    ci = cols.index(colname) + 1
    L = get_column_letter(ci)
    return f'=IFERROR(INDEX(HTS_Database!${L}:${L},MATCH({key},HTS_Database!$B:$B,0)),"Not found")'
fields = ["Description", "Full Description Path", "Level", "Unit of Quantity", "General Rate (Col 1)",
          "General Rate Source", "General Rate Type", "General Ad Valorem", "Special Rate (raw)",
          "USMCA Rate", "Column 2 Rate", "Additional Duties", "Footnotes"]
r = 6
for f in fields:
    lk.cell(row=r, column=1, value=f)
    lk.cell(row=r, column=2, value=look(f))
    r += 1
av_row = 6 + fields.index("General Ad Valorem")
lk.cell(row=av_row, column=2).number_format = "0.0%"
lk.cell(row=r + 1, column=1, value="Estimated base duty (ad valorem lines only)")
lk.cell(row=r + 1, column=2, value=f'=IF(ISNUMBER(B{av_row}),B{av_row}*$B$4,"Compound, specific, or not found: compute manually")')
lk.cell(row=r + 1, column=2).number_format = '"$"#,##0.00'
lk.cell(row=r + 2, column=1, value="Note: base Column 1 duty only. Chapter 99 overlays (Section 301, 232, and other additional duties) apply on top. See Chapter99_Overlays.")
lk.column_dimensions["A"].width = 42
lk.column_dimensions["B"].width = 90
for row in lk.iter_rows(min_row=6, max_row=r + 1, min_col=2, max_col=2):
    for cell in row:
        cell.alignment = Alignment(wrap_text=True, vertical="top")

# README
lines = [
    ("U.S. Harmonized Tariff Schedule Database", True),
    (f"Source: U.S. International Trade Commission, hts.usitc.gov (official JSON export)", False),
    (f"Release: {RELEASE}", False),
    (f"Pulled: {PULLED}", False),
    ("", False),
    (f"Coded HTS lines: {n:,}   |   Full hierarchy rows: {len(full_rows):,}   |   rate lines: {len(rate8):,}   |   Chapter 99 lines: {len(ch99):,}", False),
    ("", False),
    ("Sheets", True),
    ("HTS_Database: every coded line (4, 6, 8, 10 digit) with descriptions, rates, program flags. Primary upload table.", False),
    ("Rate_Lines: every line (8 or 10 digit) where a duty rate is stated, excluding Chapter 99. Clean rate table, one rate per line.", False),
    ("Chapter99_Overlays: temporary and additional duties (Section 301, 232, and other actions) that stack on base rates.", False),
    ("Chapter_Summary: line counts, free share, and average ad valorem rate by chapter.", False),
    ("Special_Program_Codes: every preference code cited in the Special column, with usage counts.", False),
    ("HTS_Full_Hierarchy: all rows in USITC order, including uncoded description headers.", False),
    ("Lookup: enter a code and customs value for description, rates, and a base duty estimate.", False),
    ("", False),
    ("Key fields", True),
    ("HTS Digits: code with dots removed, stored as text. Use as the primary key.", False),
    ("General Rate Source: 'Stated' if the rate appears on that line; 'Inherited from X' when a 10 digit line takes its 8 digit parent's rate.", False),
    ("General Rate Type: Free, Ad valorem, Specific, Compound, or Other. General Ad Valorem holds the decimal rate for pure percentage lines only.", False),
    ("USMCA Rate: rate text attached to program code S or S+. Qualification requires meeting USMCA rules of origin.", False),
    ("Column 2: rates for countries without normal trade relations status.", False),
    ("", False),
    ("Cautions", True),
    ("Base rates exclude Chapter 99 additional duties, AD/CVD orders, MPF, and HMF. Landed duty can exceed the Column 1 rate.", False),
    ("Program availability depends on current law; a code listed here does not confirm a program is in force. Check General Note 3(c).", False),
    ("Program names in Special_Program_Codes are a reference key; verify against General Note 3(c)(i).", False),
    ("Classification is the importer's legal responsibility. Confirm with a licensed customs broker or a CBP binding ruling.", False),
    ("Rates change with each HTS revision. Refresh from hts.usitc.gov before relying on this file.", False),
]
for i, (t, b) in enumerate(lines, 1):
    readme.cell(row=i, column=1, value=t).font = Font(bold=b, size=14 if i == 1 else 11)
readme.column_dimensions["A"].width = 140

# Full hierarchy
fh = wb.create_sheet("HTS_Full_Hierarchy")
hfh = ["Row Order", "HTS Code", "Indent", "Description", "Full Description Path", "Unit of Quantity",
       "General Rate", "General Rate Source", "Special Rate", "Column 2 Rate", "Additional Duties", "Footnotes"]
fh.append(hfh)
for i, r in enumerate(full_rows, 1):
    fh.append([i, r["code"], r["ind"], ("    " * r["ind"]) + r["desc"], r["path"], r["units"],
               r["g"], r["src"], r["sp"], r["o"], r["addl"], r["fn"]])
style_header(fh, len(hfh), [9, 14, 7, 70, 70, 12, 22, 22, 40, 22, 30, 40])
add_table(fh, "HTSHierarchy", len(full_rows) + 1, len(hfh))

wb.move_sheet("Lookup", offset=-(len(wb.sheetnames) - 2))
wb.save(OUT)

# Also CSV of main table for direct database upload
import csv
with open(OUT.replace(".xlsx", "_database.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    for row in db.iter_rows(values_only=True):
        w.writerow(row)
print("coded", n, "full", len(full_rows), "rate8", len(rate8), "ch99", len(ch99))
print("codes", dict(code_counter.most_common()))
