#!/usr/bin/env python3
"""Download MCC college profile PDFs (fees, stipend, etc.) and parse label/value tables."""
import csv, io, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
import requests, pdfplumber

URL = "https://mcc.admissions.nic.in/Counseling/Handler/ViewInstituteProfileDetailsDynamic.ashx?boardId=140012521&InstituteId={}"
OUT = "profile-data"; os.makedirs(OUT, exist_ok=True)
LIMIT = int(os.environ.get("LIMIT", "0"))
inst = list(csv.DictReader(open("tools/profile/institutes.csv", encoding="utf-8")))
if LIMIT: inst = inst[:LIMIT]

def fetch(r):
    st = "?"
    for a in range(4):
        try:
            x = requests.get(URL.format(r["id"]), timeout=60, headers={"User-Agent": "Mozilla/5.0"})
            if x.status_code == 200 and x.content[:4] == b"%PDF": return r, x.content, "ok"
            st = f"http{x.status_code}_{len(x.content)}b"
        except Exception as e: st = f"err:{type(e).__name__}"
        time.sleep(2 * (a + 1))
    return r, None, st

r0, c0, s0 = fetch(inst[0]); print("smoke test:", s0, flush=True)
if c0 is None: sys.exit("MCC not reachable from this runner: " + s0)

# label keyword -> column. First match wins; fee/NRI rows checked by year number.
def col(label):
    l = re.sub(r"\s+", " ", label).strip().lower()
    yr = re.search(r"(\d)(?:st|nd|rd|th)\s*year", l.replace("4thyear", "4th year"))
    y = yr.group(1) if yr else ""
    if l.startswith("stipend"):
        for k, n in (("iiird", "3"), ("iind", "2"), ("i st", "1")):
            if k in l: return f"stipend_year{n}"
    if "nri" in l and y: return f"nri_fee_usd_year{y}"
    if "hostel fee" in l and y: return f"fee_year{y}"
    if "including hostel fees" in l: return "amount_at_admission"
    m = [("name of the college", "college_name"), ("mailing address", "address"), ("state:", "state_code"),
         ("pin code", "pin"), ("affiliating", "university"), ("hostel facility for male", "hostel_male"),
         ("hostel facility for female", "hostel_female"), ("deducted on", "fee_deducted_on_reallocation"),
         ("reimbursed", "fee_reimbursed_on_resign"), ("forfeited", "amount_forfeited_on_resign"),
         ("annual fees", "annual_fee"), ("website", "website"), ("other info", "other_info"),
         ("miscellaneous", "misc_charges"), ("name of dean", "principal"), ("mobile no", "principal_mobile")]
    for k, c in m:
        if k in l: return c
    return None

rows, extra = [], set()
def parse(content):
    d = {}
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for pg in pdf.pages:
            for t in pg.extract_tables():
                for row in t:
                    if len(row) >= 2 and row[0] and row[1]:
                        c = col(row[0])
                        if c and c not in d: d[c] = row[1].replace("\n", " ").strip()
    return d

with ThreadPoolExecutor(8) as ex:
    for n, (r, content, st) in enumerate(ex.map(fetch, inst), 1):
        d = {"id": r["id"], "name": r["name"], "status": st}
        if content:
            try: d.update(parse(content))
            except Exception as e: d["status"] = f"parse_err:{type(e).__name__}"
        rows.append(d)
        if n % 100 == 0: print("done", n, flush=True)

cols = ["id", "name", "status", "college_name", "state_code", "university", "annual_fee", "amount_at_admission",
        *[f"fee_year{i}" for i in range(1, 6)], "stipend_year1", "stipend_year2", "stipend_year3",
        "hostel_male", "hostel_female", "fee_deducted_on_reallocation", "fee_reimbursed_on_resign",
        "amount_forfeited_on_resign", *[f"nri_fee_usd_year{i}" for i in range(1, 6)],
        "misc_charges", "other_info", "website", "address", "pin", "principal", "principal_mobile"]
with open(f"{OUT}/profile_data.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
print("ok:", sum(r["status"] == "ok" for r in rows), "of", len(rows))
