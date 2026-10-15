#!/usr/bin/env python3
"""Move one paper file between papers/ and archive/ (used by the weekly job; file names often contain spaces).
Usage: python3 -I move_paper.py --config research-lineage.json <source file> <target folder>
Source must be under papers/ or archive/; target must be an existing category folder under papers/, or any folder under
archive/ (created if missing). Never overwrites. Paths are relative to the project root.
"""
import argparse, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Config, config_arg, category_dirs  # noqa: E402


def inside(path, base):
    return os.path.commonpath([path, base]) == base


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    config_arg(ap)
    ap.add_argument("src"); ap.add_argument("dst_dir")
    a = ap.parse_args()
    cfg = Config(a.config)
    src = os.path.realpath(os.path.join(cfg.root, a.src))
    dst_dir = os.path.realpath(os.path.join(cfg.root, a.dst_dir))
    papers, archive = os.path.realpath(cfg["papers"]), os.path.realpath(cfg["archive"])
    if not ((inside(src, papers) or inside(src, archive)) and os.path.isfile(src)):
        sys.exit(f"refused: source missing or not under papers/ or archive/: {a.src}")
    cats = {os.path.realpath(os.path.join(cfg["papers"], c)) for c in category_dirs(cfg)}
    if not (inside(dst_dir, archive) or dst_dir in cats):
        sys.exit(f"refused: target must be an existing category folder ({', '.join(category_dirs(cfg))}) or under archive/: {a.dst_dir}")
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, os.path.basename(src))
    if os.path.exists(dst):
        sys.exit(f"refused: target already exists: {cfg.rel(dst)}")
    shutil.move(src, dst)
    print(f"moved: {cfg.rel(src)} -> {cfg.rel(dst)}")


if __name__ == "__main__":
    main()
