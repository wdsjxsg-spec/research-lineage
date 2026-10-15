#!/usr/bin/env python3
"""Build <lineage>/collection.csv (input of scripts/collect.py) from the category folders under papers/.
arXiv papers: "<ID>_<title>.pdf"; others: "<title>.pdf", DOI taken from the previous collection.csv (keeps DOIs added by
hand) or <state>/abstracts.json. The inbox and archive/ are not included.
Usage: python3 -I make_collection.py --config research-lineage.json [--check]
"""
import argparse, csv, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Config, config_arg, load_json, category_dirs, title_from_file  # noqa: E402


def norm(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    config_arg(ap)
    ap.add_argument("--check", action="store_true", help="compare only, do not write")
    a = ap.parse_args()
    cfg = Config(a.config)
    out = os.path.join(cfg["lineage"], "collection.csv")
    old = list(csv.DictReader(open(out, encoding="utf-8"))) if os.path.exists(out) else []
    old_doi = {norm(r["title"]): r["doi"] for r in old if r.get("doi")}
    abs_doi = {v.get("file"): v.get("doi") for v in load_json(cfg.state("abstracts.json"), {}).values() if v.get("file") and v.get("doi")}
    rows = []
    for cat in category_dirs(cfg):
        for f in sorted(os.listdir(os.path.join(cfg["papers"], cat))):
            if not f.lower().endswith(".pdf"):
                continue
            m = re.match(r"(\d{4}\.\d{4,5})_(.*)\.pdf$", f, re.I)
            ax, title = (m.group(1), m.group(2)) if m else ("", title_from_file(f))
            doi = "" if ax else (old_doi.get(norm(title)) or abs_doi.get(f) or "")
            rows.append({"arxiv_id": ax, "doi": doi, "title": title, "category": cat})
    rows.sort(key=lambda r: (r["category"], r["arxiv_id"] or "~" + norm(r["title"])))
    A = {(r["arxiv_id"], norm(r["title"]), r["category"]) for r in old}
    B = {(r["arxiv_id"], norm(r["title"]), r["category"]) for r in rows}
    print(f"collection: {len(rows)} papers (was {len(old)}; +{len(B - A)} -{len(A - B)})")
    for x in sorted(B - A): print("  +", x)
    for x in sorted(A - B): print("  -", x)
    if a.check:
        return
    os.makedirs(cfg["lineage"], exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["arxiv_id", "doi", "title", "category"])
        w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    main()
