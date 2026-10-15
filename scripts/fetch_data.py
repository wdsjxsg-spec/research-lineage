#!/usr/bin/env python3
"""Download the venue-tier tables (CCF / 中科院分区 / JCR / 新锐分区 / 预警名单) into <skill>/data.

The tables are third-party data collected by the ShowJCR project (github.com/hitfyd/ShowJCR); the rankings belong
to their publishers (CCF, 中国科学院文献情报中心, Clarivate ...). The repository ships unmodified copies (see
data/README.md); this script restores them if they are missing, or fetches a newer ShowJCR commit (maintainers:
when bumping --commit, update PINNED, SHA256 and venues.TIER_FILES together and commit the new files).

Usage: python3 -I scripts/fetch_data.py [--commit SHA] [--force]
  --commit  ShowJCR commit to download from (default: the pinned one, whose files are checked by sha256)
  --force   re-download files that already exist
"""
import argparse, hashlib, os, sys, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops the script dir from sys.path
from venues import DATA, TIER_FILES  # noqa: E402  (one list of file names, shared with venues.py)

PINNED = "4687a8f608f20aaf004299992f5d347dba009361"
FOLDER = "中科院分区表及JCR原始数据文件"
SHA256 = {  # of the files at PINNED
    "CCF2026-UTF8.csv": "0104e5431fbf522ca0511a93a6169723831ec7515a9d5efe0f7df415f5157ed8",
    "FQBJCR2025-UTF8.csv": "481224dca2cacc1cce49afb44c968d734c834e498e5ff054f15efb5a548789fc",
    "JCR2025-UTF8.csv": "e9a0402f505264a796615bcec697f843af08dbce023ce67164c0f6f4709207c4",
    "XR2026-UTF8.csv": "8bffe4bdcae8f710c756e0138d93219bb53555eae23827c20287bc9200a027e6",
    "XR2026Conferences-UTF8.csv": "96b6764033d89e196aaf40363aa193f8965261fa52fd3631c6365686b7630805",
    "GJQKYJMD2025.csv": "f6a37a5e409ce543cb5892f92603fc91272d5617d324e50fe520cdd2bca7a6c4",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commit", default=PINNED)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    os.makedirs(DATA, exist_ok=True)
    base = f"https://raw.githubusercontent.com/hitfyd/ShowJCR/{a.commit}/{urllib.parse.quote(FOLDER)}/"
    failed = 0
    for f in TIER_FILES.values():
        dst = os.path.join(DATA, f)
        if os.path.exists(dst) and not a.force:
            print(f"have  {f}")
            continue
        try:
            req = urllib.request.Request(base + urllib.parse.quote(f), headers={"User-Agent": "research-lineage-skill"})
            body = urllib.request.urlopen(req, timeout=120).read()
        except Exception as e:
            print(f"FAIL  {f}: {e}", file=sys.stderr); failed += 1; continue
        if a.commit == PINNED and f in SHA256 and hashlib.sha256(body).hexdigest() != SHA256[f]:
            print(f"FAIL  {f}: sha256 mismatch, not saved", file=sys.stderr); failed += 1; continue
        with open(dst + ".part", "wb") as fh:
            fh.write(body)
        os.replace(dst + ".part", dst)
        print(f"got   {f} ({len(body) // 1024} KB)")
    if failed:
        sys.exit(f"{failed} file(s) failed; re-run to retry (existing files are kept)")
    print(f"tier tables ready in {DATA}")


if __name__ == "__main__":
    main()
