#!/usr/bin/env python3
"""Add approved papers to a category (downloads PDF, records abstract for one-line summaries).
List file, one per line: <category folder>|<ID>, ID = arXiv ID, doi:<DOI>, openalex:<W...> or title:<exact title>
(titles are resolved in OpenAlex; a paper with an arXiv version is fetched from arXiv). Lines starting with # are skipped.
Failed downloads become 0-byte placeholders. Exit 1 only if metadata could not be found (so a scheduled run retries).
Usage: python3 -I add_papers.py --config research-lineage.json <list_file>
"""
import argparse, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (Config, config_arg, load_json, save_json, sanitize, arxiv_lookup, download, oa_get, oa_to_cand,  # noqa: E402
                    oa_find_title, OA_SELECT, ARXIV_ID)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    config_arg(ap)
    ap.add_argument("list_file")
    a = ap.parse_args()
    cfg = Config(a.config)
    pairs = [l.strip().split("|")[:2] for l in open(a.list_file, encoding="utf-8") if l.strip() and not l.startswith("#")]
    oa = {}
    for cat, pid in pairs:
        if ARXIV_ID.match(pid):
            continue
        try:
            if pid.startswith("title:"):
                w = oa_find_title(pid[6:].strip())
                if not w:
                    print(f"MISSING-META {pid} (no exact title match in OpenAlex)"); continue
            else:
                w = oa_get(f"works/{pid.replace('openalex:', '')}", {"select": OA_SELECT})
            oa[pid] = oa_to_cand(w, "manual")
        except Exception as ex:
            print(f"MISSING-META {pid}: {ex}")
        time.sleep(0.3)
    ax_ids = [pid for _, pid in pairs if ARXIV_ID.match(pid)] + [c["arxiv"] for c in oa.values() if c and c.get("arxiv")]
    meta = {p["id"]: p for p in arxiv_lookup(ax_ids)} if ax_ids else {}
    abs_path = cfg.state("abstracts.json")
    abstracts = load_json(abs_path, {})
    ok = fail = missing = 0
    for cat, pid in pairs:
        os.makedirs(os.path.join(cfg["papers"], cat), exist_ok=True)
        c = oa.get(pid)
        aid = pid if ARXIV_ID.match(pid) else (c or {}).get("arxiv")
        if aid:
            p = meta.get(aid)
            if not p:
                print(f"MISSING-META {aid}"); fail += 1; missing += 1; continue
            path = os.path.join(cfg["papers"], cat, f"{aid}_{sanitize(p['title'])}.pdf")
            got = download({"id": aid, "arxiv": aid}, path)
            key, rec = aid, {"title": p["title"], "abstract": p["abstract"], "published": p["published"]}
        else:
            if not c:
                fail += 1; missing += 1; continue
            path = os.path.join(cfg["papers"], cat, f"{sanitize(c['title'])}.pdf")
            got = download(c, path)
            key = f"doi:{c['doi']}" if c.get("doi") else f"openalex:{c['openalex']}"
            rec = {"title": c["title"], "abstract": c["abstract"], "published": c["published"],
                   "venue": c["venue"], "doi": c["doi"], "openalex": c["openalex"]}
        if not got:
            open(path, "w").close()
        abstracts[key] = {"cat": cat, **rec, "file": os.path.basename(path), "downloaded": got}
        ok += got; fail += not got
        print(f"{'OK' if got else 'PLACEHOLDER'} {key} {rec['title'][:80]}", flush=True)
        time.sleep(1.5)
    save_json(abs_path, abstracts)
    print(f"\nOK={ok} PLACEHOLDER/FAIL={fail}")
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
