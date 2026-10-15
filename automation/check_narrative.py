#!/usr/bin/env python3
"""Check <lineage>/narrative.md against the current data: every cited paper key exists, the overview's paper and
citation counts match graph.json, and every paper has a research-question label.
Overview counts are looked for in the first section: "共 N 篇" / "N 条引用关系" (zh) or "N papers" / "N citation links" (en).
Usage: python3 -I check_narrative.py --config research-lineage.json     exit 0 = OK, 1 = problems (one per line)
"""
import argparse, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Config, config_arg  # noqa: E402

REF = r"\[((?:\d{4}\.\d{4,5})|(?:s2:[0-9a-f]{8,})|(?:(?:doi|title|oa):[^\]\s]+))\]"
PAT = {"zh": (r"共\s*(\d+)\s*篇", r"(\d+)\s*条引用关系"), "en": (r"(\d+)\s+papers", r"(\d+)\s+citation (?:links|edges)")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    config_arg(ap)
    a = ap.parse_args()
    cfg = Config(a.config)
    g = json.load(open(os.path.join(cfg["lineage"], "graph.json"), encoding="utf-8"))
    md = open(os.path.join(cfg["lineage"], "narrative.md"), encoding="utf-8").read()
    keys = {n["key"] for n in g["nodes"]}
    problems = [f"cites unknown paper key: {r}" for r in sorted(set(re.findall(REF, md))) if r not in keys]
    overview = md.split("## ", 2)[1] if "## " in md else md
    p_n, p_e = PAT.get(cfg.lang, PAT["en"])
    m = re.search(p_n, overview)
    if not m or int(m.group(1)) != g["meta"]["n"]:
        problems.append(f"overview paper count ({m.group(1) if m else 'not found'}) != data ({g['meta']['n']})")
    m = re.search(p_e, overview)
    if not m or int(m.group(1)) != g["meta"]["edges"]:
        problems.append(f"overview citation count ({m.group(1) if m else 'not found'}) != data ({g['meta']['edges']})")
    unlabeled = sorted(k for k in keys if k not in (g.get("questions") or {}).get("papers", {}))
    if unlabeled:
        problems.append(f"{len(unlabeled)} papers have no research-question label: " + ", ".join(unlabeled))
    for p in problems:
        print("-", p)
    print("OK" if not problems else f"{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
