import requests, os
os.makedirs("dnb-data", exist_ok=True)
u = "https://mcc.admissions.nic.in/Applicant/Report/ViewInstituteProfileDynamic.aspx?agencyid=140&boardid=140012621"
s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0"
r = s.get(u, timeout=90)
print(r.status_code, len(r.text), r.headers.get("content-type"))
open("dnb-data/page.html", "w", encoding="utf-8").write(r.text)
