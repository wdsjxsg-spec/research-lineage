#!/usr/bin/env python3
"""Publication status + venue tiers (CCF / 中科院分区 / JCR / 新锐分区 / 预警名单) for a collection.

Input : <out>/papers.json (collect.py) ; tier tables in <skill>/data (see data/SOURCE.txt)
Output: <out>/venues.json      per-paper labels (cached raw metadata in venues_raw.json)
        <out>/venues.csv       one row per paper, for spreadsheets / manual review
        <out>/venues_stats.md  publication statistics + items needing review
        <out>/graph.json       nodes get "pub", graph gets "venue_stats" (if graph.json exists)

Usage: python3 -I venues.py --out DIR [--overrides overrides.json] [--refresh]
overrides.json: {"<paper key>": "<venue name to match>"} or {"<key>": {"venue": "...", "type": "conference"}}
"""
import argparse, datetime as dt, collections, csv, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
UA = "research-lineage-skill/1.0 (venue tiers)"
# tier tables from ShowJCR (downloaded by scripts/fetch_data.py; a new yearly release usually only renames these files)
TIER_FILES = {"ccf": "CCF2026-UTF8.csv", "cas": "FQBJCR2025-UTF8.csv", "jcr": "JCR2025-UTF8.csv",
              "xr": "XR2026-UTF8.csv", "xrc": "XR2026Conferences-UTF8.csv", "warn": "GJQKYJMD2025.csv"}
STOP = {"proceedings", "of", "the", "on", "in", "and", "annual", "international", "acm", "ieee", "usenix", "sigsac",
        "th", "st", "nd", "rd", "for", "a", "an", "ifip", "cvf", "association", "iee"}
PREPRINT = re.compile(r"ssrn|preprints\.org|preprint|research square|techrxiv|biorxiv|medrxiv|zenodo|researchgate|osf\b|philpapers", re.I)
THESIS = re.compile(r"diva|dspace|digital commons|scholar works|skemman|theses|dissertation|thesis|repository|laurea|institutional", re.I)
ARXIV = re.compile(r"arxiv", re.I)
# containers that say nothing about the actual venue (proceedings series / book platforms)
GENERIC = re.compile(r"lecture notes|springer ebooks|ebooks|communications in computer and information science|"
                     r"advances in (intelligent|computational)|book series|smart innovation|mechanisms and machine science|"
                     r"internet of things$|springer proceedings|springerbriefs|^proceedings$", re.I)


def compact(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def same_venue(a, b):
    """Name variants of one venue: token overlap, acronym (DTRAP), ISO abbreviation (Comput. Electr. Eng.),
    or one compact form contained in the other (GLOBECOM 2025 - IEEE Global Communications Conference)."""
    na, nb = norm(a), norm(b)
    if jaccard(na, nb) >= 0.3:
        return True
    ca, cb = compact(re.sub(r"\d", "", a)), compact(re.sub(r"\d", "", b))
    if min(len(ca), len(cb)) >= 4 and (ca in cb or cb in ca):
        return True
    for x, y in ((a, b), (b, a)):
        words = re.findall(r"[A-Za-z]+", y)
        acr = "".join(w[0] for w in words).lower()
        acr2 = "".join(w[0] for w in words if w.lower() not in STOP).lower()
        xs = compact(x)
        if len(xs) >= 3 and xs in (acr, acr2):
            return True
        xt = [t.strip(".").lower() for t in x.split() if t.strip(".")]
        yt = [w.lower() for w in words if w.lower() not in STOP]
        if 2 <= len(xt) <= len(yt) and all(yt[i].startswith(xt[i]) for i in range(len(xt))):
            return True
    return False


def http_json(url, data=None, headers=None, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            ra = str(e.headers.get("Retry-After") or "")
            if e.code == 429 and ra.isdigit() and int(ra) > 300:
                raise  # daily quota exhausted: fail fast instead of sleeping for hours
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(int(ra) if ra.isdigit() else min(60, 5 * 2 ** i)); continue
            raise
        except Exception:
            if i == tries - 1: raise
            time.sleep(5)


def norm(s):
    s = re.sub(r"\([^)]*\)", " ", (s or "").lower()).replace("&", " and ")
    return " ".join(t for t in re.sub(r"[^a-z0-9 ]", " ", s).split() if not t.isdigit() and t not in STOP)


def jaccard(a, b):
    A, B = set(a.split()), set(b.split())
    return len(A & B) / len(A | B) if A and B else 0.0


def issns(*vals):
    out = set()
    for v in vals:
        for x in re.findall(r"\d{4}-?\d{3}[\dxX]", v or ""):
            x = x.upper().replace("-", ""); out.add(x[:4] + "-" + x[4:])
    return out


# ---------------------------------------------------------------- tier tables
def load_tiers():
    def rows(f):
        p = os.path.join(DATA, f)
        return list(csv.DictReader(open(p, encoding="utf-8-sig"))) if os.path.exists(p) else []
    T = {"ccf": [], "cas": {}, "cas_name": {}, "jcr": {}, "jcr_name": {}, "xr": {}, "xr_name": {}, "xrc": [], "warn": {}}
    for r in rows(TIER_FILES["ccf"]):
        kind = "conference" if "会议" in (r.get("CCF推荐类别（国际学术刊物/会议）") or "") else "journal"
        T["ccf"].append({"abbr": (r.get("刊物名称") or "").strip(), "name": (r.get("Journal") or "").strip(), "kind": kind,
                         "rank": (r.get("CCF推荐类型") or "")[:1], "field": r.get("领域"), "n": norm(r.get("Journal"))})
    for r in rows(TIER_FILES["cas"]):
        m = re.match(r"\s*(\d)", r.get("大类分区") or "")
        if not m: continue
        rec = {"zone": int(m.group(1)), "top": (r.get("Top") or "").strip() == "是", "cat": r.get("大类"), "name": r.get("Journal")}
        for x in issns(r.get("ISSN/EISSN")): T["cas"][x] = rec
        T["cas_name"][norm(r.get("Journal"))] = rec
    for r in rows(TIER_FILES["jcr"]):
        qs = [r.get(k) for k in r if k and k.startswith("IF Quartile") and r.get(k)]
        qs = sorted(q for q in qs if re.match(r"Q[1-4]$", q or ""))
        if not qs: continue
        rec = {"q": qs[0], "if": r.get("IF(2025)"), "name": r.get("Journal")}
        for x in issns(r.get("ISSN"), r.get("EISSN")): T["jcr"][x] = rec
        T["jcr_name"][norm(r.get("Journal"))] = rec
    for r in rows(TIER_FILES["xr"]):
        m = re.match(r"\s*(\d)", r.get("大类新锐分区") or "")
        if not m: continue
        rec = {"zone": int(m.group(1)), "top": (r.get("Top") or "").strip() in ("是", "Top"), "name": r.get("Journal")}
        for x in issns(r.get("ISSN"), r.get("EISSN")): T["xr"][x] = rec
        T["xr_name"][norm(r.get("Journal"))] = rec
    for r in rows(TIER_FILES["xrc"]):
        m = re.match(r"\s*(\d)", r.get("分区") or "")
        if not m: continue
        T["xrc"].append({"abbr": r.get("会议缩写"), "n": norm(r.get("Journal")), "zone": int(m.group(1)), "top": r.get("Top") == "Top"})
    for r in rows(TIER_FILES["warn"]):
        T["warn"][norm(r.get("Journal"))] = next((v for k, v in r.items() if k and k.startswith("预警原因")), "预警")
    ap = os.path.join(DATA, "venue_aliases.json")
    T["alias"] = {norm(k): v for k, v in (json.load(open(ap, encoding="utf-8")) if os.path.exists(ap) else {}).items() if not k.startswith("_")}
    return T


def match_ccf(T, name, kind, alts):
    """Return (entry, method). Exact normalized name > token similarity > abbreviation in S2 alternate names."""
    n = norm(name)
    if not n:
        return None, None
    is_ws = "workshop" in n
    pool = [e for e in T["ccf"] if kind in (None, "unknown") or e["kind"] == kind]
    for e in pool:
        if e["n"] == n:
            return e, "name"
    if kind == "conference" and len(compact(name)) >= 4:
        # venue literally named by its CCF abbreviation ("Globecom"); conferences only — MDPI's journal "AI" ≠ CCF-A "AI"
        e = next((e for e in pool if e["abbr"] and compact(e["abbr"]) == compact(name)), None)
        if e:
            return e, "abbr-name"
    if n in T["alias"]:
        e = next((e for e in pool if e["abbr"] == T["alias"][n]), None)
        if e:
            return e, "alias"
    best, score = None, 0.0
    for e in pool:
        if is_ws and "workshop" not in e["n"]:
            continue  # a workshop never inherits its main conference's tier
        s = jaccard(n, e["n"])
        if s > score: best, score = e, s
    if best and score >= 0.8:
        return best, f"similar({score:.2f})"
    if not is_ws:
        # abbreviations collide a lot ("AI", "ICICS", "CSR"): require the full names to agree as well
        al = {a.strip() for a in alts or [] if a}
        for e in pool:
            if e["abbr"] and e["abbr"] in al and jaccard(n, e["n"]) >= 0.6:
                return e, "abbr"
    return None, None


def match_xrc(T, name, alts):
    n = norm(name)
    if not n or "workshop" in n:
        return None
    for e in T["xrc"]:
        if e["n"] == n or (e["abbr"] and e["abbr"] in set(alts or [])):
            return e
    return None


# ---------------------------------------------------------------- metadata
def fetch_raw(papers, cache):
    s2_need = [p for p in papers if p["key"] not in cache.get("s2", {})]
    ids = {}
    for p in s2_need:
        q = p.get("s2_id") or (("ARXIV:" + p["arxiv_id"]) if p.get("arxiv_id") else (("DOI:" + p["doi"]) if p.get("doi") else None))
        if q: ids[q] = p["key"]
    keys = list(ids)
    hdr = {"Content-Type": "application/json"}
    if os.environ.get("S2_API_KEY"): hdr["x-api-key"] = os.environ["S2_API_KEY"]
    for i in range(0, len(keys), 100):
        chunk = keys[i:i + 100]
        try:
            res = http_json("https://api.semanticscholar.org/graph/v1/paper/batch?fields=venue,publicationVenue,journal,publicationTypes,externalIds",
                            data=json.dumps({"ids": chunk}).encode(), headers=hdr)
            for q, r in zip(chunk, res):
                cache.setdefault("s2", {})[ids[q]] = r
        except Exception as e:
            print(f"[warn] S2 venue batch failed: {e}", file=sys.stderr)
        time.sleep(3)
    oa_need = [p for p in papers if p.get("openalex") and p["key"] not in cache.get("oa", {})]
    for i in range(0, len(oa_need), 50):
        chunk = oa_need[i:i + 50]
        params = {"filter": "ids.openalex:" + "|".join(p["openalex"] for p in chunk), "per-page": 50,
                  "select": "id,type,doi,primary_location,locations"}
        if os.environ.get("OPENALEX_MAILTO"): params["mailto"] = os.environ["OPENALEX_MAILTO"]
        try:
            res = http_json("https://api.openalex.org/works?" + urllib.parse.urlencode(params, safe=":|"))
            byid = {w["id"].rsplit("/", 1)[-1]: w for w in res.get("results", [])}
            for p in chunk:
                cache.setdefault("oa", {})[p["key"]] = byid.get(p["openalex"])
        except Exception as e:
            print(f"[warn] OpenAlex venue batch failed: {e}", file=sys.stderr)
        time.sleep(0.5)
    return cache


def tnorm(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def refresh_preprints(papers, cache, prev, days):
    """Papers that were arXiv-only (or unknown) last time get re-checked every `days` days:
    1. drop their cached S2/OpenAlex records so the batch fetch picks up a newly added venue;
    2. search OpenAlex for a separate published record with the *same title* (OpenAlex does not always merge
       a preprint with its journal/conference version); if found, use it as the paper's OpenAlex record.
    Title must match exactly after normalisation — renamed published versions are deliberately not handled."""
    today = dt.date.today()
    checked = cache.setdefault("checked", {})
    pubver = cache.setdefault("pubver", {})
    todo = []
    for p in papers:
        if prev.get(p["key"]) not in ("arxiv-only", "unknown", "preprint") or p["key"] in pubver:
            continue
        last = checked.get(p["key"])
        if last and (today - dt.date.fromisoformat(last)).days < days:
            continue
        todo.append(p)
    for p in todo:
        q = re.sub(r"[,:|()]", " ", p.get("title") or "").strip()
        if not q:
            continue
        params = {"filter": "title.search:" + q[:200], "per-page": 10, "select": "id,type,doi,title,primary_location,locations"}
        if os.environ.get("OPENALEX_MAILTO"): params["mailto"] = os.environ["OPENALEX_MAILTO"]
        try:
            res = http_json("https://api.openalex.org/works?" + urllib.parse.urlencode(params, safe=":|"))
        except Exception as e:
            print(f"[warn] preprint re-check failed for {p['key']}: {e}", file=sys.stderr)
            continue  # not marked as checked: retried next run
        # the query worked: drop cached S2/OpenAlex records so the batch fetch below sees any newly added venue
        cache.get("s2", {}).pop(p["key"], None)
        cache.get("oa", {}).pop(p["key"], None)
        for w in res.get("results", []):
            src = ((w.get("primary_location") or {}).get("source") or {})
            if tnorm(w.get("title")) == tnorm(p.get("title")) and src.get("type") in ("journal", "conference") \
                    and not ARXIV.search(src.get("display_name") or "") and not PREPRINT.search(src.get("display_name") or ""):
                pubver[p["key"]] = w
                break
        checked[p["key"]] = today.isoformat()
        time.sleep(0.3)
    if todo:
        print(f"re-checked {len(todo)} preprints for a published version (every {days} days)", file=sys.stderr)


def candidates(p, raw, override):
    cands, thesis, preprint = [], False, None
    if override:
        o = override if isinstance(override, dict) else {"venue": override}
        return [{"name": o["venue"], "kind": o.get("type", "unknown"), "issn": set(), "alts": [], "src": "override"}], False, None
    s2 = (raw.get("s2") or {}).get(p["key"]) or {}
    # a separately indexed published version with the same title wins over the (preprint) record
    oa = (raw.get("pubver") or {}).get(p["key"]) or (raw.get("oa") or {}).get(p["key"]) or {}
    if oa.get("type") == "dissertation":
        thesis = True
    for loc in [oa.get("primary_location") or {}] + (oa.get("locations") or []):
        src = loc.get("source") or {}
        name = src.get("display_name") or ""
        if not name or ARXIV.search(name):
            continue
        if PREPRINT.search(name):
            preprint = preprint or name; continue
        if src.get("type") == "repository":
            if THESIS.search(name): thesis = True
            continue
        if src.get("type") in ("journal", "conference", "book series", "ebook platform"):
            kind = "conference" if src["type"] == "conference" else ("journal" if src["type"] == "journal" else "unknown")
            cands.append({"name": name, "kind": kind, "issn": issns(src.get("issn_l"), *(src.get("issn") or [])), "alts": [], "src": "openalex"})
    # Semantic Scholar links venues partly by acronym and mislabels small venues (IEEE CSR -> "Computer Science
    # Symposium in Russia", IEEE CAI -> "Conference on Algebraic Informatics"). OpenAlex venue data comes from the
    # publisher's DOI metadata, so when both exist and disagree, keep OpenAlex and record the conflict.
    # generic containers (LNCS, Springer eBooks…) are kept as a fallback but never override a specific S2 venue
    generic = [c for c in cands if GENERIC.search(c["name"])]
    cands = [c for c in cands if not GENERIC.search(c["name"])]
    oa_cands = list(cands)

    def agrees(name, issn=set()):
        return any(same_venue(name, c["name"]) or (issn & c["issn"]) for c in oa_cands)

    conflicts = []
    pv = s2.get("publicationVenue") or {}
    if pv.get("name") and not ARXIV.search(pv["name"]):
        pv_issn = issns(pv.get("issn"), *(pv.get("alternate_issns") or []))
        if PREPRINT.search(pv["name"]):
            preprint = preprint or pv["name"]
        elif oa_cands and not agrees(pv["name"], pv_issn):
            conflicts.append(pv["name"])
        else:
            cands.insert(0, {"name": pv["name"], "kind": pv.get("type") or "unknown", "issn": pv_issn,
                             "alts": pv.get("alternate_names") or [], "src": "s2"})
    for nm in ((s2.get("journal") or {}).get("name"), s2.get("venue")):
        if not nm or ARXIV.search(nm) or PREPRINT.search(nm) or any(norm(c["name"]) == norm(nm) for c in cands):
            continue
        if oa_cands and not agrees(nm):
            conflicts.append(nm); continue
        cands.append({"name": nm, "kind": "unknown", "issn": set(), "alts": [], "src": "s2"})
    if not cands:
        cands = generic  # only a series/platform name is known
    # preprint servers recognisable from the DOI alone (works even when the metadata APIs are unavailable)
    doi = (p.get("doi") or "").lower()
    for prefix, server in (("10.5281/zenodo", "Zenodo"), ("10.2139/ssrn", "SSRN"), ("10.36227/techrxiv", "TechRxiv"),
                           ("10.20944/preprints", "Preprints.org"), ("10.21203/rs.", "Research Square")):
        if not cands and not preprint and doi.startswith(prefix):
            preprint = server
    for c in cands:
        c["conflicts"] = conflicts
    return cands, thesis, preprint


def label(p, raw, T, override):
    cands, thesis, preprint = candidates(p, raw, override)
    best = None
    for c in cands:
        r = {"venue": c["name"], "venue_kind": c["kind"], "src": c["src"], "conflict": "; ".join(c.get("conflicts") or []),
             "ccf": None, "ccf_abbr": None, "ccf_method": None,
             "cas_zone": None, "cas_top": False, "jcr_q": None, "jcr_if": None, "xr_zone": None, "xr_top": False, "warning": None}
        cas = next((T["cas"][x] for x in c["issn"] if x in T["cas"]), None) or T["cas_name"].get(norm(c["name"]))
        jcr = next((T["jcr"][x] for x in c["issn"] if x in T["jcr"]), None) or T["jcr_name"].get(norm(c["name"]))
        xr = next((T["xr"][x] for x in c["issn"] if x in T["xr"]), None) or T["xr_name"].get(norm(c["name"]))
        if cas or jcr or xr:
            r["venue_kind"] = "journal"
        if cas: r["cas_zone"], r["cas_top"] = cas["zone"], cas["top"]
        if jcr: r["jcr_q"], r["jcr_if"] = jcr["q"], jcr["if"]
        if xr: r["xr_zone"], r["xr_top"] = xr["zone"], xr["top"]
        e, how = match_ccf(T, c["name"], r["venue_kind"] if r["venue_kind"] != "unknown" else None, c["alts"])
        if e:
            r["ccf"], r["ccf_abbr"], r["ccf_method"] = e["rank"], e["abbr"], how
            if r["venue_kind"] == "unknown": r["venue_kind"] = e["kind"]
        if r["venue_kind"] != "journal":
            xc = match_xrc(T, c["name"], c["alts"])
            if xc: r["xr_zone"], r["xr_top"] = xc["zone"], xc["top"]
        r["warning"] = T["warn"].get(norm(c["name"]))
        rank = (r["ccf"] or "Z", r["cas_zone"] or 9, r["jcr_q"] or "Q9")
        if best is None or rank < best[0]:
            best = (rank, r)
    if best:
        r = best[1]
        r["pub_type"] = "workshop" if "workshop" in norm(r["venue"]) else (r["venue_kind"] if r["venue_kind"] in ("journal", "conference") else "published")
    else:
        r = {"venue": preprint or "", "pub_type": "thesis" if thesis else ("preprint" if preprint else ("arxiv-only" if p.get("arxiv_id") else "unknown"))}
    r["has_arxiv"] = bool(p.get("arxiv_id"))
    r["key"], r["title"], r["category"], r["year"] = p["key"], p["title"], p.get("category"), p.get("year")
    return r


# ---------------------------------------------------------------- stats
TYPES = ["conference", "journal", "workshop", "published", "thesis", "preprint", "arxiv-only", "unknown"]
TYPE_ZH = {"conference": "会议", "journal": "期刊", "workshop": "Workshop", "published": "已发表(其他)", "thesis": "学位论文",
           "preprint": "其他预印本", "arxiv-only": "仅 arXiv", "unknown": "未知"}


def stats(labels):
    def block(items):
        c = collections.Counter(x["pub_type"] for x in items)
        ccf = collections.Counter(x.get("ccf") or "无" for x in items if x["pub_type"] in ("conference", "journal", "workshop", "published"))
        cas = collections.Counter((f"{x['cas_zone']}区" + (" Top" if x.get("cas_top") else "")) if x.get("cas_zone") else "未收录"
                                  for x in items if x["pub_type"] == "journal")
        jcr = collections.Counter(x.get("jcr_q") or "未收录" for x in items if x["pub_type"] == "journal")
        xr = collections.Counter(f"{x['xr_zone']}区" + (" Top" if x.get("xr_top") else "") for x in items if x.get("xr_zone"))
        return {"n": len(items), "types": dict(c), "ccf": dict(ccf), "cas": dict(cas), "jcr": dict(jcr), "xr": dict(xr),
                "warning": sum(1 for x in items if x.get("warning")),
                "arxiv_published": sum(1 for x in items if x["has_arxiv"] and x["pub_type"] not in ("arxiv-only", "unknown"))}
    by_cat = collections.defaultdict(list); by_year = collections.defaultdict(list)
    for x in labels:
        by_cat[x["category"]].append(x); by_year[x.get("year")].append(x)
    return {"all": block(labels), "by_category": {k: block(v) for k, v in sorted(by_cat.items())},
            "by_year": {str(k): block(v) for k, v in sorted(by_year.items(), key=lambda kv: kv[0] or 0)}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--overrides")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--recheck-days", type=int, default=7, help="re-check arXiv-only papers for a published version every N days")
    a = ap.parse_args()
    papers = json.load(open(os.path.join(a.out, "papers.json"), encoding="utf-8"))["papers"]
    raw_path = os.path.join(a.out, "venues_raw.json")
    raw = {} if a.refresh or not os.path.exists(raw_path) else json.load(open(raw_path, encoding="utf-8"))
    vpath = os.path.join(a.out, "venues.json")
    prev = {x["key"]: x["pub_type"] for x in json.load(open(vpath, encoding="utf-8"))} if os.path.exists(vpath) else {}
    prev_full = {x["key"]: x for x in json.load(open(vpath, encoding="utf-8"))} if os.path.exists(vpath) else {}
    refresh_preprints(papers, raw, prev, a.recheck_days)
    T = load_tiers()
    if not T["ccf"]:
        sys.exit(f"tier tables missing in {DATA} — run: python3 -I {os.path.join(HERE, 'fetch_data.py')}")
    raw = fetch_raw(papers, raw)
    json.dump(raw, open(raw_path, "w", encoding="utf-8"), ensure_ascii=False)
    overrides = json.load(open(a.overrides, encoding="utf-8")) if a.overrides and os.path.exists(a.overrides) else {}
    labels = [label(p, raw, T, overrides.get(p["key"])) for p in papers]
    S = stats(labels)
    # log preprints that turned out to be formally published (arXiv-only -> conference/journal/...)
    PUBD = ("conference", "journal", "workshop", "published")
    changes = [(x, prev_full[x["key"]]) for x in labels if x["key"] in prev_full
               and prev_full[x["key"]]["pub_type"] in ("arxiv-only", "preprint", "unknown") and x["pub_type"] in PUBD]
    if changes:
        log = os.path.join(a.out, "venue_changes.md")
        new = not os.path.exists(log)
        with open(log, "a", encoding="utf-8") as f:
            if new: f.write("# 预印本转正式发表记录\n\n由 venues.py 自动追加(仅识别标题不变的情况)。\n\n")
            for x, o in changes:
                tier = " ".join(t for t in (f"CCF-{x['ccf']}" if x.get("ccf") else "", f"中科院{x['cas_zone']}区" if x.get("cas_zone") else "",
                                            x.get("jcr_q") or "") if t)
                f.write(f"- {dt.date.today()} [{x['key']}] {x['title']}:{o['pub_type']} → {x['pub_type']} · {x['venue']}{(' · ' + tier) if tier else ''}\n")
        print(f"{len(changes)} preprint(s) now formally published -> venue_changes.md", file=sys.stderr)
    json.dump(labels, open(os.path.join(a.out, "venues.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    cols = ["key", "category", "year", "title", "pub_type", "venue", "ccf", "ccf_abbr", "cas_zone", "cas_top", "jcr_q", "jcr_if",
            "xr_zone", "warning", "has_arxiv", "ccf_method", "src"]
    with open(os.path.join(a.out, "venues.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(labels)

    gpath = os.path.join(a.out, "graph.json")
    labels_cat = {}
    if os.path.exists(gpath):
        g = json.load(open(gpath, encoding="utf-8"))
        by = {x["key"]: x for x in labels}
        for n in g["nodes"]:
            x = by.get(n["key"])
            if x:
                n["pub"] = {k: x.get(k) for k in ("pub_type", "venue", "ccf", "ccf_abbr", "cas_zone", "cas_top", "jcr_q", "jcr_if", "xr_zone", "xr_top", "warning", "has_arxiv")}
        g["venue_stats"] = S
        labels_cat = {c["name"]: c["label"] for c in g.get("categories", [])}
        json.dump(g, open(gpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    A = S["all"]
    pubd = sum(A["types"].get(t, 0) for t in ("conference", "journal", "workshop", "published"))
    L = ["# 发表情况统计", "",
         f"- 论文 {A['n']} 篇：已正式发表 {pubd} 篇(会议 {A['types'].get('conference', 0)}、期刊 {A['types'].get('journal', 0)}、"
         f"Workshop {A['types'].get('workshop', 0)}、其他 {A['types'].get('published', 0)}),仅 arXiv 预印本 {A['types'].get('arxiv-only', 0)} 篇，"
         f"其他预印本 {A['types'].get('preprint', 0)} 篇，学位论文 {A['types'].get('thesis', 0)} 篇，未知 {A['types'].get('unknown', 0)} 篇",
         f"- 有 arXiv 版本且已正式发表：{A['arxiv_published']} 篇",
         f"- CCF(已发表论文中):" + "、".join(f"{k}{'类' if k in 'ABC' else ''} {v}" for k, v in sorted(A["ccf"].items())),
         f"- 中科院分区(期刊论文中):" + "、".join(f"{k} {v}" for k, v in sorted(A["cas"].items())),
         f"- JCR(期刊论文中):" + "、".join(f"{k} {v}" for k, v in sorted(A["jcr"].items())),
         f"- 新锐分区(期刊与会议中，仅列已收录的):" + ("、".join(f"{k} {v}" for k, v in sorted(A["xr"].items())) or "无"),
         f"- 预警期刊：{A['warning']} 篇", "",
         "## 按方向", "", "| 方向 | 篇数 | 会议 | 期刊 | Workshop | 仅 arXiv | 预印本 | 学位论文 | CCF-A | CCF-B | CCF-C | 中科院1区 | 中科院2区 | JCR Q1 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for cat, B in S["by_category"].items():
        t, c = B["types"], B["ccf"]
        cas1 = sum(v for k, v in B["cas"].items() if k.startswith("1区")); cas2 = sum(v for k, v in B["cas"].items() if k.startswith("2区"))
        L.append(f"| {labels_cat.get(cat, cat)} | {B['n']} | {t.get('conference', 0)} | {t.get('journal', 0)} | {t.get('workshop', 0)} | {t.get('arxiv-only', 0)} | "
                 f"{t.get('preprint', 0)} | {t.get('thesis', 0)} | {c.get('A', 0)} | {c.get('B', 0)} | {c.get('C', 0)} | {cas1} | {cas2} | {B['jcr'].get('Q1', 0)} |")
    L += ["", "## 按年份", "", "| 年份 | 篇数 | 已发表 | 仅 arXiv | CCF-A/B | 中科院1-2区 |", "|---|---|---|---|---|---|"]
    for y, B in S["by_year"].items():
        t = B["types"]; pub = sum(t.get(k, 0) for k in ("conference", "journal", "workshop", "published"))
        ab = B["ccf"].get("A", 0) + B["ccf"].get("B", 0)
        c12 = sum(v for k, v in B["cas"].items() if k[:1] in "12")
        L.append(f"| {y} | {B['n']} | {pub} | {t.get('arxiv-only', 0)} | {ab} | {c12} |")
    review = [x for x in labels if (x.get("ccf_method") or "").startswith(("similar", "abbr"))]
    unmatched = [x for x in labels if x["pub_type"] in ("conference", "journal", "workshop", "published") and not (x.get("ccf") or x.get("cas_zone") or x.get("jcr_q"))]
    L += ["", f"## 需复核：模糊/缩写匹配的 CCF 等级({len(review)})", ""]
    L += [f"- [{x['key']}] {x['venue']} → CCF-{x['ccf']} {x['ccf_abbr']} ({x['ccf_method']})" for x in review]
    L += ["", f"## 已发表但未匹配到任何等级({len(unmatched)})", "",
          "未入 CCF/中科院/JCR 的会议、期刊或 workshop。若确有对应等级，可在 overrides 文件中指定标准刊名后重跑。", ""]
    L += [f"- [{x['key']}] {x['venue']} ({TYPE_ZH.get(x['pub_type'], x['pub_type'])})"
          + (" — 仅来自 Semantic Scholar,可信度较低" if x.get("src") == "s2" else "") for x in unmatched]
    conf = [x for x in labels if x.get("conflict")]
    L += ["", f"## 来源冲突：已采用 OpenAlex,忽略 Semantic Scholar 的出版场所({len(conf)})", ""]
    L += [f"- [{x['key']}] 采用「{x['venue']}」,忽略「{x['conflict']}」" for x in conf]
    open(os.path.join(a.out, "venues_stats.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"labelled {len(labels)} papers: published {pubd}, arXiv-only {A['types'].get('arxiv-only', 0)}; "
          f"{len(review)} fuzzy CCF matches and {len(unmatched)} unranked venues to review -> venues_stats.md")


if __name__ == "__main__":
    main()
