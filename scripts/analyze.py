#!/usr/bin/env python3
"""Analyze a collected paper set: citation graph, lineage, roles, directions, gaps.

Input : <out>/papers.json  (from collect.py)
Output: <out>/graph.json   (data for render.py)
        <out>/analysis.md  (compact digest for Claude to read before writing the narrative)

Usage: python3 -I analyze.py --out DIR [--cluster] [--labels labels.json] [--order a,b,c]
"""
import argparse, collections, datetime as dt, json, math, os, re, statistics

TODAY = dt.date.today()


def load(out):
    return json.load(open(os.path.join(out, "papers.json"), encoding="utf-8"))


def default_label(name):
    return re.sub(r"^\d+[-_ ]*", "", name).replace("-", " ").replace("_", " ").strip() or name


def ext_key(r):
    return r.get("arxiv_id") or ("s2:" + r["s2_id"] if r.get("s2_id") else None)


def pagerank(nodes, out_edges, d=0.85, it=60):
    n = len(nodes)
    pr = {k: 1 / n for k in nodes}
    for _ in range(it):
        nxt = {k: (1 - d) / n for k in nodes}
        sink = sum(pr[k] for k in nodes if not out_edges[k])
        for k in nodes:
            if out_edges[k]:
                share = d * pr[k] / len(out_edges[k])
                for t in out_edges[k]:
                    nxt[t] += share
        for k in nodes:
            nxt[k] += d * sink / n
        pr = nxt
    return pr


def betweenness(nodes, adj):
    """Brandes, undirected, unweighted; normalized to [0,1]."""
    bc = dict.fromkeys(nodes, 0.0)
    for s in nodes:
        stack, pred = [], {v: [] for v in nodes}
        sigma = dict.fromkeys(nodes, 0); sigma[s] = 1
        dist = dict.fromkeys(nodes, -1); dist[s] = 0
        q = collections.deque([s])
        while q:
            v = q.popleft(); stack.append(v)
            for w in adj[v]:
                if dist[w] < 0:
                    dist[w] = dist[v] + 1; q.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]; pred[w].append(v)
        delta = dict.fromkeys(nodes, 0.0)
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                bc[w] += delta[w]
    n = len(nodes)
    norm = (n - 1) * (n - 2) if n > 2 else 1
    return {k: v / norm for k, v in bc.items()}


def label_propagation(nodes, weights, rounds=30):
    lab = {k: k for k in nodes}
    for _ in range(rounds):
        changed = False
        for v in sorted(nodes):
            score = collections.Counter()
            for u, w in weights[v].items():
                score[lab[u]] += w
            if not score:
                continue
            best = max(score.items(), key=lambda x: (x[1], x[0]))[0]  # stable tie-break
            if best != lab[v]:
                lab[v] = best; changed = True
        if not changed:
            break
    return lab


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--cluster", action="store_true", help="derive directions from the graph instead of folder categories")
    ap.add_argument("--labels", help='JSON {"category-name": "display label"}')
    ap.add_argument("--order", help="comma-separated category order (first three get the three colors)")
    ap.add_argument("--min-hub", type=int, default=2, help="min collection papers citing an outside paper to list it")
    a = ap.parse_args()

    doc = load(a.out)
    papers = doc["papers"]
    P = {p["key"]: p for p in papers}
    keys = list(P)
    alias = {}
    for p in papers:
        alias[p["key"]] = p["key"]
        if p.get("arxiv_id"): alias[p["arxiv_id"]] = p["key"]
        if p.get("s2_id"): alias[p["s2_id"]] = p["key"]
        if p.get("openalex"): alias["oa:" + p["openalex"]] = p["key"]

    def resolve(r):
        return (alias.get(r.get("s2_id")) or alias.get(r.get("arxiv_id"))
                or (alias.get("oa:" + r["openalex"]) if r.get("openalex") else None))

    # ---- internal edges (citing -> cited); merge evidence from both sides' lists
    edges = set()
    hubs, frontier = collections.defaultdict(lambda: {"by": set(), "title": None, "year": None}), \
                     collections.defaultdict(lambda: {"of": set(), "title": None, "year": None})
    for p in papers:
        for r in p["refs"]:
            k = resolve(r)
            if k and k != p["key"]:
                edges.add((p["key"], k))
            elif not k and ext_key(r):
                h = hubs[ext_key(r)]; h["by"].add(p["key"]); h["title"] = h["title"] or r.get("title"); h["year"] = h["year"] or r.get("year")
        for c in p["cites"]:
            k = resolve(c)
            if k and k != p["key"]:
                edges.add((k, p["key"]))
            elif not k and ext_key(c):
                f = frontier[ext_key(c)]; f["of"].add(p["key"]); f["title"] = f["title"] or c.get("title"); f["year"] = f["year"] or c.get("year")
    out_e = collections.defaultdict(set); in_e = collections.defaultdict(set); adj = collections.defaultdict(set)
    for s, t in edges:
        out_e[s].add(t); in_e[t].add(s); adj[s].add(t); adj[t].add(s)
    for k in keys:
        out_e[k]; in_e[k]; adj[k]

    # ---- directions: folder categories, or graph clusters
    cat_source = "folders"
    cats = {k: P[k].get("category") or "uncategorized" for k in keys}
    if a.cluster or len(set(cats.values())) == 1:
        cat_source = "clusters"
        refsets = {k: {ext_key(r) or resolve(r) for r in P[k]["refs"]} - {None} for k in keys}
        w = {k: collections.Counter() for k in keys}
        for s, t in edges:
            w[s][t] += 3; w[t][s] += 3
        for i, u in enumerate(keys):
            for v in keys[i + 1:]:
                shared = len(refsets[u] & refsets[v])
                if shared >= 2:
                    w[u][v] += shared; w[v][u] += shared
        lab = label_propagation(keys, w)
        sizes = collections.Counter(lab.values())
        rank = {l: i for i, (l, n) in enumerate(sizes.most_common()) if n >= 3}
        cats = {k: (f"cluster-{rank[lab[k]] + 1}" if lab[k] in rank else "other") for k in keys}

    labels = json.load(open(a.labels, encoding="utf-8")) if a.labels else {}
    order = [c.strip() for c in a.order.split(",")] if a.order else []
    names = sorted(set(cats.values()), key=lambda c: (order.index(c) if c in order else len(order), c == "other", c))

    # ---- metrics
    pr = pagerank(keys, out_e)
    bc = betweenness(keys, adj)
    def year_of(k):
        p = P[k]; return p.get("year") or (int(p["published"][:4]) if p.get("published") else None)
    def date_of(k):
        p = P[k]; return p.get("published") or (f"{year_of(k)}-01-01" if year_of(k) else "")
    def cpy(k):
        y, c = year_of(k), P[k].get("citationCount") or 0
        return round(c / max(1, TODAY.year - y + 1), 2) if y else 0

    max_date = max((date_of(k) for k in keys if date_of(k)), default="")
    li = {k: len(in_e[k]) for k in keys}
    lo = {k: len(out_e[k]) for k in keys}
    roles = {k: [] for k in keys}
    found = sorted([k for k in keys if li[k] > 0], key=lambda k: (-pr[k], -li[k]))[:12]
    for k in found: roles[k].append("foundational")
    bridges = sorted([k for k in keys if bc[k] > 0 and len({cats[n] for n in adj[k]} | {cats[k]}) >= 2],
                     key=lambda k: -bc[k])[:10]
    for k in bridges: roles[k].append("bridge")
    recent_cut = (dt.date.fromisoformat(max_date) - dt.timedelta(days=365)).isoformat() if max_date else ""
    front = sorted([k for k in keys if date_of(k) >= recent_cut], key=lambda k: (-(lo[k] + li[k]), -cpy(k)))[:12]
    for k in front: roles[k].append("frontier")
    isolated = [k for k in keys if not adj[k]]
    for k in isolated: roles[k].append("isolated")

    # ---- longest lineage chains (time-respecting DAG: cited no later than citing)
    order_k = sorted(keys, key=lambda k: (date_of(k), k))
    best, nxt = {}, {}
    for k in order_k:
        cands = [t for t in out_e[k] if date_of(t) <= date_of(k) and t in best]
        if cands:
            t = max(cands, key=lambda t: (best[t], pr[t]))
            best[k], nxt[k] = best[t] + 1, t
        else:
            best[k] = 1
    chains, used = [], set()
    for k in sorted(keys, key=lambda k: -best[k]):
        if best[k] < 3 or k in used or len(chains) >= 6:
            continue
        ch = [k]
        while ch[-1] in nxt:
            ch.append(nxt[ch[-1]])
        if len(set(ch) & used) > len(ch) // 2:
            continue
        used |= set(ch); chains.append(list(reversed(ch)))   # oldest -> newest

    # ---- per-direction stats + cross-direction flow
    cstats = []
    flow = collections.Counter((cats[s], cats[t]) for s, t in edges)
    for i, c in enumerate(names):
        mem = [k for k in keys if cats[k] == c]
        ys = collections.Counter(year_of(k) for k in mem if year_of(k))
        dates = sorted(date_of(k) for k in mem if date_of(k))
        internal = sum(1 for s, t in edges if cats[s] == c and cats[t] == c)
        cstats.append({"name": c, "label": labels.get(c) or default_label(c), "slot": i + 1 if i < 3 else 0,
                       "n": len(mem), "years": dict(sorted(ys.items())), "first": dates[0] if dates else "",
                       "last": dates[-1] if dates else "", "internal_edges": internal,
                       "median_citations": statistics.median([P[k].get("citationCount") or 0 for k in mem]) if mem else 0})

    # ---- gaps
    # each gap carries structured fields so render.py can phrase it in the page language;
    # "detail" is the English fallback used in analysis.md
    gaps = []
    for cs in cstats:
        if cs["n"] < 3:
            gaps.append({"type": "thin_direction", "a": cs["label"], "n": cs["n"],
                         "detail": f"{cs['label']}: only {cs['n']} paper(s)"})
        if cs["last"] and recent_cut and cs["last"] < recent_cut:
            gaps.append({"type": "cooling_direction", "a": cs["label"], "last": cs["last"],
                         "detail": f"{cs['label']}: newest paper {cs['last']} (nothing in the last 12 months of the collection)"})
    big = [cs for cs in cstats if cs["n"] >= 3]
    for i, x in enumerate(big):
        for y in big[i + 1:]:
            ab, ba = flow[(x["name"], y["name"])], flow[(y["name"], x["name"])]
            pair = {"a": x["label"], "b": y["label"], "na": x["n"], "nb": y["n"], "ab": ab, "ba": ba}
            if ab + ba == 0:
                gaps.append({"type": "disconnected_pair", **pair,
                             "detail": f"no citation links between {x['label']} and {y['label']}"})
            elif (ab + ba) / min(x["n"], y["n"]) < 0.15:
                gaps.append({"type": "weakly_connected_pair", **pair,
                             "detail": f"{x['label']} ({x['n']}) and {y['label']} ({y['n']}) barely cite each other: "
                                       f"{ab} links one way, {ba} the other — likely separate communities"})
    if isolated:
        gaps.append({"type": "isolated_papers", "n": len(isolated), "total": len(keys),
                     "detail": f"{len(isolated)}/{len(keys)} papers have no citation link to the rest of the collection"})
    missing = [k for k in keys if not (P[k].get("s2_ok") or P[k].get("oa_ok"))]
    if missing:
        gaps.append({"type": "data_quality", "n": len(missing),
                     "detail": f"{len(missing)} papers lack citation data; their links are undercounted"})

    hub_list = sorted(({"key": k, "title": v["title"], "year": v["year"], "count": len(v["by"]),
                        "directions": sorted({cats[b] for b in v["by"]}), "cited_by": sorted(v["by"])}
                       for k, v in hubs.items() if len(v["by"]) >= a.min_hub),
                      key=lambda h: (-h["count"], -(h["year"] or 0)))[:40]
    front_list = sorted(({"key": k, "title": v["title"], "year": v["year"], "count": len(v["of"]),
                          "directions": sorted({cats[b] for b in v["of"]}), "cites": sorted(v["of"])}
                         for k, v in frontier.items() if len(v["of"]) >= a.min_hub),
                        key=lambda h: (-h["count"], -(h["year"] or 0)))[:40]

    def url(k):
        p = P[k]
        if p.get("arxiv_id"): return f"https://arxiv.org/abs/{p['arxiv_id']}"
        if p.get("s2_id"): return f"https://www.semanticscholar.org/paper/{p['s2_id']}"
        return ""

    nodes = [{"key": k, "title": P[k]["title"], "year": year_of(k), "date": date_of(k), "category": cats[k],
              "citations": P[k].get("citationCount"), "cpy": cpy(k), "local_in": li[k], "local_out": lo[k],
              "pagerank": round(pr[k] * len(keys), 3), "betweenness": round(bc[k], 4), "roles": roles[k],
              "url": url(k), "authors": P[k].get("authors", [])[:4], "venue": P[k].get("venue", ""),
              "abstract": (P[k].get("abstract") or "")[:700], "withdrawn": P[k].get("withdrawn", False)}
             for k in keys]
    graph = {"meta": {"generated": dt.datetime.now().isoformat(timespec="seconds"), "n": len(keys),
                      "edges": len(edges), "category_source": cat_source, "max_date": max_date,
                      "collect_meta": doc.get("meta", {})},
             "nodes": nodes, "edges": sorted(edges), "categories": cstats,
             "flow": [{"from": s, "to": t, "count": n} for (s, t), n in flow.most_common()],
             "chains": chains, "gaps": gaps, "hubs": hub_list, "frontier": front_list}
    json.dump(graph, open(os.path.join(a.out, "graph.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---- digest for Claude
    lab_of = {c["name"]: c["label"] for c in cstats}
    T = lambda k: f"{P[k]['title'][:110]} ({year_of(k)}, {lab_of[cats[k]]})"
    L = [f"# Lineage analysis digest", "",
         f"- papers: {len(keys)} | internal citation links: {len(edges)} | directions from: {cat_source}",
         f"- date range: {min((date_of(k) for k in keys if date_of(k)), default='?')} .. {max_date}",
         f"- citation data: {doc['meta'].get('with_citation_data')}/{len(keys)} papers"
         + ("" if doc["meta"].get("s2_api_key") else " (no S2_API_KEY: rate limits likely)"), ""]
    if doc["meta"].get("warnings"):
        L += ["## Data warnings", ""] + [f"- {w}" for w in doc["meta"]["warnings"][:15]] + [""]
    L += ["## Directions", "", "| direction | papers | first | last | internal links | median citations | per-year |", "|---|---|---|---|---|---|---|"]
    for cs in cstats:
        L.append(f"| {cs['label']} | {cs['n']} | {cs['first']} | {cs['last']} | {cs['internal_edges']} | {cs['median_citations']} | "
                 + ", ".join(f"{y}:{n}" for y, n in cs["years"].items()) + " |")
    yearly = collections.Counter(year_of(k) for k in keys if year_of(k))
    L += ["", "## Papers per year (all)", "", ", ".join(f"{y}: {n}" for y, n in sorted(yearly.items())), ""]
    L += ["## Cross-direction flow (row cites column = row builds on column)", ""]
    L += ["| cites → | " + " | ".join(lab_of[c] for c in names) + " |", "|---" * (len(names) + 1) + "|"]
    for s in names:
        L.append(f"| {lab_of[s]} | " + " | ".join(str(flow[(s, t)]) for t in names) + " |")
    L += ["", "## Foundational (local PageRank; cited inside the collection)", ""]
    L += [f"- [{k}] {T(k)} — cited by {li[k]} in collection, {P[k].get('citationCount')} total" for k in found]
    L += ["", "## Bridges (connect directions; betweenness)", ""]
    L += [f"- [{k}] {T(k)} — betweenness {bc[k]:.3f}, neighbours in {sorted({lab_of[cats[n]] for n in adj[k]})}" for k in bridges]
    L += ["", "## Frontier (last 12 months of the collection)", ""]
    L += [f"- [{k}] {T(k)} — links in/out {li[k]}/{lo[k]}, {cpy(k)} citations/yr" for k in front]
    L += ["", "## Longest lineage chains (oldest → newest; each step cites the previous)", ""]
    for ch in chains:
        L.append("- " + " → ".join(f"[{k}] {P[k]['title'][:60]} ({year_of(k)})" for k in ch))
    L += ["", "## Gaps", ""] + [f"- ({g['type']}) {g['detail']}" for g in gaps]
    L += ["", f"## Outside papers cited by ≥{a.min_hub} collection papers (candidate missing foundations)", ""]
    L += [f"- {h['count']}× {h['title']} ({h['year']}) [{h['key']}] — from {[lab_of[d] for d in h['directions']]}" for h in hub_list[:25]]
    L += ["", f"## Outside papers citing ≥{a.min_hub} collection papers (newer work building on it)", ""]
    L += [f"- {h['count']}× {h['title']} ({h['year']}) [{h['key']}]" for h in front_list[:20]]
    if cat_source == "clusters":
        L += ["", "## Auto clusters — name these from their members", ""]
        for cs in cstats:
            mem = sorted([k for k in keys if cats[k] == cs["name"]], key=lambda k: -pr[k])[:8]
            L += [f"### {cs['name']} ({cs['n']})"] + [f"- {P[k]['title'][:120]}" for k in mem] + [""]
    open(os.path.join(a.out, "analysis.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"wrote graph.json and analysis.md: {len(keys)} nodes, {len(edges)} edges, {len(cstats)} directions")


if __name__ == "__main__":
    main()
