import requests, os, re
from bs4 import BeautifulSoup
os.makedirs("dnb-data", exist_ok=True)
U = "https://mcc.admissions.nic.in/Applicant/Report/ViewInstituteProfileDynamic.aspx?agencyid=140&boardid=140012621"
P = "ctl00$ContentPlaceHolder1$"
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0"

def form(html):
    soup = BeautifulSoup(html, "lxml"); d = {}
    for i in soup.select("input[type=hidden]"):
        if i.get("name"): d[i["name"]] = i.get("value", "")
    for sel in soup.select("select"):
        o = sel.find("option", selected=True) or sel.find("option")
        d[sel["name"]] = o["value"] if o else ""
    return soup, d

def opts(soup, name):
    sel = soup.find("select", id="ctl00_ContentPlaceHolder1_" + name)
    return [(o.get("value"), o.text.strip()) for o in sel.find_all("option")] if sel else []

r = s.get(U, timeout=90); soup, d = form(r.text)
log = open("dnb-data/probe_log.txt", "w", encoding="utf-8")
def L(*a): print(*a, flush=True); print(*a, file=log)

for t in ("DNB", "DNP"):
    d2 = dict(d); d2[P + "ddlInstType"] = t; d2["__EVENTTARGET"] = P + "ddlInstType"
    r = s.post(U, data=d2, timeout=90); sp, dd = form(r.text)
    ins = opts(sp, "ddlInstitutes"); L(t, "institutes:", len(ins), ins[:5])
    open(f"dnb-data/{t}_institutes.txt", "w", encoding="utf-8").write("\n".join(f"{v}\t{n}" for v, n in ins))
    if t == "DNB" and len(ins) > 1:
        iid = ins[1][0]
        d3 = dict(dd); d3[P + "ddlInstType"] = t; d3[P + "ddlInstitutes"] = iid; d3["__EVENTTARGET"] = P + "ddlInstitutes"
        r = s.post(U, data=d3, timeout=90); sp2, d4 = form(r.text)
        pr = opts(sp2, "ddlprogram"); L("programs for", ins[1], len(pr), pr[:10])
        d4[P + "ddlInstType"] = t; d4[P + "ddlInstitutes"] = iid
        if len(pr) > 1: d4[P + "ddlprogram"] = pr[1][0]
        d4["__EVENTTARGET"] = ""; d4[P + "btnsubmit"] = "Submit"
        r = s.post(U, data=d4, timeout=90)
        L("submit:", r.status_code, r.headers.get("content-type"), len(r.content))
        ext = "pdf" if r.content[:4] == b"%PDF" else "html"
        open(f"dnb-data/sample_submit.{ext}", "wb").write(r.content)
