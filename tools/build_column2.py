"""Extract the Column 2 origins from HTS General Note 3(b) into the data directory.

Usage:
  curl -L -o gn.pdf "https://hts.usitc.gov/reststop/file?release=currentRelease&filename=General%20Notes"
  pdftotext -layout gn.pdf gn.txt
  python3 tools/build_column2.py gn.txt <DATA_DIR> <REVISION, e.g. 2026_Rev21>
"""
import csv
import os
import re
import sys


def main(gn_txt, data_dir, rev):
    lines = open(gn_txt, encoding="utf-8", errors="replace").read().split("\n")
    start = next(i for i, l in enumerate(lines) if "Rate of Duty Column 2" in l)
    end = next(i for i in range(start + 1, len(lines)) if re.match(r"^\s*\(c\)\s", lines[i]))
    block = lines[start:end]
    # the country table follows the sentence ending in "thereunder:"
    t = next(i for i, l in enumerate(block) if "thereunder" in l)
    names = []
    for l in block[t + 1:]:
        for part in re.split(r"\s{3,}", l.strip()):
            part = part.strip()
            if part and not part.endswith("/") and re.match(r"^[A-Z][A-Za-z .'-]+$", part):
                names.append(part)
    if not names:
        sys.exit("No Column 2 origins found; check the General Notes layout.")
    out = os.path.join(data_dir, f"US_General_Note3b_Column2_{rev}.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Origin", "Source"])
        for n in names:
            w.writerow([n, f"HTS General Note 3(b), {rev}"])
    print(out, names)


if __name__ == "__main__":
    main(*sys.argv[1:4])
