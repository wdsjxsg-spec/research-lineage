"""Shared helpers for the research-lineage automation tools: project config, paths, HTTP, arXiv / OpenAlex access,
PDF download, title normalisation. Standard library only.

Every tool takes --config <project>/research-lineage.json (default: ./research-lineage.json). Paths in the config are
relative to the config file's directory (the project root).
"""
import html, json, os, re, sys, time
import urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
UA = "Mozilla/5.0 (compatible; research-lineage-crawler)"
ARXIV_ID = re.compile(r"^\d{4}\.\d{4,5}$")

DEFAULT_PATHS = {
    "papers": "papers",          # one sub-folder per category, e.g. papers/01-xxx/
    "inbox": "papers/00-inbox",  # crawler candidates awaiting review
    "archive": "archive",        # removed papers (still used for de-duplication)
    "lineage": "lineage",        # research-lineage output folder
    "state": "automation",       # seen.json, abstracts.json, auto_ingested.csv, ...
    "notes": "papers/summaries.md",
    "scope": "lineage/prompts/scope.md",
}


class Config:
    def __init__(self, path):
        self.file = os.path.abspath(path)
        if not os.path.exists(self.file):
            sys.exit(f"config not found: {path} (see {os.path.join(SKILL, 'references', 'automation.md')})")
        self.data = json.load(open(self.file, encoding="utf-8"))
        self.root = os.path.dirname(self.file)
        paths = {**DEFAULT_PATHS, **(self.data.get("paths") or {})}
        self.paths = {k: os.path.normpath(os.path.join(self.root, v)) for k, v in paths.items()}

    def __getitem__(self, k):
        return self.paths[k]

    def get(self, k, default=None):
        return self.data.get(k, default)

    @property
    def categories(self):
        """{folder: description}; folders that exist on disk but are not listed are still collected."""
        return self.data.get("categories") or {}

    @property
    def lang(self):
        return self.data.get("lang", "zh")

    def state(self, name):
        return os.path.join(self.paths["state"], name)

    def rel(self, path):
        return os.path.relpath(path, self.root)


def config_arg(ap):
    ap.add_argument("--config", default=os.environ.get("RESEARCH_LINEAGE_CONFIG", "research-lineage.json"),
                    help="project config (default: ./research-lineage.json)")


def load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def save_json(path, obj, indent=1):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    json.dump(obj, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=indent)
    os.replace(tmp, path)


def category_dirs(cfg):
    """Category folders under papers/: listed ones first (config order), then other NN-* folders except the inbox."""
    papers, inbox = cfg["papers"], os.path.basename(cfg["inbox"])
    listed = [c for c in cfg.categories if os.path.isdir(os.path.join(papers, c))]
    extra = sorted(d for d in (os.listdir(papers) if os.path.isdir(papers) else [])
                   if re.match(r"\d\d-", d) and d != inbox and d not in listed and os.path.isdir(os.path.join(papers, d)))
    return listed + extra


# ---------------------------------------------------------------- titles & files
def norm_title(t):
    """Title fingerprint: lowercase alphanumerics only (file names drop : ? etc., so they still match)."""
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())[:90]


def title_from_file(f):
    stem = re.sub(r"^\d{4}\.\d{4,5}_", "", f[:-4])
    return re.sub(r"\s*\([^()]*\d{4}[^()]*\)\s*$", "", stem)  # drop a "(USENIX Security 2025)" style suffix


def sanitize(s):
    return re.sub(r"\s+", " ", re.sub(r'[/:?*"<>|\\]', "", s)).strip()[:150]


def walk_pdfs(base):
    for root, _, files in os.walk(base):
        for f in files:
            if f.lower().endswith(".pdf"):
                yield root, f


# ---------------------------------------------------------------- HTTP
def get(url, data=None, headers=None, timeout=90, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
            return urllib.request.urlopen(req, timeout=timeout).read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(10 * (i + 1)); continue
            if i == tries - 1: raise
        except Exception:
            if i == tries - 1: raise
        time.sleep(5)
    return b""


# ---------------------------------------------------------------- arXiv
def _arxiv_entries(t):
    out = []
    for e in re.findall(r"<entry>(.*?)</entry>", t, re.S):
        m = re.search(r"<id>(.*?)</id>", e)
        if not m or "/abs/" not in m.group(1):
            continue
        aid = re.sub(r"v\d+$", "", m.group(1).split("/abs/")[-1])
        title = html.unescape(re.sub(r"\s+", " ", re.search(r"<title>(.*?)</title>", e, re.S).group(1))).strip()
        abst = html.unescape(re.sub(r"\s+", " ", re.search(r"<summary>(.*?)</summary>", e, re.S).group(1))).strip()
        pub = re.search(r"<published>(.*?)</published>", e).group(1)[:10]
        out.append({"id": aid, "title": title, "abstract": abst, "published": pub})
    return out


def arxiv_search(q, n=50):
    t = ""
    for start in range(0, n, 100):
        url = ("http://export.arxiv.org/api/query?search_query=" + urllib.parse.quote(q)
               + f"&start={start}&max_results={min(100, n - start)}&sortBy=submittedDate&sortOrder=descending")
        page = get(url).decode("utf-8", "ignore")
        t += page
        if page.count("<entry>") < min(100, n - start):
            break
        time.sleep(3)
    return [{**p, "via": "arxiv: " + q} for p in _arxiv_entries(t)]


def arxiv_lookup(ids):
    out = []
    for i in range(0, len(ids), 40):
        url = "http://export.arxiv.org/api/query?id_list=" + ",".join(ids[i:i + 40]) + "&max_results=40"
        out += _arxiv_entries(get(url).decode("utf-8", "ignore"))
        time.sleep(3)
    return out


def s2_citing(anchor):
    url = f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{anchor}/citations?fields=externalIds&limit=100"
    hdr = {"x-api-key": os.environ["S2_API_KEY"]} if os.environ.get("S2_API_KEY") else None
    try:
        d = json.loads(get(url, headers=hdr, tries=4))
    except Exception as ex:
        print(f"[warn] Semantic Scholar citations failed for {anchor}: {ex}", file=sys.stderr)
        return []
    return [(c.get("citingPaper", {}).get("externalIds") or {}).get("ArXiv") for c in d.get("data", [])]


# ---------------------------------------------------------------- OpenAlex
OPENALEX = "https://api.openalex.org"
OA_SELECT = "id,doi,title,publication_date,type,primary_location,best_oa_location,locations,abstract_inverted_index,open_access"
OA_SKIP_TYPES = {"paratext", "erratum", "retraction", "editorial", "letter", "peer-review", "dataset", "grant", "other"}


def oa_get(path, params):
    params = dict(params)
    if os.environ.get("OPENALEX_MAILTO"): params["mailto"] = os.environ["OPENALEX_MAILTO"]
    if os.environ.get("OPENALEX_API_KEY"): params["api_key"] = os.environ["OPENALEX_API_KEY"]
    url = f"{OPENALEX}/{path}?" + urllib.parse.urlencode(params, safe=":,|!")
    return json.loads(get(url, tries=4))


def oa_abstract(inv):
    if not inv:
        return ""
    return " ".join(w for _, w in sorted((i, w) for w, idxs in inv.items() for i in idxs))


def oa_to_cand(w, via):
    """OpenAlex work -> candidate. Papers that have an arXiv version are keyed by their arXiv ID."""
    if not w or not w.get("title") or (w.get("type") in OA_SKIP_TYPES):
        return None
    doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
    ax = None
    m = re.match(r"10\.48550/arxiv\.(\d{4}\.\d{4,5})", doi)
    if m: ax = m.group(1)
    pdfs = []
    for loc in [w.get("best_oa_location") or {}, w.get("primary_location") or {}] + (w.get("locations") or []):
        for u in (loc.get("landing_page_url") or "", loc.get("pdf_url") or ""):
            m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", u)
            if m and not ax: ax = m.group(1)
        if loc.get("pdf_url") and "arxiv.org" not in loc["pdf_url"] and loc["pdf_url"] not in pdfs:
            pdfs.append(loc["pdf_url"])
    landings = [(w.get("open_access") or {}).get("oa_url")] + [l.get("landing_page_url") for l in (w.get("locations") or []) if l.get("is_oa")]
    landings = [u for i, u in enumerate(landings) if u and "doaj.org" not in u and u not in landings[:i] and u not in pdfs]
    src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
    key = ax or (f"doi:{doi}" if doi else "openalex:" + w["id"].rsplit("/", 1)[-1])
    return {"id": key, "arxiv": ax, "doi": doi, "openalex": w["id"].rsplit("/", 1)[-1], "landings": landings,
            "title": html.unescape(re.sub(r"<[^>]+>", "", w["title"])).strip(),
            "abstract": oa_abstract(w.get("abstract_inverted_index")),
            "published": w.get("publication_date") or "", "venue": src, "type": w.get("type"),
            "pdfs": pdfs, "via": via}


# ---------------------------------------------------------------- PDF download
def _is_pdf(data):
    return bool(data) and data[:5] == b"%PDF-" and len(data) > 20000


def download(p, path):
    """arXiv papers from arXiv; others from OpenAlex open-access PDF links, then the citation_pdf_url meta tag of
    open-access landing pages (the standard field publishers expose for indexers). Only real PDFs are accepted —
    paywalls often answer 200 with an HTML page. No access controls are bypassed."""
    ax = p.get("arxiv") or (p["id"] if ARXIV_ID.match(p.get("id", "")) else None)
    urls = ([f"https://arxiv.org/pdf/{ax}"] if ax else []) + list(p.get("pdfs", []))

    def fetch(u):
        try:
            return get(u, timeout=180, tries=2)
        except Exception:
            return None

    for u in urls:
        data = fetch(u)
        if _is_pdf(data):
            open(path, "wb").write(data); return True
        time.sleep(1)
    for land in p.get("landings", []):
        page = fetch(land)
        if not page:
            continue
        if page[:5] == b"%PDF-":
            if len(page) > 20000:
                open(path, "wb").write(page); return True
            continue
        m = re.search(rb'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)', page[:400000], re.I) \
            or re.search(rb'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']citation_pdf_url', page[:400000], re.I)
        if not m:
            continue
        data = fetch(urllib.parse.urljoin(land, html.unescape(m.group(1).decode("utf-8", "ignore"))))
        if _is_pdf(data):
            open(path, "wb").write(data); return True
        time.sleep(1)
    return False


def link_of(p):
    ax = p.get("arxiv") or (p["id"] if ARXIV_ID.match(p.get("id", "")) else None)
    if ax:
        return f"https://arxiv.org/abs/{ax}"
    if p.get("doi"):
        return f"https://doi.org/{p['doi']}"
    return f"https://openalex.org/{p.get('openalex', '')}"
