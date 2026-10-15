#!/usr/bin/env python3
"""Download MCC bond PDFs for every institute, dedupe by md5, OCR the unique ones,
and write a best-effort summary (years / amount / raw text) to bond-data/."""
import csv, hashlib, os, re, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
import requests

URL = "https://mcc.admissions.nic.in/Counseling/Handler/ViewInstituteProfileDynamic.ashx?boardId=140012521&InstituteId={}&Type=BM"
OUT = "bond-data"
PDFS, TEXT = f"{OUT}/unique", f"{OUT}/text"
os.makedirs(PDFS, exist_ok=True); os.makedirs(TEXT, exist_ok=True)
LIMIT = int(os.environ.get("LIMIT", "0"))

inst = list(csv.DictReader(open("tools/bond/institutes.csv", encoding="utf-8")))
if LIMIT: inst = inst[:LIMIT]

def fetch(r):
    for a in range(4):
        try:
            resp = requests.get(URL.format(r["id"]), timeout=60, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200 and resp.content[:4] == b"%PDF" and len(resp.content) > 2000:
                return r, resp.content, "ok"
            if resp.status_code == 200: return r, None, f"not_pdf_or_tiny({len(resp.content)}b)"
            st = f"http{resp.status_code}"
        except Exception as e:
            st = f"err:{type(e).__name__}"
        time.sleep(2 * (a + 1))
    return r, None, st

# smoke test so a blocked network fails fast
r0, c0, s0 = fetch(inst[0])
print("smoke test:", inst[0]["id"], s0, flush=True)
if c0 is None: sys.exit("MCC not reachable from this runner: " + s0)

index = []
with ThreadPoolExecutor(8) as ex:
    for n, (r, content, st) in enumerate(ex.map(fetch, inst), 1):
        md5 = ""
        if content:
            md5 = hashlib.md5(content).hexdigest()
            p = f"{PDFS}/{md5}.pdf"
            if not os.path.exists(p): open(p, "wb").write(content)
        index.append({"id": r["id"], "name": r["name"], "md5": md5, "status": st})
        if n % 100 == 0: print("downloaded", n, flush=True)

with open(f"{OUT}/index.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, ["id", "name", "md5", "status"]); w.writeheader(); w.writerows(index)
uniq = sorted({i["md5"] for i in index if i["md5"]})
print(f"{sum(1 for i in index if i['md5'])} PDFs downloaded, {len(uniq)} unique", flush=True)

def ocr(md5):
    t = f"{TEXT}/{md5}.txt"
    if os.path.exists(t): return
    tmp = f"/tmp/ocr_{md5}"; os.makedirs(tmp, exist_ok=True)
    subprocess.run(["pdftoppm", "-r", "200", "-l", "10", "-png", f"{PDFS}/{md5}.pdf", f"{tmp}/p"], check=False)
    parts = []
    for img in sorted(os.listdir(tmp)):
        res = subprocess.run(["tesseract", f"{tmp}/{img}", "-", "-l", "hin+eng", "--psm", "6"],
                             capture_output=True, text=True)
        parts.append(res.stdout)
    open(t, "w", encoding="utf-8").write("\n\f\n".join(parts))
    shutil.rmtree(tmp, ignore_errors=True)

with ThreadPoolExecutor(os.cpu_count() or 2) as ex:
    list(ex.map(ocr, uniq))
print("OCR done", flush=True)

NUM = {"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,"ten":10}
def summarize(txt):
    yrs = re.findall(r"(\d+(?:\.\d+)?)\s*(?:\(\w+\)\s*)?(?:years?|yrs?|वर्ष|साल)", txt, re.I)
    yrs += [str(NUM[w.lower()]) for w in re.findall(r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s+years?", txt, re.I)]
    amt = re.findall(r"(?:Rs\.?|₹|INR|रु\.?|रुपये?)\s*([\d,]+(?:\.\d+)?)\s*(lakhs?|लाख|crores?|करोड़)?", txt, re.I)
    amt += [(a, u) for a, u in re.findall(r"([\d,]+(?:\.\d+)?)\s*(lakhs?|लाख|crores?|करोड़)", txt, re.I)]
    amt = [f"{a} {u}".strip() for a, u in amt if a.strip(",.")]
    return sorted(set(yrs), key=float) if yrs else [], list(dict.fromkeys(amt))

summ = {}
for m in uniq:
    txt = open(f"{TEXT}/{m}.txt", encoding="utf-8").read()
    y, a = summarize(txt)
    summ[m] = ("; ".join(y), "; ".join(a), len(txt))
with open(f"{OUT}/bond_summary.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id", "name", "md5", "years_found", "amounts_found", "text_chars"])
    for i in index:
        if i["md5"]: w.writerow([i["id"], i["name"], i["md5"], *summ[i["md5"]]])
print("summary written")
