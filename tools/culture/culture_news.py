"""DocPulsee: weekly work-culture news signals (27 Oct 2026).
For every college with MD/MS seats, read Google News RSS for resident/PG news, keep stories from the last 24 months whose
headline names the college and talks about residents/PG doctors, and turn each into one rating signal:
  toxicity 5  ragging, harassment, abuse, suicide of a resident/PG
  toxicity 4  strike / protest by residents, stipend not paid or delayed
  hours    5  duty hours, 24/36/48-hour shifts, overwork
  hands_on 2  NMC show-cause, deficiency, seats cut or withdrawn
Writes culture_news.json at the site root (public: headlines + links only). Supabase pulls it weekly
(sync_culture_news) and stores each item as a 'news' rating (seed=true, note=headline, source=link).
Run: python3 tools/culture/culture_news.py [limit]"""
import json, re, sys, time, hashlib, urllib.request, urllib.parse, html, datetime, email.utils
import xml.etree.ElementTree as ET

ROOT = __file__.rsplit('/tools/', 1)[0]
D = json.load(open(ROOT + '/neetpg_data.min.json'))
def col(k):
    V = D['d'][k]; return [V[v - 1] if v else None for v in D['c'][k]]
N, I, G, SP, ST = col('Display_Name'), col('I'), col('Deg'), col('Spec_Norm'), col('State')
inst = {}
for n, i, g, sp, st in zip(N, I, G, SP, ST):
    if i is None or not n: continue
    x = inst.setdefault(i, {'n': n, 'st': st, 'b': set()})
    if g in ('MD', 'MS'): x['b'].add((g, sp))
inst = {i: x for i, x in inst.items() if x['b']}


STOP = {'post', 'graduate', 'postgraduate', 'employees', 'state', 'insurance', 'corporation', 'sri', 'shri', 'shree', 'memorial', 'government', 'govt', 'medical', 'college', 'institute', 'of', 'and', 'hospital', 'sciences', 'science', 'the', '&', 'research', 'health', 'centre', 'center', 'pvt', 'ltd', 'university'}
def short(n):
    a = re.split(r',', n)[0]
    a = re.sub(r'\(.*?\)', '', a); a = re.sub(r'\s+', ' ', a).strip()
    return a
def keys(n):
    """Distinctive words that must appear in a headline to count as this college (+ the city when the name is generic)."""
    parts = [p.strip() for p in n.split(',')]; a = short(n); ac = re.findall(r'\(([A-Z]{3,8})\)', n)
    w = [x for x in re.findall(r"[A-Za-z]+", a) if x.lower() not in STOP and len(x) > 2]
    city = None
    for p in parts[1:]:
        t = [x for x in re.findall(r"[A-Za-z]+", p) if x.lower() not in STOP and len(x) > 2]
        if t: city = t[-1] if len(t) <= 2 else t[0]; break
    if len(w) < 2 and city and city.lower() not in [v.lower() for v in w]: w.append(city)
    q = a + (' ' + city if city and city.lower() not in a.lower() and len(w) <= 2 else '')
    return q, w, ac

SMALL = {'of', 'and', 'the', '&', 'for', 'in'}
def acr(n):
    w = [x for x in re.findall(r"[A-Za-z]+", short(n)) if x.lower() not in SMALL]
    full = ''.join(x[0] for x in w).upper()
    pre = []
    for k, x in enumerate(w):
        if x.lower() in ('medical', 'institute', 'college', 'university'): break
        pre.append(x[0].upper())
    return full, ''.join(pre)
_ac = {}
for i, x in inst.items():
    f, p = acr(x['n']); x['acr'] = f; x['pre'] = p; _ac[f] = _ac.get(f, 0) + 1
def norm(t):
    t = re.sub(r"[.'’]", ' ', t.lower()); t = re.sub(r'\s+', ' ', t)
    for _ in range(3): t = re.sub(r'\b([a-z]) (?=[a-z]\b)', r'\1', t)
    return t.strip()
def stem(n):
    w = re.findall(r"[A-Za-z.]+", short(n)); out = []
    for x in w:
        if x.lower() in ('medical', 'institute', 'college', 'university', 'hospital', 'government', 'govt'): break
        out.append(x)
    return norm(' '.join(out))
_st = {}
for _x in inst.values(): _x['stem'] = stem(_x['n']); _st[_x['stem']] = _st.get(_x['stem'], 0) + 1
STEMS = [k for k in _st if k]
SHORTS = sorted({norm(short(x['n'])) for x in inst.values()}, key=len)

CTX = re.compile(r"\b(residents?|resident doctors?|pg (students?|doctors?|residents?|medicos?)|post ?graduates?|junior doctors?|jrs?|medicos|pgs)\b", re.I)
RULES = [
    ('toxicity', 5, re.compile(r"ragg|harass|abus|humiliat|suicide|toxic|bully|caste discrimin|casteis|punish|forced to pay|murga|exploit|threaten", re.I)),
    ('toxicity', 4, re.compile(r"stipend.{0,40}(not paid|unpaid|delay|pending|withheld|months|protest|strike|cut)|(unpaid|delayed|pending|no|without) stipend|(protest|strike|agitat)\w*.{0,40}stipend", re.I)),
    ('hours', 5, re.compile(r"duty hours?|work(ing)? hours?|\b(24|36|48|72)[- ]hours?|overwork|long hours|sleep[- ]deprived|no rest", re.I)),
    ('hands_on', 2, re.compile(r"show[- ]cause|deficien|seats? (cut|reduced|withdrawn|derecogn)|derecogni|faculty shortage|nmc (penal|fine|notice)", re.I)),
]
DEPT = [('Anaesthesiology', r'anaesthe|anesthe'), ('General Medicine', r'medicine dep|department of medicine'), ('General Surgery', r'surgery dep|department of surgery'),
        ('Obstetrics And Gynaecology', r'gyn|obstet|obg'), ('Paediatrics', r'paediatric|pediatric'), ('Orthopaedics', r'ortho'), ('Radio Diagnosis', r'radiolog'),
        ('Psychiatry', r'psychiatr'), ('Dermatology', r'dermatolog'), ('ENT', r'\bent\b'), ('Ophthalmology', r'ophthalm|eye dep')]

def rss(q):
    u = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q': q, 'hl': 'en-IN', 'gl': 'IN', 'ceid': 'IN:en'})
    for t in range(3):
        try:
            r = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0 (DocPulsee culture bot)'}), timeout=20)
            return ET.fromstring(r.read())
        except Exception as e:
            time.sleep(4 * (t + 1))
    return None

def bkey(i, deg, sp): return re.sub(r'[^a-zA-Z0-9_.-]', '_', f'{i}__{deg}__{sp}')[:180]

def main(limit=None, debug=False):
    dbg = []
    cut = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=730)
    out, seen = [], set(); ids = sorted(inst)[:limit] if limit else sorted(inst)
    for k, i in enumerate(ids):
        x = inst[i]; a, w, ac = keys(x['n'])
        if not w and not ac: continue
        q = '"' + short(x['n']) + '"' + (' ' + a.replace(short(x['n']), '').strip() if a != short(x['n']) else '') + ' (resident OR residents OR PG OR stipend OR ragging OR strike OR NMC)'
        root = rss(q); time.sleep(1.2)
        if debug: dbg.append({'n': x['n'], 'q': q, 'ok': root is not None, 'titles': [html.unescape(t.findtext('title') or '')[:140] for t in (root.iter('item') if root is not None else [])][:8]})
        if root is None: continue
        got = 0
        for it in root.iter('item'):
            t = html.unescape(it.findtext('title') or ''); link = it.findtext('link') or ''; src = it.findtext('source') or ''
            try: pd = email.utils.parsedate_to_datetime(it.findtext('pubDate') or '')
            except Exception: continue
            if not link.startswith('https://') or pd < cut or link in seen: continue
            head = re.sub(r'\s+-\s+[^-]+$', '', t)  # drop " - Outlet"
            hl = head.lower()
            # the headline must name this college: all distinctive words, or its acronym
            sn = norm(short(x['n'])); nh = norm(head)
            longer = any(sn in o and o != sn and o in nh for o in SHORTS)
            named = False
            if sn in nh and not longer: named = True
            elif len(w) >= 2 and all(v.lower() in hl for v in w[:3]) and not longer: named = True
            elif len(x['stem']) >= 6 and _st.get(x['stem']) == 1 and re.search(r'\b' + re.escape(x['stem']) + r'\b', nh) and not any(x['stem'] in o and o != x['stem'] and o in nh for o in STEMS): named = True
            elif len(x['acr']) >= 4 and re.search(r'\b' + x['acr'] + r'\b', head) and (_ac.get(x['acr']) == 1 or (x['st'] and x['st'].split()[0].lower() in hl)): named = True
            elif len(x['pre']) >= 2 and re.search(r'\b' + x['pre'] + r'\b\s+(medical|hospital)', head): named = True
            elif any(re.search(r'\b' + c + r'\b', head) for c in ac): named = True
            elif len(w) == 1 and re.search(r'\b' + re.escape(w[0].lower()) + r'\b', hl) and re.search(r'medical college|\bgmc\b|institute of medical|medical sciences', hl): named = True
            elif x['st'] and len(w) >= 1 and re.search(r'\bgmc\b', hl) and any(re.search(r'\b' + re.escape(v.lower()) + r'\b', hl) for v in w[-1:]): named = True
            if not named: continue
            for dim, val, rx in RULES:
                if not rx.search(head): continue
                if dim != 'hands_on' and not CTX.search(head): continue
                br = None
                for sp, rr in DEPT:
                    if re.search(rr, hl):
                        for deg, s2 in x['b']:
                            if s2 == sp: br = bkey(i, deg, sp)
                out.append({'i': str(i), 'b': br, 'dim': dim, 'v': val, 'h': head[:220], 'src': src[:60], 'd': pd.strftime('%b %Y'), 'u': link[:600],
                            'id': 'news_' + hashlib.sha1(link.encode()).hexdigest()[:16]})
                seen.add(link); got += 1; break
            if got >= 3: break
        if k % 50 == 0: print(k, len(ids), len(out), flush=True)
    json.dump({'v': datetime.date.today().isoformat(), 'n': len(out), 'items': out}, open(ROOT + '/culture_news.json', 'w'), ensure_ascii=False, indent=0)
    if debug: json.dump(dbg, open(ROOT + '/tools/culture/debug.json', 'w'), ensure_ascii=False, indent=1)
    print('done', len(out), 'items from', len(ids), 'colleges')

if __name__ == '__main__':
    a = sys.argv[1:]
    if a and a[0] == 'debug':
        names = ['Maulana Azad', 'King George', 'Grant Government', 'Seth G S', 'Lokmanya Tilak', 'Madras Medical', 'Gandhi Medical College', 'Sawai Man Singh', 'Lady Hardinge', 'R G Kar', 'Bangalore Medical', 'Osmania', 'Topiwala', 'Government Medical College, Kota', 'Indira Gandhi Medical College Shimla']
        sel = [i for i, x in inst.items() if any(nm.lower() in x['n'].lower() for nm in names)]
        inst = {i: inst[i] for i in sel}; print(len(inst), [inst[i]['n'][:40] for i in inst]); main(None, True)
    else:
        main(int(a[0]) if a else None)
