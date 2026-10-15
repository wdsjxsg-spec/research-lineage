#!/usr/bin/env python3
"""Collect metadata + citation links for a paper collection (stdlib only).

Inputs (combine freely):
  --dir PATH    folder of papers; files named "<arXivID>_<title>.pdf" (or any name -> title-only).
                The first sub-folder under PATH becomes the paper's category.
  --ids FILE    one arXiv ID per line, optionally "ID<sep>category" (sep: tab , |)
  --csv FILE    columns: arxiv_id|id (optional), title (optional), category (optional)

Output: <out>/papers.json  (cached; re-runs only fetch what is missing unless --refresh)

Sources: arXiv API (title, abstract, date, authors) and the Semantic Scholar Graph API
batch endpoint (citation counts, references, citations). Set S2_API_KEY for higher limits.
"""
import argparse, csv, datetime as dt, fnmatch, html, http.client, json, os, re, sys, time
import urllib.error, urllib.parse, urllib.request

UA = "research-lineage-skill/1.0 (literature analysis)"
ARXIV_RE = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?")
S2_FIELDS = ("title,year,venue,publicationDate,citationCount,externalIds,"
             "references.paperId,references.externalIds,references.title,references.year,"
             "citations.paperId,citations.externalIds,citations.title,citations.year")
DEFAULT_EXCLUDE = ["00-inbox", "archive", "_*", ".*"]
WARNINGS = []


def warn(msg):
    WARNINGS.append(msg)
    print(f"[warn] {msg}", file=sys.stderr, flush=True)


def http(url, data=None, headers=None, tries=6, timeout=120):
    """GET/POST with exponential backoff on 429/5xx. Raises after the last try."""
    hdrs = {"User-Agent": UA, **(headers or {})}
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                ra = int(e.headers.get("Retry-After") or 0) if str(e.headers.get("Retry-After") or "").isdigit() else 0
                if ra > 300:
                    # daily quota exhausted (OpenAlex sends Retry-After until midnight UTC): fail fast, the cache keeps
                    # what we have; sleeping for hours would hang scheduled runs
                    raise
                wait = ra or min(120, 5 * 2 ** i)
                print(f"  HTTP {e.code}, retry in {wait}s", file=sys.stderr, flush=True)
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, OSError):
            # includes RemoteDisconnected ("Remote end closed connection") that arXiv sometimes sends
            if i < tries - 1:
                time.sleep(5 * (i + 1)); continue
            raise


def s2_headers():
    key = os.environ.get("S2_API_KEY")
    return {"x-api-key": key} if key else {}


# ---------------------------------------------------------------- inputs
def from_dir(root, exclude):
    out = []
    root = os.path.abspath(root)
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not any(fnmatch.fnmatch(d, p) for p in exclude)]
        rel = os.path.relpath(dirpath, root)
        category = "uncategorized" if rel == "." else rel.split(os.sep)[0]
        for f in files:
            if not f.lower().endswith(".pdf") or any(fnmatch.fnmatch(f, p) for p in exclude):
                continue
            stem = f[:-4]
            m = ARXIV_RE.match(stem)
            if m:
                title = stem[len(m.group(0)):].lstrip("_ -") or None
                out.append({"arxiv_id": m.group(1), "title": title, "category": category,
                            "file": os.path.join(dirpath, f)})
            else:
                out.append({"arxiv_id": None, "title": stem, "category": category,
                            "file": os.path.join(dirpath, f)})
    return out


def from_ids(path):
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = re.split(r"[\t,|]", line, maxsplit=1)
        m = ARXIV_RE.match(parts[0].strip().replace("arXiv:", ""))
        if not m:
            warn(f"not an arXiv id, skipped: {parts[0]}"); continue
        out.append({"arxiv_id": m.group(1), "title": None,
                    "category": parts[1].strip() if len(parts) > 1 else "uncategorized"})
    return out


def from_csv(path):
    out = []
    for row in csv.DictReader(open(path, encoding="utf-8")):
        raw = (row.get("arxiv_id") or row.get("id") or row.get("arxiv") or "").strip()
        m = ARXIV_RE.match(raw.replace("arXiv:", "")) if raw else None
        title = (row.get("title") or row.get("filename") or "").strip() or None
        if title and title.lower().endswith(".pdf"):
            title = ARXIV_RE.sub("", title[:-4]).lstrip("_ -")
        doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", (row.get("doi") or "").strip(), flags=re.I).lower() or None
        if not m and not title and not doi:
            continue
        out.append({"arxiv_id": m.group(1) if m else None, "title": title, "doi": doi,
                    "category": (row.get("category") or "uncategorized").strip()})
    return out


# ---------------------------------------------------------------- fetchers
def arxiv_meta(ids):
    """id_list in batches of 50 (arXiv rejects very long lists; max_results=0 returns HTTP 500)."""
    meta = {}
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        url = ("http://export.arxiv.org/api/query?id_list=" + ",".join(chunk)
               + f"&max_results={len(chunk)}")
        try:
            t = http(url).decode("utf-8", "ignore")
        except Exception as e:
            warn(f"arXiv metadata batch failed ({chunk[0]}..): {e}"); continue
        for e in re.findall(r"<entry>(.*?)</entry>", t, re.S):
            idm = re.search(r"<id>https?://arxiv.org/abs/(.*?)</id>", e)
            if not idm:
                continue
            aid = re.sub(r"v\d+$", "", idm.group(1))
            g = lambda tag: html.unescape(re.sub(r"\s+", " ", (re.search(fr"<{tag}>(.*?)</{tag}>", e, re.S) or [None, ""])[1])).strip()
            meta[aid] = {
                "title": g("title"), "abstract": g("summary"), "published": g("published")[:10],
                "authors": [html.unescape(a).strip() for a in re.findall(r"<name>(.*?)</name>", e)][:6],
                "withdrawn": "withdrawn" in g("arxiv:comment").lower() if "<arxiv:comment" in e else False,
            }
        time.sleep(3)
    return meta


def clean_title(title):
    """Filenames often carry venue suffixes and ' - ' instead of ':'; strip them for matching."""
    t = re.sub(r"\s*[\(\[][^()\[\]]*\d{4}[^()\[\]]*[\)\]]\s*$", "", title)  # "(USENIX Security 2025)"
    return re.sub(r"\s+-\s+", ": ", t).strip()


def s2_match_title(title):
    url = ("https://api.semanticscholar.org/graph/v1/paper/search/match?query="
           + urllib.parse.quote(clean_title(title)[:300]) + "&fields=paperId,title,externalIds")
    try:
        d = json.loads(http(url, headers=s2_headers()))
        best = (d.get("data") or [None])[0]
        return best
    except urllib.error.HTTPError as e:
        if e.code != 404:
            warn(f"S2 title match failed for '{title[:60]}': {e}")
    except Exception as e:
        warn(f"S2 title match failed for '{title[:60]}': {e}")
    return None


def s2_batch(ids):
    """POST /paper/batch: one request per 100 ids instead of one per paper (avoids most 429s)."""
    res = {}
    url = "https://api.semanticscholar.org/graph/v1/paper/batch?fields=" + S2_FIELDS
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        body = json.dumps({"ids": chunk}).encode()
        try:
            d = json.loads(http(url, data=body, headers={"Content-Type": "application/json", **s2_headers()}))
        except Exception as e:
            warn(f"S2 batch failed for {len(chunk)} ids starting {chunk[0]}: {e}"); continue
        for q, p in zip(chunk, d):
            if p is None:
                warn(f"S2 has no record for {q}")
            res[q] = p
        time.sleep(1 if s2_headers() else 3)
    return res


# ---------------------------------------------------------------- OpenAlex fallback
OPENALEX = "https://api.openalex.org"


def oa_get(path, params):
    params = dict(params)
    if os.environ.get("OPENALEX_MAILTO"): params["mailto"] = os.environ["OPENALEX_MAILTO"]
    if os.environ.get("OPENALEX_API_KEY"): params["api_key"] = os.environ["OPENALEX_API_KEY"]
    return json.loads(http(f"{OPENALEX}/{path}?" + urllib.parse.urlencode(params, safe=":,|"), tries=4))


def oa_doi(p):
    if p.get("doi"):
        return p["doi"].lower()
    return f"10.48550/arxiv.{p['arxiv_id']}" if p.get("arxiv_id") else None


def openalex_fallback(papers):
    """Attach OpenAlex IDs to every paper (needed to map links), then fill refs/cites from OpenAlex
    for papers Semantic Scholar does not index (theses, very new or regional venues)."""
    need_id = [p for p in papers if not p.get("openalex")]
    dois = {}
    for p in need_id:
        d = oa_doi(p)
        if d: dois.setdefault(d, []).append(p)
    keys = list(dois)
    for i in range(0, len(keys), 50):
        try:
            r = oa_get("works", {"filter": "doi:" + "|".join(keys[i:i + 50]), "per-page": 50, "select": "id,doi"})
            for w in r.get("results", []):
                for p in dois.get((w.get("doi") or "").replace("https://doi.org/", "").lower(), []):
                    p["openalex"] = w["id"].rsplit("/", 1)[-1]
        except Exception as e:
            warn(f"OpenAlex id lookup failed: {e}")
        time.sleep(0.5)
    # OpenAlex merges an arXiv preprint with its published version and returns the published DOI,
    # so batch results cannot be matched back by DOI — look the rest up one by one.
    for p in papers:
        d = oa_doi(p)
        if p.get("openalex") or not d:
            continue
        try:
            w = oa_get(f"works/doi:{d}", {"select": "id,doi"})
            p["openalex"] = w["id"].rsplit("/", 1)[-1]
            pub = (w.get("doi") or "").replace("https://doi.org/", "").lower()
            if pub and not pub.startswith("10.48550/") and not p.get("doi"):
                p["published_doi"] = pub  # evidence the preprint was formally published
        except urllib.error.HTTPError as e:
            if e.code != 404: warn(f"OpenAlex lookup failed for {d}: {e}")
        except Exception as e:
            warn(f"OpenAlex lookup failed for {d}: {e}")
        time.sleep(0.3)
    for p in papers:
        if not p.get("openalex") and not p.get("s2_ok") and p.get("title"):
            try:
                q = re.sub(r"[,:|]", " ", p["title"])
                r = oa_get("works", {"filter": f"title.search:{q}", "per-page": 1, "select": "id,title"})["results"]
                if r and re.sub(r"\W", "", r[0]["title"].lower())[:60] == re.sub(r"\W", "", p["title"].lower())[:60]:
                    p["openalex"] = r[0]["id"].rsplit("/", 1)[-1]
            except Exception as e:
                warn(f"OpenAlex title lookup failed for '{p['title'][:50]}': {e}")
            time.sleep(0.5)
    filled = 0
    for p in papers:
        if p.get("s2_ok") or not p.get("openalex"):
            continue
        try:
            w = oa_get(f"works/{p['openalex']}", {"select": "referenced_works,publication_date,cited_by_count"})
            c = oa_get("works", {"filter": f"cites:{p['openalex']}", "per-page": 200, "select": "id,title,publication_date"})
        except Exception as e:
            warn(f"OpenAlex links failed for {p['key']}: {e}"); continue
        p["refs"] = [{"arxiv_id": None, "s2_id": None, "openalex": u.rsplit("/", 1)[-1], "title": None, "year": None}
                     for u in w.get("referenced_works") or []]
        p["cites"] = [{"arxiv_id": None, "s2_id": None, "openalex": x["id"].rsplit("/", 1)[-1], "title": x.get("title"),
                       "year": int(x["publication_date"][:4]) if x.get("publication_date") else None} for x in c.get("results", [])]
        p["citationCount"] = p.get("citationCount") or w.get("cited_by_count")
        if not p.get("published") and w.get("publication_date"):
            p["published"] = w["publication_date"]; p["year"] = int(w["publication_date"][:4])
        p["oa_ok"] = True; filled += 1
        time.sleep(0.5)
    if filled:
        print(f"OpenAlex fallback: links for {filled} papers Semantic Scholar does not index", file=sys.stderr)


# ---------------------------------------------------------------- main
def fallback_key(it):
    """Key for a paper S2 cannot resolve (also the cache key for OpenAlex-only papers)."""
    return ("doi:" + it["doi"]) if it["doi"] else "title:" + re.sub(r"\W+", "-", (it["title"] or "x").lower())[:60]


def link(p):
    ext = p.get("externalIds") or {}
    ax = ext.get("ArXiv")
    return {"arxiv_id": ax, "s2_id": p.get("paperId"), "title": p.get("title"), "year": p.get("year")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", action="append", default=[])
    ap.add_argument("--ids")
    ap.add_argument("--csv")
    ap.add_argument("--exclude", action="append", help=f"folder/file globs to skip (default {DEFAULT_EXCLUDE})")
    ap.add_argument("--out", required=True, help="output folder (papers.json is written here)")
    ap.add_argument("--refresh", action="store_true", help="ignore cache and refetch everything")
    a = ap.parse_args()

    items = []
    for d in a.dir:
        items += from_dir(d, a.exclude or DEFAULT_EXCLUDE)
    if a.ids:
        items += from_ids(a.ids)
    if a.csv:
        items += from_csv(a.csv)
    if not items:
        sys.exit("no papers found in the given inputs")

    # dedupe: arXiv id first, else normalized title
    seen, uniq = set(), []
    for it in items:
        it.setdefault("doi", None)
        k = it["arxiv_id"] or (("d:" + it["doi"]) if it["doi"] else "t:" + re.sub(r"\W+", "", (it["title"] or "").lower()))
        if k not in seen:
            seen.add(k); uniq.append(it)
    items = uniq
    os.makedirs(a.out, exist_ok=True)
    out_path = os.path.join(a.out, "papers.json")
    cache = {}
    if os.path.exists(out_path) and not a.refresh:
        for p in json.load(open(out_path, encoding="utf-8")).get("papers", []):
            # papers S2 does not index but OpenAlex does are cached too; otherwise every run would retry
            # S2 title matching for them, with minutes of 429 backoff each
            if p.get("s2_ok") or p.get("oa_ok"):
                cache[p["key"]] = p
    cache_doi = {p["doi"]: p for p in cache.values() if p.get("doi")}
    tnorm = lambda t: re.sub(r"\W+", "", clean_title(t or "").lower())[:80]
    cache_title = {tnorm(p.get("title")): p for p in cache.values() if p.get("title")}
    print(f"{len(items)} papers in collection, {len(cache)} cached", file=sys.stderr)

    ax_ids = [it["arxiv_id"] for it in items if it["arxiv_id"]]
    need_ax = [i for i in ax_ids if i not in cache]
    ameta = arxiv_meta(need_ax) if need_ax else {}

    # resolve items to S2 ids: arXiv ID > DOI (exact, fast) > title match (slow, may fail)
    queries = {}
    for it in items:
        it["_fb"] = fallback_key(it) if not it["arxiv_id"] else None
    doi_items = [it for it in items if not it["arxiv_id"] and it["doi"] and it["doi"] not in cache_doi and it["_fb"] not in cache]
    doi_hits = s2_batch(["DOI:" + it["doi"] for it in doi_items]) if doi_items else {}
    for it in items:
        if it["arxiv_id"]:
            if it["arxiv_id"] not in cache:
                queries["ARXIV:" + it["arxiv_id"]] = it
        elif it["doi"] and (it["doi"] in cache_doi or doi_hits.get("DOI:" + it["doi"])):
            continue  # resolved by DOI (fresh or cached)
        elif it["_fb"] in cache:
            continue  # known S2 miss with OpenAlex links (cached); use --refresh to retry S2
        elif it["title"] and tnorm(it["title"]) in cache_title:
            it["_cached"] = cache_title[tnorm(it["title"])]  # title-only paper resolved on an earlier run
            continue
        else:
            m = s2_match_title(it["title"]) if it["title"] else None
            time.sleep(1 if s2_headers() else 3)
            if m and m.get("paperId"):
                it["_s2_match"] = m
                ax = (m.get("externalIds") or {}).get("ArXiv")
                key = ax or "s2:" + m["paperId"]
                if key not in cache:
                    queries[m["paperId"]] = it
            else:
                warn(f"could not resolve title-only paper: {it['title']}")
    extra = [(it["_s2_match"].get("externalIds") or {}).get("ArXiv") for it in items if it.get("_s2_match")]
    extra = [x for x in extra if x and x not in ameta and x not in cache]
    if extra:
        ameta.update(arxiv_meta(extra))
    s2 = s2_batch(list(queries)) if queries else {}
    s2.update({k: v for k, v in doi_hits.items() if v})

    papers = []
    for it in items:
        if it.get("_cached"):
            p = it["_cached"]; p["category"] = it["category"]; papers.append(p); continue
        if it["doi"] and it["doi"] in cache_doi and not it["arxiv_id"]:
            p = cache_doi[it["doi"]]; p["category"] = it["category"]; papers.append(p); continue
        m = it.get("_s2_match")
        dsp = s2.get("DOI:" + it["doi"]) if (it["doi"] and not it["arxiv_id"]) else None
        dax = ((dsp or {}).get("externalIds") or {}).get("ArXiv")
        key = it["arxiv_id"] or dax or ("s2:" + dsp["paperId"] if dsp else None) \
              or ((m.get("externalIds") or {}).get("ArXiv") if m else None) \
              or ("s2:" + m["paperId"] if m else None) \
              or it["_fb"]
        if key in cache:
            p = cache[key]; p["category"] = it["category"]; papers.append(p); continue
        q = ("ARXIV:" + it["arxiv_id"]) if it["arxiv_id"] else ("DOI:" + it["doi"] if dsp else (m["paperId"] if m else None))
        sp = s2.get(q) if q else None
        am = ameta.get(it["arxiv_id"] or (key if ARXIV_RE.match(key) else ""), {})
        title = am.get("title") or (sp or {}).get("title") or it["title"] or key
        p = {
            "key": key, "arxiv_id": key if ARXIV_RE.match(key) else None,
            "doi": (((sp or {}).get("externalIds") or {}).get("DOI") or it["doi"] or "").lower() or None,
            "s2_id": (sp or {}).get("paperId") or (m or {}).get("paperId"),
            "title": title, "abstract": am.get("abstract", ""),
            "authors": am.get("authors", []), "withdrawn": am.get("withdrawn", False),
            "published": am.get("published") or (sp or {}).get("publicationDate") or "",
            "year": (sp or {}).get("year") or (int(am["published"][:4]) if am.get("published") else None),
            "venue": (sp or {}).get("venue") or "",
            "category": it["category"],
            "citationCount": (sp or {}).get("citationCount"),
            "refs": [link(r) for r in ((sp or {}).get("references") or []) if r and r.get("paperId")],
            "cites": [link(c) for c in ((sp or {}).get("citations") or []) if c and c.get("paperId")],
            "s2_ok": sp is not None,
        }
        if not p["published"] and p["year"]:
            p["published"] = f"{p['year']}-01-01"
        papers.append(p)

    openalex_fallback(papers)
    ok = sum(bool(p["s2_ok"] or p.get("oa_ok")) for p in papers)
    if ok < len(papers):
        warn(f"{len(papers) - ok}/{len(papers)} papers lack citation data (S2 miss or rate limit) — "
             "rerun later or set S2_API_KEY; analysis will undercount links for them")
    doc = {"meta": {"created": dt.datetime.now().isoformat(timespec="seconds"),
                    "n_papers": len(papers), "with_citation_data": ok,
                    "s2_api_key": bool(os.environ.get("S2_API_KEY")), "warnings": WARNINGS},
           "papers": papers}
    json.dump(doc, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {out_path}: {len(papers)} papers, citation data for {ok}", file=sys.stderr)


if __name__ == "__main__":
    main()
