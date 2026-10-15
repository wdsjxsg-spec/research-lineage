#!/usr/bin/env python3
"""List 0-byte placeholder papers in <papers>/placeholders_todo.md with links and open-access status, so the user can
download them in a browser (many open-access sites block scripts) and overwrite the placeholder with the same name.
Usage: python3 -I placeholders.py --config research-lineage.json
"""
import argparse, csv, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Config, config_arg, load_json, oa_get, category_dirs, title_from_file  # noqa: E402

TXT = {
    "zh": {"title": "# 占位论文待下载清单", "sum": "共 {n} 篇占位(0 字节文件，文件名即标题):开放获取 {o} 篇，其他 {x} 篇。",
           "how": "在浏览器中打开链接下载 PDF,用**同名文件**覆盖占位文件即可;下次运行时它会从清单中消失。",
           "oa": "开放获取(浏览器可直接下载)", "other": "付费墙 / 无 PDF / 未知", "cols": "| 分类 | 论文 | 状态 | 链接 |",
           "s_arxiv": "arXiv 无 PDF(撤回或仅索引条目)", "s_oa": "开放获取({})— 站点拦截脚本，浏览器可下载",
           "s_pay": "付费墙 — 需机构订阅或联系作者", "s_unknown": "未知(没有记录 DOI,可在 collection.csv 里补)", "s_fail": "查询失败:{}"},
    "en": {"title": "# Placeholder papers to download", "sum": "{n} placeholders (0-byte files named by title): {o} open access, {x} other.",
           "how": "Open the link in a browser, download the PDF and overwrite the placeholder with the **same file name**.",
           "oa": "Open access (download in a browser)", "other": "Paywalled / no PDF / unknown", "cols": "| Category | Paper | Status | Link |",
           "s_arxiv": "no PDF on arXiv (withdrawn or index-only)", "s_oa": "open access ({}) — site blocks scripts, browser works",
           "s_pay": "paywalled — needs a subscription or ask the authors", "s_unknown": "unknown (no DOI recorded; add one in collection.csv)", "s_fail": "lookup failed: {}"},
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    config_arg(ap)
    a = ap.parse_args()
    cfg = Config(a.config)
    T = TXT.get(cfg.lang, TXT["en"])
    by_file = {v.get("file"): k for k, v in load_json(cfg.state("abstracts.json"), {}).items() if v.get("file")}
    coll = os.path.join(cfg["lineage"], "collection.csv")
    doi_by_title = {r["title"]: r["doi"] for r in csv.DictReader(open(coll, encoding="utf-8"))} if os.path.exists(coll) else {}
    rows = []
    for cat in category_dirs(cfg):
        d = os.path.join(cfg["papers"], cat)
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".pdf") or os.path.getsize(os.path.join(d, fn)) > 0:
                continue
            title = title_from_file(fn)
            m = re.match(r"(\d{4}\.\d{4,5})_", fn)
            key = by_file.get(fn) or (m.group(1) if m else None) or (f"doi:{doi_by_title[title]}" if doi_by_title.get(title) else None)
            status, link, is_oa = T["s_unknown"], "", False
            if key and re.match(r"\d{4}\.\d{4,5}$", key):
                status, link = T["s_arxiv"], f"https://arxiv.org/abs/{key}"
            elif key:
                ref = key.replace("openalex:", "")
                try:
                    w = oa_get(f"works/{ref}", {"select": "doi,open_access,primary_location"})
                    oa = w.get("open_access") or {}
                    link = (oa.get("oa_url") if oa.get("is_oa") else None) or w.get("doi") or f"https://openalex.org/{ref}"
                    is_oa = bool(oa.get("is_oa"))
                    status = T["s_oa"].format(oa.get("oa_status")) if is_oa else T["s_pay"]
                except Exception as ex:
                    status = T["s_fail"].format(ex)
                time.sleep(0.3)
            rows.append((cat, title, status, link, is_oa))
    oa_rows = [r for r in rows if r[4]]
    other = [r for r in rows if not r[4]]
    L = [T["title"], "", T["sum"].format(n=len(rows), o=len(oa_rows), x=len(other)), T["how"], ""]
    for name, group in ((T["oa"], oa_rows), (T["other"], other)):
        L += [f"## {name} ({len(group)})", "", T["cols"], "|---|---|---|---|"]
        L += [f"| {c[:2]} | {t} | {s} | {l} |" for c, t, s, l, _ in group]
        L.append("")
    out = os.path.join(cfg["papers"], "placeholders_todo.md")
    open(out, "w", encoding="utf-8").write("\n".join(L))
    print(f"wrote {cfg.rel(out)}: {len(rows)} placeholders ({len(oa_rows)} open access)")


if __name__ == "__main__":
    main()
