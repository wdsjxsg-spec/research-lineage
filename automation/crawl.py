#!/usr/bin/env python3
"""Crawl new papers for a research-lineage project. Topic-specific parts (queries, anchors, scoring rules) live in the
project's research-lineage.json under "crawl"; this engine is generic. See references/automation.md.

Sources: arXiv keyword search (newest first) + Semantic Scholar forward citations of anchor papers + OpenAlex keyword
search and anchor citations (journals / conferences / non-arXiv). De-duplicates against papers/, archive/ and seen.json
(arXiv ID, title fingerprint, fuzzy title). Relevant candidates are downloaded to <inbox>/<date>/ with a REPORT.md;
with --auto-ingest, candidates passing the strict "auto_ingest" rules go straight into their category and are logged in
<state>/auto_ingested.csv for weekly review. Non-arXiv papers without an open-access PDF become 0-byte placeholders.

Usage: python3 -I crawl.py --config research-lineage.json [--days 14] [--dry-run] [--auto-ingest] [--sources arxiv,s2,openalex]
       python3 -I crawl.py --config research-lineage.json --eval     # score the current collection and archive (no network)
       python3 -I crawl.py --config research-lineage.json --bootstrap [--since 2018]
            build a collection from scratch: no recency limit, relevance-sorted queries, anchors' references AND citations;
            nothing is downloaded — candidates go to <inbox>/bootstrap-<date>/candidates.tsv + REPORT.md for review,
            then approved ones are added with add_papers.py
"""
import argparse, datetime as dt, difflib, json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (Config, config_arg, load_json, save_json, norm_title, title_from_file, sanitize, walk_pdfs,  # noqa: E402
                    arxiv_search, arxiv_lookup, s2_citing, oa_get, oa_to_cand, oa_works_by_ids, download, link_of,
                    OA_SELECT, ARXIV_ID)

DEFAULT_REPOSITORY = r"zenodo|ssrn|research square|techrxiv|preprints\.org|authorea|figshare|social science research network"


# ---------------------------------------------------------------- scoring (rules from config["crawl"]["scoring"])
class Rules:
    """All regexes are matched against lowercased text (title, or title + " " + abstract).

    scoring:
      exclude       text matches -> 0
      require       text must match, else 0 (e.g. "is this security at all")
      title_reject  title matches -> 0 (e.g. dataset / software-release records)
      groups        [{name, regex, title: w1, text: w2, required: bool}]: +w1 if the title matches, +w2 if the text
                    matches (the title is part of the text, so a title hit earns both); required groups must match the text
      vetoes        [{title: R, unless_text: R}]: title matches R and the text does not match unless_text -> 0
      penalties     [{regex, title: w1, text: w2, unless_group_in_title: name}]: add w1 if the title matches, else w2 if
                    the text matches; skipped when the named group matched the title
      no_abstract   added when the candidate has no abstract (titles alone are weaker evidence)
      min_score     candidates scoring at least this go to the inbox
    auto_ingest (optional):
      category, min_score, require_abstract (default true), formal_only (default true: arXiv, or a journal article /
      book chapter not hosted on a repository such as Zenodo/SSRN), repository (regex), title_require [R, ...] (all must
      match the title), title_exclude R
    """

    def __init__(self, crawl_cfg):
        s = crawl_cfg.get("scoring") or {}
        c = lambda r: re.compile(r) if r else None
        self.exclude, self.require, self.title_reject = c(s.get("exclude")), c(s.get("require")), c(s.get("title_reject"))
        self.groups = [{**g, "re": re.compile(g["regex"])} for g in s.get("groups", [])]
        self.vetoes = [{"title": re.compile(v["title"]), "unless": c(v.get("unless_text"))} for v in s.get("vetoes", [])]
        self.penalties = [{**p, "re": re.compile(p["regex"])} for p in s.get("penalties", [])]
        self.no_abstract = s.get("no_abstract", 0)
        self.min_score = s.get("min_score", 4)
        a = crawl_cfg.get("auto_ingest") or None
        self.auto = a
        if a:
            self.auto_req = [re.compile(r) for r in a.get("title_require", [])]
            self.auto_excl = c(a.get("title_exclude"))
            self.repository = re.compile(a.get("repository", DEFAULT_REPOSITORY))

    def score(self, p):
        title = p["title"].lower()
        text = (p["title"] + " " + (p.get("abstract") or "")).lower()
        if (self.exclude and self.exclude.search(text)) or (self.require and not self.require.search(text)):
            return 0
        if self.title_reject and self.title_reject.search(title):
            return 0
        hit_t, hit_a = {}, {}
        for g in self.groups:
            hit_t[g["name"]] = bool(g["re"].search(title))
            hit_a[g["name"]] = bool(g["re"].search(text))
        if any(g.get("required") and not hit_a[g["name"]] for g in self.groups):
            return 0
        for v in self.vetoes:
            if v["title"].search(title) and not (v["unless"] and v["unless"].search(text)):
                return 0
        s = sum(g.get("title", 0) * hit_t[g["name"]] + g.get("text", 0) * hit_a[g["name"]] for g in self.groups)
        for pen in self.penalties:
            if pen.get("unless_group_in_title") and hit_t.get(pen["unless_group_in_title"]):
                continue
            if pen["re"].search(title):
                s += pen.get("title", 0)
            elif pen["re"].search(text):
                s += pen.get("text", 0)
        if not p.get("abstract"):
            s += self.no_abstract
        return s

    def auto_ok(self, p):
        a = self.auto
        if not a:
            return False
        t = p["title"].lower()
        formal = bool(p.get("arxiv")) or (p.get("type") in ("article", "book-chapter")
                                          and not self.repository.search((p.get("venue") or "").lower()))
        return (p["score"] >= a.get("min_score", self.min_score + 2)
                and (bool(p.get("abstract")) or not a.get("require_abstract", True))
                and (formal or not a.get("formal_only", True))
                and all(r.search(t) for r in self.auto_req)
                and not (self.auto_excl and self.auto_excl.search(t)))


# ---------------------------------------------------------------- de-duplication
def existing(cfg):
    ids, titles = set(), set()
    for base in (cfg["papers"], cfg["archive"]):
        for _, f in walk_pdfs(base):
            m = re.match(r"(\d{4}\.\d{4,5})_", f)
            if m and base == cfg["papers"]: ids.add(m.group(1))
            titles.add(norm_title(title_from_file(f)))
    return ids, titles


def near_dup(t, pool, ratio=0.85):
    t = norm_title(t)
    if not t:
        return None
    for o in pool:
        if o and abs(len(o) - len(t)) < 30 and difflib.SequenceMatcher(None, t, o).ratio() >= ratio:
            return o
    return None


def openalex_anchor_ids(cfg, anchors):
    cache_path = cfg.state("openalex_anchors.json")
    cache = load_json(cache_path, {})
    for a in anchors:
        if a in cache:
            continue
        try:
            if ARXIV_ID.match(a):
                w = oa_get(f"works/doi:10.48550/arxiv.{a}", {"select": "id"})
            else:
                r = oa_get("works", {"filter": "title.search:" + re.sub(r"[,:|]", " ", a), "per-page": 1, "select": "id,title"})["results"]
                w = r[0] if r and norm_title(r[0]["title"]) == norm_title(a) else None
            cache[a] = w["id"].rsplit("/", 1)[-1] if w else None
            if not w:
                print(f"[warn] anchor not indexed in OpenAlex: {a}", file=sys.stderr)
        except Exception as ex:
            print(f"[warn] OpenAlex anchor resolve failed: {a}: {ex}", file=sys.stderr)
        time.sleep(0.5)
    save_json(cache_path, cache)
    return {k: v for k, v in cache.items() if v}


# ---------------------------------------------------------------- eval (no network)
def evaluate(cfg, rules):
    """Score what the user already decided: papers in the collection should pass, archived ones mostly should not."""
    graph = load_json(os.path.join(cfg["lineage"], "graph.json"), {"nodes": []})
    abstracts = load_json(cfg.state("abstracts.json"), {})
    by_title = {norm_title(n.get("title")): n for n in graph.get("nodes", [])}
    by_title.update({norm_title(v.get("title")): v for v in abstracts.values() if v.get("title")})

    def records(base):
        out = []
        for root, f in walk_pdfs(base):
            if os.path.commonpath([root, cfg["inbox"]]) == cfg["inbox"]:
                continue
            t = title_from_file(f)
            m = re.match(r"(\d{4}\.\d{4,5})_", f)
            src = by_title.get(norm_title(t)) or {}
            p = {"id": m.group(1) if m else t, "title": src.get("title") or t, "abstract": src.get("abstract") or "",
                 "arxiv": m.group(1) if m else None, "venue": src.get("venue") or "", "type": src.get("type") or "article"}
            p["score"] = rules.score(p)
            p["auto"] = rules.auto_ok(p)
            out.append(p)
        return out

    keep, arch = records(cfg["papers"]), records(cfg["archive"])
    rec = [p for p in keep if p["score"] >= rules.min_score]
    fp = [p for p in arch if p["score"] >= rules.min_score]
    print(f"collection: {len(rec)}/{len(keep)} would reach the inbox (min_score {rules.min_score}); "
          f"{sum(p['auto'] for p in keep)} would be auto-ingested")
    print(f"archive:    {len(fp)}/{len(arch)} would reach the inbox; {sum(p['auto'] for p in arch)} would be auto-ingested (should be 0)")
    print(f"no abstract available offline for {sum(not p['abstract'] for p in keep + arch)} papers (scored on title only)")
    print("\nmissed papers in the collection:")
    for p in sorted(keep, key=lambda p: p["score"]):
        if p["score"] < rules.min_score: print(f"  [{p['score']}] {p['title'][:100]}")
    print("\narchived papers that would come back:")
    for p in sorted(fp, key=lambda p: -p["score"]):
        print(f"  [{p['score']}]{' AUTO' if p['auto'] else ''} {p['title'][:100]}")


# ---------------------------------------------------------------- bootstrap
def bootstrap_report(cfg, picked, fresh, today, seen, seen_path, rules, T):
    """List candidates for building a collection; nothing is downloaded. Candidates are recorded in seen.json so daily
    tracking will not offer them again — the ones the user approves are added with add_papers.py."""
    d = os.path.join(cfg["inbox"], f"bootstrap-{today}")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "candidates.tsv"), "w", encoding="utf-8") as f:
        f.write("score\tid\tpublished\tvenue\ttitle\tvia\tlink\n")
        for p in picked:
            cells = [p["score"], p["id"], p["published"], p.get("venue") or ("arXiv" if p.get("arxiv") else ""),
                     p["title"], p["via"], link_of(p)]
            f.write("\t".join(str(c).replace("\t", " ").replace("\n", " ") for c in cells) + "\n")
    rep = [f"# Bootstrap candidates {today}", "",
           f"{len(picked)} candidates scored >= {rules.min_score} (of {len(fresh)} unseen). Review them against the scope; "
           "approved ones go into a list file (`<category>|<id>` per line) for add_papers.py.", ""]
    for p in picked:
        rep += [f"## [{p['score']}] {p['title']}",
                f"- id `{p['id']}` | {p['published']} | {p.get('venue') or ('arXiv' if p.get('arxiv') else '')} | {link_of(p)}",
                f"- {T['via']}: {p['via']}",
                f"- {T['abs']}: {(p.get('abstract') or T['noabs'])[:500]}", ""]
    open(os.path.join(d, "REPORT.md"), "w", encoding="utf-8").write("\n".join(rep))
    for p in fresh:
        if p["score"] >= rules.min_score:
            seen[p["id"]] = {"date": today, "title": p["title"], "score": p["score"], "kept": True, "bootstrap": True,
                             "source": "arxiv" if p.get("arxiv") else "openalex"}
    save_json(seen_path, seen)
    print(f"bootstrap: {len(picked)} candidates -> {cfg.rel(d)}/candidates.tsv (nothing downloaded)")


# ---------------------------------------------------------------- main
TEXT = {
    "zh": {"head": "# 新论文审核报告 {d}", "intro": "共 {n} 篇候选(已下载到本目录)。确认相关后移入 papers/ 对应分类;不相关的移到 archive/(已记入 seen.json,不会再次抓取)。",
           "auto": "另有 {n} 篇满足严格规则，已直接入库 papers/{c}/(见 auto_ingested.csv,每周复核)。",
           "link": "链接", "pub": "发布", "via": "来源", "abs": "摘要", "noabs": "(无摘要，仅凭标题入选，请重点核对)"},
    "en": {"head": "# New papers to review {d}", "intro": "{n} candidates (downloaded here). Move relevant ones into a papers/ category and the rest to archive/ (already in seen.json, they will not be fetched again).",
           "auto": "{n} more passed the strict rules and were added to papers/{c}/ directly (see auto_ingested.csv; reviewed weekly).",
           "link": "Link", "pub": "published", "via": "Found via", "abs": "Abstract", "noabs": "(no abstract — selected on the title alone, check carefully)"},
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    config_arg(ap)
    ap.add_argument("--days", type=int, default=None, help="only papers published in the last N days (anchor citations are not limited)")
    ap.add_argument("--max-per-query", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--eval", action="store_true", help="score the current collection and archive offline")
    ap.add_argument("--mark-seen", action="store_true", help="record current candidates in seen.json without downloading")
    ap.add_argument("--sources", default=None, help="comma-separated: arxiv,s2,openalex")
    ap.add_argument("--auto-ingest", action="store_true")
    ap.add_argument("--bootstrap", action="store_true", help="build a collection: no recency limit, references too, list only")
    ap.add_argument("--since", type=int, default=2000, help="--bootstrap: earliest publication year")
    a = ap.parse_args()
    cfg = Config(a.config)
    C = cfg.get("crawl") or {}
    rules = Rules(C)
    if a.eval:
        return evaluate(cfg, rules)
    days = a.days or C.get("days", 14)
    per_q = a.max_per_query or (100 if a.bootstrap else C.get("max_per_query", 50))
    sources = set((a.sources or ",".join(C.get("sources", ["arxiv", "s2", "openalex"]))).split(","))
    anchors, anchor_titles = C.get("anchors", []), C.get("anchor_titles", [])
    T = TEXT.get(cfg.lang, TEXT["en"])
    auto_cat = (rules.auto or {}).get("category")

    today = dt.date.today().isoformat()
    cutoff = f"{a.since}-01-01" if a.bootstrap else (dt.date.today() - dt.timedelta(days=days)).isoformat()
    sort_ax = "relevance" if a.bootstrap else "submittedDate"
    seen_path = cfg.state("seen.json")
    have, have_titles = existing(cfg)
    seen = load_json(seen_path, {})
    seen_titles = {norm_title(v.get("title")) for v in seen.values()}
    cands, cand_titles = {}, set()

    def add(p):
        t = norm_title(p["title"])
        if p["id"] in cands or t in cand_titles:
            return
        cands[p["id"]] = p; cand_titles.add(t)

    if "arxiv" in sources:
        for q in C.get("arxiv_queries", []):
            try:
                for p in arxiv_search(q, per_q, sort_ax):
                    if p["published"] >= cutoff:
                        p["arxiv"] = p["id"]; add(p)
            except Exception as ex:
                print(f"[warn] query failed: {q}: {ex}", file=sys.stderr)
            time.sleep(3)
    if "s2" in sources:
        cited = set()
        for anc in anchors:
            cited.update(x for x in s2_citing(anc) if x)
            time.sleep(4)
        new_cited = [x for x in cited if x not in have and x not in seen and x not in cands]
        for p in arxiv_lookup(new_cited):
            p["via"] = "cites anchor paper (Semantic Scholar)"; p["arxiv"] = p["id"]; add(p)
    if "openalex" in sources:
        n0 = len(cands)
        for q in C.get("openalex_queries", []):
            try:
                params = {"filter": f"title_and_abstract.search:{q},from_publication_date:{cutoff}",
                          "per-page": min(200, per_q), "select": OA_SELECT}
                if not a.bootstrap:
                    params["sort"] = "publication_date:desc"  # otherwise OpenAlex ranks by relevance
                d = oa_get("works", params)
                for w in d.get("results", []):
                    c = oa_to_cand(w, "openalex: " + q)
                    if c: add(c)
            except Exception as ex:
                print(f"[warn] OpenAlex query failed: {q}: {ex}", file=sys.stderr)
            time.sleep(0.5)
        for anc, wid in openalex_anchor_ids(cfg, anchors + anchor_titles).items():
            try:
                d = oa_get("works", {"filter": f"cites:{wid}", "sort": "publication_date:desc", "per-page": 100, "select": OA_SELECT})
                for w in d.get("results", []):
                    c = oa_to_cand(w, f"cites anchor (OpenAlex {wid})")
                    if c: add(c)
            except Exception as ex:
                print(f"[warn] OpenAlex citations failed for {wid}: {ex}", file=sys.stderr)
            time.sleep(0.5)
            if a.bootstrap:  # backward snowballing: what the anchors build on
                try:
                    refs = oa_get(f"works/{wid}", {"select": "referenced_works"}).get("referenced_works") or []
                    for c in oa_works_by_ids([r.rsplit("/", 1)[-1] for r in refs], f"cited by anchor (OpenAlex {wid})"):
                        add(c)
                except Exception as ex:
                    print(f"[warn] OpenAlex references failed for {wid}: {ex}", file=sys.stderr)
        print(f"openalex: +{len(cands) - n0} candidates", file=sys.stderr)

    fresh = [p for i, p in cands.items() if i not in have and i not in seen
             and norm_title(p["title"]) not in have_titles and norm_title(p["title"]) not in seen_titles]
    pool = list(have_titles)
    for p in fresh:
        d = near_dup(p["title"], pool)
        if d: p["dup_of"] = d
        else: pool.append(norm_title(p["title"]))
    picked = []
    for p in fresh:
        p["score"] = 0 if p.get("dup_of") else rules.score(p)
        if p["score"] >= rules.min_score: picked.append(p)
    for p in picked:
        p["auto"] = a.auto_ingest and rules.auto_ok(p)
    picked.sort(key=lambda p: (-p["score"], p["published"]))
    if a.bootstrap:
        return bootstrap_report(cfg, picked, fresh, today, seen, seen_path, rules, T)

    ndup = sum(1 for p in fresh if p.get("dup_of"))
    print(f"{today}: {len(cands)} candidates, {len(fresh)} unseen ({ndup} near-duplicates of existing papers), {len(picked)} relevant")
    if a.dry_run:
        for p in fresh:
            if p.get("dup_of"): print(f"  [dup] {p['title'][:70]}  ~ {p['dup_of'][:50]}")
        for p in picked:
            tag = "" if p.get("arxiv") else f"  [non-arXiv · {p.get('venue') or p.get('type') or '?'}]"
            print(f"  [{p['score']}]{' AUTO' if p.get('auto') else ''} {p['id']} {p['title']}{tag}")
        return

    day_dir = os.path.join(cfg["inbox"], today)
    rows = []
    for p in ([] if a.mark_seen else picked):
        dest = os.path.join(cfg["papers"], auto_cat) if p.get("auto") else day_dir
        os.makedirs(dest, exist_ok=True)
        name = f"{p['arxiv']}_{sanitize(p['title'])}.pdf" if p.get("arxiv") else f"{sanitize(p['title'])}.pdf"
        path = os.path.join(dest, name)
        p["file"] = name
        ok = download(p, path)
        if not ok:
            open(path, "w").close()
        p["status"] = "downloaded" if ok else "PLACEHOLDER"
        rows.append(p)
        time.sleep(2)

    for p in fresh:
        seen[p["id"]] = {"date": today, "title": p["title"], "score": p["score"],
                         "kept": p["score"] >= rules.min_score, "source": "arxiv" if p.get("arxiv") else "openalex"}
        if p.get("dup_of"): seen[p["id"]]["dup_of"] = p["dup_of"]
        if p.get("auto"): seen[p["id"]]["auto"] = True
    auto = [p for p in rows if p.get("auto")]
    if auto:
        abs_path = cfg.state("abstracts.json")
        abstracts = load_json(abs_path, {})
        for p in auto:
            key = p["arxiv"] or (f"doi:{p['doi']}" if p.get("doi") else f"openalex:{p.get('openalex')}")
            abstracts[key] = {"cat": auto_cat, "title": p["title"], "abstract": p["abstract"], "published": p["published"],
                              "venue": p.get("venue") or "", "doi": p.get("doi") or "", "openalex": p.get("openalex") or "",
                              "file": p["file"], "downloaded": p["status"] == "downloaded", "auto": today}
        save_json(abs_path, abstracts)
        log = cfg.state("auto_ingested.csv")
        new_log = not os.path.exists(log)
        with open(log, "a", encoding="utf-8") as f:
            if new_log: f.write("date,id,score,status,file,title,reviewed\n")
            for p in auto:
                f.write(f"{today},{p['id']},{p['score']},{p['status']},\"{p['file'].replace(chr(34), '')}\",\"{p['title'].replace(chr(34), '')}\",\n")
    save_json(seen_path, seen)

    inbox = [p for p in rows if not p.get("auto")]
    if auto:
        print(f"auto-ingested {len(auto)} -> papers/{auto_cat}/: " + "; ".join(p["title"][:60] for p in auto))
    if inbox:
        rep = [T["head"].format(d=today), "", T["intro"].format(n=len(inbox)), ""]
        if auto:
            rep += [T["auto"].format(n=len(auto), c=auto_cat), ""]
        for p in inbox:
            rep += [f"## [{p['score']}] {p['title']}",
                    f"- {T['link']}: {link_of(p)} | {T['pub']} {p['published']} | {p.get('venue') or ('arXiv' if p.get('arxiv') else '')} | {p['status']}",
                    f"- {T['via']}: {p['via']}",
                    f"- {T['abs']}: {(p['abstract'] or T['noabs'])[:600]}", ""]
        open(os.path.join(day_dir, "REPORT.md"), "w", encoding="utf-8").write("\n".join(rep))
        with open(os.path.join(cfg["inbox"], "inbox_log.csv"), "a", encoding="utf-8") as f:
            for p in inbox:
                f.write(f"{today},{p['id']},{p['score']},{p['status']},\"{p['title'].replace(chr(34), '')}\"\n")
    print(f"done: {len(inbox)} new papers -> {cfg.rel(day_dir) if inbox else '(inbox: none)'}; auto-ingested {len(auto)}")


if __name__ == "__main__":
    main()
