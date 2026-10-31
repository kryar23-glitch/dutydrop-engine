"""Download one openly licensed Wikimedia Commons photo per golden item (1024 px wide)."""
import json, os, time, urllib.parse, urllib.request, csv
UA = "DutyDropGoldenSet/1.0 (kryar23@gmail.com)"
here = os.path.dirname(os.path.abspath(__file__))
items = json.load(open(os.path.join(here, "golden.json")))
OK_LIC = ("CC BY", "CC0", "Public domain", "CC BY-SA", "PD")
out = []
for it in items:
    dest = os.path.join(here, "photos", it["id"] + ".jpg")
    url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrnamespace=6"
           "&gsrlimit=25&prop=imageinfo&iiprop=url|extmetadata|mime&iiurlwidth=1024&gsrsearch="
           + urllib.parse.quote("filetype:bitmap " + it["q"]))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    pages = json.load(urllib.request.urlopen(req, timeout=30)).get("query", {}).get("pages", {})
    picked = None
    for p in sorted(pages.values(), key=lambda p: p.get("index", 99)):
        ii = p["imageinfo"][0]
        lic = ii["extmetadata"].get("LicenseShortName", {}).get("value", "")
        title_ok = (not it.get("kw")) or it["kw"].lower() in p["title"].lower()
        bad = any(b in p["title"].lower() for b in ("player", "match", "concert", "festival", "masters", "cup ", "league", "nga", "painting", "rendering", "boy", "girl", "child", "man ", "woman", "people", "visitors", "playing", "train", "texture"))
        if title_ok and not bad and ii.get("mime") in ("image/jpeg", "image/png") and lic.startswith(OK_LIC) and ii.get("thumburl"):
            picked = (p["title"], ii["thumburl"], lic, ii.get("descriptionurl"))
            break
    if not picked:
        out.append([it["id"], "", "", "", "NOT FOUND"]); print(it["id"], "NOT FOUND"); continue
    if not os.path.exists(dest):
        r = urllib.request.Request(picked[1], headers={"User-Agent": UA})
        open(dest, "wb").write(urllib.request.urlopen(r, timeout=60).read())
        time.sleep(0.5)
    out.append([it["id"], picked[0], picked[2], picked[3], "ok"])
    print(it["id"], picked[0], picked[2])
with open(os.path.join(here, "photo_sources.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["id", "commons_title", "license", "source_page", "status"]); w.writerows(out)
