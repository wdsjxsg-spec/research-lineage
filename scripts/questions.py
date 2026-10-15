#!/usr/bin/env python3
"""Question lineage: organise the collection by the research questions papers put forward.

  prepare  write <out>/questions_todo.md — compact title/abstract/note list for Claude to read
  build    validate <out>/questions.json (written by Claude) and add a question graph to
           <out>/graph.json plus a digest <out>/questions_digest.md

Usage: python3 -I questions.py prepare --out DIR [--notes FILE]
       python3 -I questions.py build   --out DIR
Schema of questions.json: see references/questions.md
"""
import argparse, collections, datetime as dt, json, os, re, sys

STANCES = ["proposes", "extends", "evaluates", "challenges", "reframes", "surveys"]


def load_graph(out):
    return json.load(open(os.path.join(out, "graph.json"), encoding="utf-8"))


def load_notes(path):
    if not path:
        return {}
    notes = {}
    for line in open(path, encoding="utf-8"):
        m = re.search(r"(\d{4}\.\d{4,5})", line)
        if m and line.lstrip().startswith(("-", "*")):
            notes[m.group(1)] = re.sub(r"[*`]", "", line.split("—", 1)[-1]).strip()
    return notes


def prepare(a):
    g = load_graph(a.out)
    notes = load_notes(a.notes)
    labels = {c["name"]: c["label"] for c in g["categories"]}
    by_cat = collections.defaultdict(list)
    for n in g["nodes"]:
        by_cat[n["category"]].append(n)
    L = ["# Papers to map to research questions", "",
         f"{len(g['nodes'])} papers. For each: what question does it put forward? See references/questions.md.", ""]
    for c in g["categories"]:
        L += [f"## {labels[c['name']]}", ""]
        for n in sorted(by_cat[c["name"]], key=lambda n: n["date"] or ""):
            L.append(f"### [{n['key']}] {n['title']} ({n['year']})")
            if notes.get(n["key"]):
                L.append(f"- note: {notes[n['key']]}")
            if n.get("abstract"):
                L.append(f"- abstract: {n['abstract'][:600]}")
            L.append("")
    path = os.path.join(a.out, "questions_todo.md")
    open(path, "w", encoding="utf-8").write("\n".join(L))
    print(f"wrote {path} ({len(g['nodes'])} papers)")


def build(a):
    g = load_graph(a.out)
    qdoc = json.load(open(os.path.join(a.out, "questions.json"), encoding="utf-8"))
    nodes = {n["key"]: n for n in g["nodes"]}
    Q = {q["id"]: q for q in qdoc["questions"]}
    papers = qdoc["papers"]

    # ---- validation: fail loudly, a silently wrong map is worse than none
    errs = []
    for qid, q in Q.items():
        if q.get("parent") and q["parent"] not in Q:
            errs.append(f"question {qid}: unknown parent {q['parent']}")
    gone = [k for k in papers if k not in nodes]
    if gone:  # paper removed from the collection: keep its label in questions.json, just leave it out of the graph
        print(f"[warn] ignoring {len(gone)} labels for papers no longer in the collection: {gone[:5]}", file=sys.stderr)
        papers = {k: v for k, v in papers.items() if k in nodes}
    for k, p in papers.items():
        if p.get("q") not in Q:
            errs.append(f"paper {k}: unknown question id {p.get('q')}")
        if p.get("stance") not in STANCES:
            errs.append(f"paper {k}: stance must be one of {STANCES}, got {p.get('stance')}")
    missing = [k for k in nodes if k not in papers]
    if errs:
        sys.exit("questions.json invalid:\n  " + "\n  ".join(errs[:40]))
    if missing:
        print(f"[warn] {len(missing)} papers have no question yet: {missing[:10]}", file=sys.stderr)

    max_date = g["meta"].get("max_date") or max(n["date"] for n in nodes.values() if n["date"])
    last12 = (dt.date.fromisoformat(max_date) - dt.timedelta(days=365)).isoformat()
    last18 = (dt.date.fromisoformat(max_date) - dt.timedelta(days=548)).isoformat()
    qof = {k: p["q"] for k, p in papers.items()}

    # roll paper questions up the tree so parents summarise their sub-questions
    def ancestors(qid):
        out = []
        while Q[qid].get("parent"):
            qid = Q[qid]["parent"]; out.append(qid)
        return out

    members = collections.defaultdict(list)
    for k, qid in qof.items():
        members[qid].append(k)
    sub = collections.defaultdict(list)
    for k, qid in qof.items():
        for anc in [qid] + ancestors(qid):
            sub[anc].append(k)

    flow = collections.Counter()
    challenge = collections.Counter()
    internal = collections.Counter()
    for s, t in g["edges"]:
        qs, qt = qof.get(s), qof.get(t)
        if not qs or not qt:
            continue
        if qs == qt:
            internal[qs] += 1
        else:
            flow[(qs, qt)] += 1
            if papers[s]["stance"] == "challenges":
                challenge[(qs, qt)] += 1

    date = lambda k: nodes[k]["date"] or ""
    out_q = []
    for qid, q in Q.items():
        own = sorted(members.get(qid, []), key=date)
        allp = sorted(set(sub.get(qid, [])), key=date)
        stances = collections.Counter(papers[k]["stance"] for k in own)
        first = date(allp[0]) if allp else ""
        last = date(allp[-1]) if allp else ""
        momentum = sum(1 for k in allp if date(k) >= last12)
        status = []
        if first and first >= last12: status.append("emerging")
        if momentum >= 3: status.append("active")
        if last and last < last18: status.append("dormant")
        if stances.get("challenges"): status.append("contested")
        builds_on = sorted(((t, n) for (s, t), n in flow.items() if s == qid), key=lambda x: -x[1])
        led_to = sorted(((s, n) for (s, t), n in flow.items() if t == qid), key=lambda x: -x[1])
        # seeds: papers of this question that no other paper of the same question precedes via citation
        own_set = set(own)
        seeds = [k for k in own if not any(t in own_set for s, t in g["edges"] if s == k)]
        out_q.append({"id": qid, "parent": q.get("parent"), "text": q["text"], "short": q.get("short") or q["text"][:40],
                      "papers": own, "all_papers": allp, "n": len(own), "n_all": len(allp),
                      "first": first, "last": last, "momentum": momentum, "status": status,
                      "stances": dict(stances), "internal_edges": internal[qid],
                      "builds_on": [{"q": t, "count": n} for t, n in builds_on],
                      "led_to": [{"q": s, "count": n} for s, n in led_to],
                      "seeds": seeds[:5]})
    # tree order: depth-first by first appearance
    kids = collections.defaultdict(list)
    for q in out_q:
        kids[q["parent"]].append(q)
    order = []
    def walk(parent, depth):
        for q in sorted(kids[parent], key=lambda q: (q["first"] or "9999", q["id"])):
            q["depth"] = depth; order.append(q); walk(q["id"], depth + 1)
    walk(None, 0)

    g["questions"] = {"list": order,
                      "papers": papers,
                      "flow": [{"from": s, "to": t, "count": n, "challenges": challenge[(s, t)]} for (s, t), n in flow.most_common()]}
    json.dump(g, open(os.path.join(a.out, "graph.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    T = lambda k: f"{nodes[k]['title'][:80]} ({nodes[k]['year']})"
    L = ["# Question lineage digest", "",
         f"- {len(Q)} questions, {len(papers)}/{len(nodes)} papers mapped, {sum(flow.values())} cross-question citation links", ""]
    for q in order:
        pad = "  " * q["depth"]
        L.append(f"{pad}- **{q['id']}** {q['text']} — {q['n']} own / {q['n_all']} incl. sub-questions, "
                 f"{q['first']}..{q['last']}, last-12-months {q['momentum']}, status {q['status'] or '-'}, stances {q['stances']}")
        if q["builds_on"]:
            L.append(f"{pad}  builds on: " + ", ".join(f"{b['q']}×{b['count']}" for b in q["builds_on"]))
        if q["seeds"]:
            L.append(f"{pad}  seeds: " + "; ".join(f"[{k}] {T(k)}" for k in q["seeds"][:3]))
    ch = [(s, t, n) for (s, t), n in challenge.items()]
    if ch:
        L += ["", "## Challenge links (a 'challenges' paper citing another question)", ""]
        L += [f"- {s} → {t} ×{n}" for s, t, n in sorted(ch, key=lambda x: -x[2])]
    open(os.path.join(a.out, "questions_digest.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"question graph added to graph.json; digest -> questions_digest.md ({len(Q)} questions)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prepare", "build"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--notes")
    a = ap.parse_args()
    prepare(a) if a.cmd == "prepare" else build(a)


if __name__ == "__main__":
    main()
