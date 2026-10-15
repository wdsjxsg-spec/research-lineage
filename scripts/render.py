#!/usr/bin/env python3
"""Render graph.json (+ narrative.md) into one self-contained interactive HTML page.

Usage: python3 -I render.py --out DIR [--narrative DIR/narrative.md] [--notes FILE]
                            [--title "..."] [--lang zh|en] [--html DIR/lineage.html]
No external assets: works offline and can be published as-is.
"""
import argparse, html, json, os, re

LABELS = {
    "en": {"report": "Report", "timeline": "Timeline", "network": "Citation network", "key": "Key papers",
           "gaps": "Gaps & candidates", "search": "Search title or ID…", "papers": "papers", "links": "citation links",
           "directions": "directions", "builds_on": "Builds on (in collection)", "built_upon": "Built upon by (in collection)",
           "clear": "Clear selection", "foundational": "Foundational", "bridge": "Bridge", "frontier": "Frontier",
           "isolated": "Isolated", "chains": "Longest lineage chains", "year": "Year", "direction": "Direction",
           "local_in": "Cited in set", "citations": "Citations", "cpy": "Cit./yr", "roles": "Roles", "title": "Title",
           "hubs": "Outside papers cited by several collection papers — candidate missing foundations",
           "front": "Outside papers citing several collection papers — newer work to consider",
           "count": "×", "flow": "Cross-direction flow (row builds on column)", "per_year": "Papers per year by direction",
           "gap_list": "Gaps", "no_narrative": "No narrative yet — write narrative.md and re-render.",
           "note": "Note", "abstract": "Abstract", "open": "Open paper", "theme": "Theme", "focus_hint": "Click a direction to focus it; click again to clear.",
           "select_hint": "Click any paper to trace its lineage.", "withdrawn": "withdrawn", "other": "Other",
           "show_tl": "Show in timeline", "show_net": "Show in network", "none": "none",
           "questions": "Question lineage", "q_hint": "One lane per research question. Shape = stance; dashed lines = citations from papers that challenge earlier work. Click a question to focus it.",
           "q_overview": "Research questions", "q_period": "Period", "q_momentum": "Last 12 mo.", "q_status": "Status",
           "q_builds_on": "Builds on", "q_led_to": "Led to", "q_papers": "Papers", "research_q": "Research question",
           "q_approach": "Approach", "q_finding": "Finding", "back": "← All questions", "q_col": "Question",
           "st_proposes": "proposes", "st_extends": "extends", "st_evaluates": "evaluates", "st_challenges": "challenges",
           "st_reframes": "reframes", "st_surveys": "surveys", "status_emerging": "emerging", "status_active": "active",
           "status_dormant": "dormant", "status_contested": "contested",
           "gap_thin_direction": "{a}: only {n} paper(s)",
           "gap_cooling_direction": "{a}: newest paper {last} — nothing in the last 12 months of the collection",
           "gap_disconnected_pair": "No citation links between {a} and {b}",
           "gap_weakly_connected_pair": "{a} ({na}) and {b} ({nb}) barely cite each other: {ab} links one way, {ba} the other — likely separate communities",
           "gap_isolated_papers": "{n}/{total} papers have no citation link to the rest of the collection",
           "gap_data_quality": "{n} paper(s) lack citation data; their links are undercounted",
           "pub": "Publication", "pub_status": "Publication status", "pub_tiers": "Venue tiers", "pub_by_dir": "By direction",
           "pub_by_year": "By year", "pub_list": "Papers by venue", "published": "Formally published", "preprint_only": "Preprint only",
           "thesis": "Thesis", "ccf_ab": "CCF A/B", "cas12": "CAS zone 1–2", "of_journals": "of journals", "of_published": "of published",
           "cas": "CAS", "zone": "", "xr": "XR", "warning": "warning list", "unranked": "not listed", "venue": "Venue", "type": "Type",
           "all": "All", "arxiv_only": "arXiv only", "ccf_note": "Among formally published papers (conference, journal, workshop, other).",
           "cas_note": "Journals only. Top journals are counted in their zone.", "jcr_note": "Journals only (best quartile across categories).",
           "xr_note": "Only papers whose journal or conference is listed.", "pub_src": "Venue from OpenAlex (preferred) or Semantic Scholar; tiers from ShowJCR tables (CCF 2026, CAS 2025, JCR 2025, XR 2026, warning list 2025). Posters and short papers inherit their conference's tier.",
           "pt_conference": "Conference", "pt_journal": "Journal", "pt_workshop": "Workshop", "pt_published": "Published (other)",
           "pt_arxiv-only": "arXiv only", "pt_preprint": "Other preprint", "pt_thesis": "Thesis", "pt_unknown": "Unknown",
           "zoom_in": "Zoom in", "zoom_out": "Zoom out", "zoom_reset": "Reset view", "zoom_hint": "Ctrl/⌘ + wheel or the buttons to zoom; drag to pan.",
           "sort": "Sort", "sort_tier": "Tier (high→low)", "sort_new": "Year (new→old)", "sort_old": "Year (old→new)", "sort_title": "Title (A→Z)",
           "pub_search": "Search title or venue…", "undated": "Date unknown"},
    "zh": {"report": "脉络报告", "timeline": "时间线", "network": "引文网络", "key": "关键论文",
           "gaps": "空白与候选", "search": "搜索标题或 ID…", "papers": "篇论文", "links": "条内部引用",
           "directions": "个方向", "builds_on": "它所继承的(集合内)", "built_upon": "继承它的(集合内)",
           "clear": "清除选择", "foundational": "奠基", "bridge": "桥梁", "frontier": "前沿",
           "isolated": "孤立", "chains": "最长传承链", "year": "年份", "direction": "方向",
           "local_in": "集合内被引", "citations": "总被引", "cpy": "年均被引", "roles": "角色", "title": "标题",
           "hubs": "被多篇集合论文引用的外部论文 —— 可能遗漏的奠基文献",
           "front": "引用多篇集合论文的外部论文 —— 值得考虑纳入的新工作",
           "count": "次", "flow": "方向间传承(行 引用 列 = 行建立在列之上)", "per_year": "各方向逐年论文数",
           "gap_list": "空白与问题", "no_narrative": "尚未撰写脉络报告 —— 写好 narrative.md 后重新渲染。",
           "note": "笔记", "abstract": "摘要", "open": "打开论文", "theme": "主题", "focus_hint": "点击方向可聚焦，再次点击取消。",
           "select_hint": "点击任意论文，追踪它的传承脉络。", "withdrawn": "已撤回", "other": "其他",
           "show_tl": "在时间线中查看", "show_net": "在网络中查看", "none": "无",
           "questions": "问题脉络", "q_hint": "每条泳道是一个研究问题，标记形状表示立场，虚线表示「质疑型」论文对前人工作的引用。点击问题可聚焦。",
           "q_overview": "研究问题总览", "q_period": "时间跨度", "q_momentum": "近 12 个月", "q_status": "状态",
           "q_builds_on": "建立在", "q_led_to": "引出", "q_papers": "论文", "research_q": "研究问题",
           "q_approach": "方法", "q_finding": "发现", "back": "← 返回问题总览", "q_col": "问题",
           "st_proposes": "提出", "st_extends": "改进", "st_evaluates": "评测", "st_challenges": "质疑",
           "st_reframes": "重构问题", "st_surveys": "综述", "status_emerging": "新兴", "status_active": "活跃",
           "status_dormant": "沉寂", "status_contested": "有争议",
           "gap_thin_direction": "{a}:仅 {n} 篇论文",
           "gap_cooling_direction": "{a}:最新论文为 {last},集合最近 12 个月内没有新工作",
           "gap_disconnected_pair": "{a} 与 {b} 之间没有任何引用关系",
           "gap_weakly_connected_pair": "{a}({na} 篇)与 {b}({nb} 篇)几乎互不引用：一个方向 {ab} 条，另一个方向 {ba} 条 —— 很可能是两个分离的社区",
           "gap_isolated_papers": "{n}/{total} 篇论文与集合其余部分没有任何引用关系",
           "gap_data_quality": "{n} 篇论文缺少引用数据，其关联会被低估",
           "pub": "发表情况", "pub_status": "发表状态", "pub_tiers": "等级分布", "pub_by_dir": "按方向", "pub_by_year": "按年份",
           "pub_list": "论文与出版场所", "published": "已正式发表", "preprint_only": "仅预印本", "thesis": "学位论文",
           "ccf_ab": "CCF A/B 类", "cas12": "中科院 1–2 区", "of_journals": "篇期刊中", "of_published": "篇已发表中",
           "cas": "中科院", "zone": "区", "xr": "新锐", "warning": "预警", "unranked": "未收录", "venue": "出版场所", "type": "类型",
           "all": "全部", "arxiv_only": "仅 arXiv", "ccf_note": "统计范围：已正式发表的论文(会议、期刊、Workshop、其他)。",
           "cas_note": "统计范围：期刊论文;Top 期刊计入其所在分区。", "jcr_note": "统计范围：期刊论文(取各学科中最好的分区)。",
           "xr_note": "只统计期刊或会议被新锐分区收录的论文。", "pub_src": "出版场所以 OpenAlex 为准，缺失时用 Semantic Scholar;等级来自 ShowJCR 数据表(CCF 2026、中科院分区 2025 升级版、JCR 2025、新锐分区 2026、国际期刊预警名单 2025)。Poster 与短文按所属会议计等级。",
           "pt_conference": "会议", "pt_journal": "期刊", "pt_workshop": "Workshop", "pt_published": "已发表(其他)",
           "pt_arxiv-only": "仅 arXiv", "pt_preprint": "其他预印本", "pt_thesis": "学位论文", "pt_unknown": "未知",
           "zoom_in": "放大", "zoom_out": "缩小", "zoom_reset": "复位", "zoom_hint": "Ctrl/⌘ + 滚轮或用按钮缩放，按住拖动可平移。",
           "sort": "排序", "sort_tier": "等级(高→低)", "sort_new": "年份(新→旧)", "sort_old": "年份(旧→新)", "sort_title": "标题(A→Z)",
           "pub_search": "搜索标题或出版场所…", "undated": "日期未知"},
}


def inline(s):
    s = html.escape(s, quote=True)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?!\w)", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    # paper references like [2410.13919] or [s2:abc] become in-page links
    s = re.sub(r"\[((?:\d{4}\.\d{4,5})|(?:s2:[0-9a-f]{8,})|(?:(?:doi|title|oa):[^\]\s]+))\]", r'<a href="#" class="pref" data-key="\1">\1</a>', s)
    return s


def md_to_html(md):
    out, para, lst, tbl = [], [], None, []

    def flush():
        nonlocal para, lst, tbl
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>"); para = []
        if lst:
            tag, items = lst
            out.append(f"<{tag}>" + "".join(f"<li>{inline(i)}</li>" for i in items) + f"</{tag}>"); lst = None
        if tbl:
            rows = [r for r in tbl if not re.match(r"^\s*\|?\s*:?-{2,}", r)]
            cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
            if cells:
                h = "".join(f"<th>{inline(c)}</th>" for c in cells[0])
                b = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in cells[1:])
                out.append(f'<div class="tablewrap"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>')
            tbl = []

    for line in md.splitlines():
        s = line.rstrip()
        m = re.match(r"^(#{1,4})\s+(.*)", s)
        if m:
            flush(); lvl = min(4, len(m.group(1)) + 1)
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>"); continue
        if s.strip().startswith("|"):
            if para or lst: flush()
            tbl.append(s); continue
        elif tbl:
            flush()
        m = re.match(r"^\s*[-*]\s+(.*)", s) or re.match(r"^\s*(\d+)[.)]\s+(.*)", s)
        if m:
            tag = "ol" if re.match(r"^\s*\d", s) else "ul"
            if para: flush()
            if lst and lst[0] != tag: flush()
            if not lst: lst = (tag, [])
            lst[1].append(m.group(m.lastindex)); continue
        if s.startswith(">"):
            flush(); out.append("<blockquote>" + inline(s.lstrip("> ")) + "</blockquote>"); continue
        if not s.strip():
            flush(); continue
        if lst:
            lst[1][-1] += " " + s.strip(); continue
        para.append(s.strip())
    flush()
    return "\n".join(out)


def load_notes(path):
    if not path:
        return {}
    txt = open(path, encoding="utf-8").read()
    try:
        return {str(k): str(v) for k, v in json.loads(txt).items()}
    except Exception:
        notes = {}
        for line in txt.splitlines():
            m = re.search(r"(\d{4}\.\d{4,5})", line)
            if m and line.lstrip().startswith(("-", "*")):
                body = line.split("—", 1)[1] if "—" in line else line
                notes[m.group(1)] = re.sub(r"[*`]", "", body).strip()
        return notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--narrative")
    ap.add_argument("--notes", help="JSON {key: text} or a markdown list whose lines contain arXiv IDs")
    ap.add_argument("--title", default=None)
    ap.add_argument("--lang", default="en", choices=sorted(LABELS))
    ap.add_argument("--html")
    a = ap.parse_args()

    graph = json.load(open(os.path.join(a.out, "graph.json"), encoding="utf-8"))
    narrative = a.narrative or os.path.join(a.out, "narrative.md")
    nar_html = md_to_html(open(narrative, encoding="utf-8").read()) if os.path.exists(narrative) else ""
    notes = load_notes(a.notes)
    for n in graph["nodes"]:
        if n["key"] in notes:
            n["note"] = notes[n["key"]]
    L = LABELS[a.lang]
    title = a.title or ("研究脉络图" if a.lang == "zh" else "Research Lineage")
    payload = json.dumps({"graph": graph, "L": L}, ensure_ascii=False).replace("</", "<\\/")
    subs = {"__TITLE__": html.escape(title), "__LANG__": "zh-CN" if a.lang == "zh" else "en",
            "__NARRATIVE__": nar_html or f'<p class="muted">{html.escape(L["no_narrative"])}</p>',
            "__DATA__": payload}
    subs.update({"{{" + k + "}}": html.escape(v) for k, v in L.items()})
    # single pass, so text inside titles/narrative can never be re-substituted
    page = re.sub("|".join(re.escape(k) for k in subs), lambda m: subs[m.group(0)], TEMPLATE)
    dest = a.html or os.path.join(a.out, "lineage.html")
    open(dest, "w", encoding="utf-8").write(page)
    print(f"wrote {dest} ({len(page) // 1024} KB)")


TEMPLATE = r"""<!doctype html>
<html lang="__LANG__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{color-scheme:light;
 --page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
 --border:rgba(11,11,11,.10);--edge:rgba(82,81,78,.28);--edge-hi:#0b0b0b;--wash:rgba(42,120,214,.10);
 --s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--other:#b5b3ac;--flow:42,120,214;
 --t1:#174e94;--t2:#2a78d6;--t3:#79aae6;--t4:#bcd5f3;--warn:#b3261e}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
 --page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;
 --border:rgba(255,255,255,.10);--edge:rgba(195,194,183,.22);--edge-hi:#f0efec;--wash:rgba(57,135,229,.16);
 --s1:#3987e5;--s2:#d95926;--s3:#199e70;--other:#5c5b57;--flow:57,135,229;
 --t1:#b4d1f6;--t2:#6aa6ee;--t3:#3577c7;--t4:#25528a;--warn:#f2867d}}
:root[data-theme="dark"]{color-scheme:dark;
 --page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;
 --border:rgba(255,255,255,.10);--edge:rgba(195,194,183,.22);--edge-hi:#f0efec;--wash:rgba(57,135,229,.16);
 --s1:#3987e5;--s2:#d95926;--s3:#199e70;--other:#5c5b57;--flow:57,135,229;
 --t1:#b4d1f6;--t2:#6aa6ee;--t3:#3577c7;--t4:#25528a;--warn:#f2867d}
*{box-sizing:border-box}
html,body{margin:0;background:var(--page);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
header{padding:20px 16px 0;max-width:1400px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}
.stats{color:var(--ink2);font-size:14px}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
button,.chip,input{font:inherit;color:inherit}
.btn{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:5px 10px;cursor:pointer}
.btn:hover{background:var(--wash)}
nav{display:flex;gap:4px;overflow-x:auto;margin-top:14px;border-bottom:1px solid var(--grid)}
nav button{background:none;border:0;border-bottom:2px solid transparent;padding:8px 12px;cursor:pointer;color:var(--ink2);white-space:nowrap}
nav button[aria-selected="true"]{color:var(--ink);border-bottom-color:var(--ink);font-weight:600}
main{max-width:1400px;margin:0 auto;padding:16px;display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:16px;align-items:start}
main.nodrawer{grid-template-columns:minmax(0,1fr)}
@media (max-width:900px){main,main.nodrawer{grid-template-columns:minmax(0,1fr)}}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px;min-width:0}
section[hidden]{display:none}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px}
.chip{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--border);border-radius:999px;padding:3px 10px;background:var(--surface);cursor:pointer;font-size:13px;color:var(--ink)}
.chip[aria-pressed="true"]{background:var(--wash);border-color:var(--ink2)}
.sw{width:10px;height:10px;border-radius:50%;flex:none}
.sw.o{background:transparent!important;border:2px solid var(--other)}
select{font:inherit;color:inherit;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:4px 8px}
input[type=search]{border:1px solid var(--border);border-radius:8px;padding:5px 10px;background:var(--surface);min-width:200px;flex:1;max-width:320px}
.hint{color:var(--muted);font-size:13px}
.muted{color:var(--muted)}
svg{display:block;width:100%;height:auto;touch-action:none}
svg text{fill:var(--ink2);font-size:12px}
.axis line{stroke:var(--grid)}
.axis text{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
.lane-sep{stroke:var(--grid)}
.lane-label{fill:var(--ink);font-size:13px;font-weight:600}
.lane-count{fill:var(--muted);font-size:11px}
.e{fill:none;stroke:var(--edge);stroke-width:1}
.e.hi{stroke:var(--edge-hi);stroke-width:1.6;opacity:.85}
.e.dim{opacity:.05}
.n{stroke:var(--surface);stroke-width:2;cursor:pointer}
.n.o{fill:var(--surface)!important;stroke:var(--other);stroke-width:2}
.n.dim{opacity:.13}
.n.sel{stroke:var(--ink);stroke-width:3}
.n.match{stroke:var(--ink);stroke-width:2.5}
.hit{fill:transparent;cursor:pointer}
.nl{fill:var(--ink);font-size:11px;paint-order:stroke;stroke:var(--surface);stroke-width:3px;pointer-events:none}
.nl.dim{opacity:.15}
#tip{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:13px;max-width:340px;box-shadow:0 4px 16px rgba(0,0,0,.12);z-index:10;display:none}
#tip b{display:block;margin-bottom:2px}
#tip .m{color:var(--ink2)}
aside{position:sticky;top:12px;max-height:calc(100vh - 24px);overflow:auto}
aside h3{margin:0 0 6px;font-size:16px;line-height:1.35}
aside .meta{color:var(--ink2);font-size:13px;margin-bottom:8px}
aside h4{margin:14px 0 4px;font-size:13px;color:var(--ink2)}
aside ul{margin:0;padding-left:18px;font-size:13px}
aside li{margin:2px 0}
.linkish{background:none;border:0;padding:0;color:var(--ink);text-decoration:underline;text-decoration-color:var(--axis);cursor:pointer;text-align:left}
.linkish:hover{text-decoration-color:var(--ink)}
.role{display:inline-block;font-size:11px;border:1px solid var(--border);border-radius:999px;padding:0 7px;margin-right:4px;color:var(--ink2)}
.abs{font-size:13px;color:var(--ink2)}
#report{max-width:860px}
#report h2{font-size:19px;margin:22px 0 8px}#report h3{font-size:16px;margin:18px 0 6px}#report h4{font-size:15px}
#report p,#report li{color:var(--ink)}
#report blockquote{margin:8px 0;padding:6px 12px;border-left:3px solid var(--axis);color:var(--ink2)}
a{color:var(--ink);text-decoration-color:var(--axis)}a:hover{text-decoration-color:var(--ink)}
a.pref{font-variant-numeric:tabular-nums;font-size:.9em;color:var(--ink2)}
code{font-size:.9em;background:var(--wash);padding:0 4px;border-radius:4px}
.tablewrap{overflow-x:auto;margin:8px 0 16px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--grid);vertical-align:top}
th{color:var(--ink2);font-weight:600;white-space:nowrap}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
h2.sec{font-size:16px;margin:4px 0 8px}
.mult{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;margin-bottom:18px}
.mult .card{padding:10px 12px}
.mult h5{margin:0 0 4px;font-size:13px;display:flex;align-items:center;gap:6px}
.bar{rx:2}
.gap{margin:4px 0}
.chain{margin:6px 0 10px;font-size:13px}
.chain .arrow{color:var(--muted);margin:0 4px}
.e.ch{stroke-dasharray:4 3}
.ring{fill:none;stroke:var(--ink2);stroke-width:1.2;pointer-events:none}
.ring.dim{opacity:.13}
.qlabel{fill:var(--ink);font-size:12.5px;cursor:pointer}
.qlabel.root{font-weight:700;font-size:13px}
.qlabel:hover{text-decoration:underline}
.qmeta{fill:var(--muted);font-size:11px}
.qsel-bg{fill:transparent}
.qsel-bg.qband{fill:var(--wash);opacity:.6}
.qsel-bg.qsel{fill:var(--wash);opacity:1}
.tag{display:inline-block;font-size:11px;border-radius:999px;padding:0 7px;margin:0 4px 2px 0;border:1px solid var(--border);color:var(--ink2);white-space:nowrap}
.tag.st-challenges{border-color:var(--ink2);color:var(--ink)}
.qitem{margin:10px 0;padding-bottom:8px;border-bottom:1px solid var(--grid)}
.qitem .qq{margin:3px 0;color:var(--ink)}
.qitem .qa{font-size:13px;color:var(--ink2)}
.qchip{font:inherit;font-size:12px;background:var(--surface);border:1px solid var(--border);border-radius:999px;padding:1px 9px;margin:0 4px 4px 0;cursor:pointer;color:var(--ink)}
.qchip:hover{background:var(--wash)}
.mk{vertical-align:-2px;margin-right:4px}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px;margin-bottom:18px}
.tile{border:1px solid var(--border);border-radius:10px;padding:10px 12px}
.tile .v{font-size:26px;font-weight:650;font-variant-numeric:tabular-nums;line-height:1.2}
.tile .k{color:var(--ink2);font-size:13px}.tile .s{color:var(--muted);font-size:12px}
svg text.val{fill:var(--ink);font-variant-numeric:tabular-nums}
.tag.tier{border-color:var(--ink2);color:var(--ink)}
.tag.warn{border-color:var(--warn);color:var(--warn)}
.lg{display:inline-flex;align-items:center;gap:6px;margin-right:12px;font-size:13px;color:var(--ink2)}
.lg i{width:10px;height:10px;border-radius:2px;display:inline-block}
.zoombar{display:flex;gap:6px;align-items:center;margin:6px 0;flex-wrap:wrap}.zoombar .btn{padding:2px 9px;line-height:1.3}
svg#tl,svg#net,svg#qv{cursor:grab}
</style>
</head>
<body>
<header>
 <div class="top">
  <div><h1>__TITLE__</h1><div class="stats" id="stats"></div></div>
  <button class="btn" id="theme" title="{{theme}}">◐</button>
 </div>
 <nav role="tablist" id="tabs">
  <button role="tab" data-tab="report">{{report}}</button>
  <button role="tab" data-tab="questions" id="qtabbtn">{{questions}}</button>
  <button role="tab" data-tab="timeline">{{timeline}}</button>
  <button role="tab" data-tab="network">{{network}}</button>
  <button role="tab" data-tab="pub" id="pubtabbtn">{{pub}}</button>
 </nav>
</header>
<main id="main" class="nodrawer">
 <div>
  <section id="tab-report" class="card"><div id="report">__NARRATIVE__</div></section>
  <section id="tab-questions" class="card" hidden>
   <div class="toolbar"><div id="legend-q" class="toolbar" style="margin:0"></div><input type="search" id="q-q" placeholder="{{search}}"></div>
   <div class="hint">{{q_hint}}</div>
   <svg id="qv"></svg>
   <div id="qcard"></div>
  </section>
  <section id="tab-timeline" class="card" hidden>
   <div class="toolbar"><div id="legend-tl" class="toolbar" style="margin:0"></div><input type="search" id="q-tl" placeholder="{{search}}"></div>
   <div class="hint">{{select_hint}} {{focus_hint}}</div>
   <svg id="tl"></svg>
  </section>
  <section id="tab-network" class="card" hidden>
   <div class="toolbar"><div id="legend-net" class="toolbar" style="margin:0"></div><input type="search" id="q-net" placeholder="{{search}}"></div>
   <div class="hint">{{select_hint}} {{focus_hint}}</div>
   <svg id="net"></svg>
  </section>
  <section id="tab-pub" class="card" hidden><div id="pubview"></div></section>
 </div>
 <aside class="card" id="drawer" hidden></aside>
</main>
<div id="tip"></div>
<script type="application/json" id="data">__DATA__</script>
<script>
(function(){
"use strict";
const D=JSON.parse(document.getElementById('data').textContent);
const G=D.graph,L=D.L;
const N=G.nodes,byKey=new Map(N.map(n=>[n.key,n]));
const cats=new Map(G.categories.map(c=>[c.name,c]));
const outE=new Map(N.map(n=>[n.key,new Set()])),inE=new Map(N.map(n=>[n.key,new Set()]));
G.edges.forEach(([s,t])=>{outE.get(s).add(t);inE.get(t).add(s);});
const VS=G.venue_stats||null;
const QG=G.questions||null,QP=QG?QG.papers:{},QL=QG?QG.list:[],QM=new Map(QL.map(q=>[q.id,q]));
const SVGNS='http://www.w3.org/2000/svg';
const el=(tag,attrs,parent,text)=>{const e=document.createElementNS(SVGNS,tag);for(const k in attrs)e.setAttribute(k,attrs[k]);if(text!=null)e.textContent=text;if(parent)parent.appendChild(e);return e;};
const h=(tag,props,parent,text)=>{const e=document.createElement(tag);if(props)for(const k in props){if(k==='class')e.className=props[k];else e.setAttribute(k,props[k]);}if(text!=null)e.textContent=text;if(parent)parent.appendChild(e);return e;};
const color=c=>{const s=(cats.get(c)||{}).slot||0;return s?`var(--s${s})`:'var(--other)';};
const isOther=c=>!((cats.get(c)||{}).slot);
const catLabel=c=>(cats.get(c)||{}).label||c;
const roleName={foundational:L.foundational,bridge:L.bridge,frontier:L.frontier,isolated:L.isolated};
const short=(s,n)=>s.length>n?s.slice(0,n-1)+'…':s;
const yr=n=>n.year||(n.date?n.date.slice(0,4):'?');

document.getElementById('stats').textContent=`${G.meta.n} ${L.papers} · ${G.meta.edges} ${L.links} · ${G.categories.length} ${L.directions} · ${G.meta.generated.slice(0,10)}`;

// ---------- theme toggle (wins both ways over OS setting)
const root=document.documentElement;
document.getElementById('theme').onclick=()=>{const dark=root.dataset.theme?root.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;root.dataset.theme=dark?'light':'dark';try{localStorage.setItem('rl-theme',root.dataset.theme)}catch(e){}};
try{const t=localStorage.getItem('rl-theme');if(t)root.dataset.theme=t;}catch(e){}

// ---------- tabs
const tabs=[...document.querySelectorAll('#tabs button')];
let built={};
function show(tab){tabs.forEach(b=>b.setAttribute('aria-selected',b.dataset.tab===tab));
 document.querySelectorAll('main section').forEach(s=>s.hidden=s.id!=='tab-'+tab);
 if(!built[tab]){built[tab]=true;({questions:buildQuestions,timeline:buildTimeline,network:buildNetwork,pub:buildPub}[tab]||(()=>{}))();}
 applyState();try{history.replaceState(null,'','#'+tab)}catch(e){}}
tabs.forEach(b=>b.onclick=()=>show(b.dataset.tab));

// ---------- shared state: selection, focus direction, search
const state={sel:null,focus:null,q:'',qfocus:null};
const views=[]; // {nodes:Map key->[elements], labels, edges:[{s,t,el}]}
function lineage(k){const anc=new Set(),desc=new Set();const walk=(m,acc,s)=>{(m.get(s)||[]).forEach(x=>{if(!acc.has(x)){acc.add(x);walk(m,acc,x);}});};walk(outE,anc,k);walk(inE,desc,k);return{anc,desc};}
function applyState(){
 let keep=null,lin=null;
 if(state.sel){lin=lineage(state.sel);keep=new Set([state.sel,...lin.anc,...lin.desc]);}
 const q=state.q.trim().toLowerCase();
 const match=q?new Set(N.filter(n=>n.title.toLowerCase().includes(q)||n.key.toLowerCase().includes(q)||(QP[n.key]&&QP[n.key].question.toLowerCase().includes(q))).map(n=>n.key)):null;
 const qset=state.qfocus&&QM.has(state.qfocus)?new Set(QM.get(state.qfocus).all_papers):null;
 document.querySelectorAll('.qsel-bg').forEach(r=>r.classList.toggle('qsel',r.dataset.q===state.qfocus));
 views.forEach(v=>{
  v.nodes.forEach((els,k)=>{const n=byKey.get(k);let dim=false;
   if(keep)dim=!keep.has(k);else if(match)dim=!match.has(k);else if(state.focus)dim=n.category!==state.focus;else if(qset)dim=!qset.has(k);
   els.forEach(e=>{e.classList.toggle('dim',dim);e.classList.toggle('sel',k===state.sel&&e.classList.contains('n'));e.classList.toggle('match',!!match&&match.has(k)&&!keep&&e.classList.contains('n'));});});
  v.edges.forEach(({s,t,el:e})=>{let hi=false,dim=false;
   if(lin){const up=(s===state.sel||lin.anc.has(s))&&lin.anc.has(t);const down=(t===state.sel||lin.desc.has(t))&&lin.desc.has(s);hi=up||down;dim=!hi;}
   else if(state.focus){dim=byKey.get(s).category!==state.focus&&byKey.get(t).category!==state.focus;}
   else if(match){dim=!(match.has(s)||match.has(t));}
   else if(qset){dim=!(qset.has(s)||qset.has(t));}
   e.classList.toggle('hi',hi);e.classList.toggle('dim',dim);});
 });
 document.querySelectorAll('.chip[data-cat]').forEach(c=>c.setAttribute('aria-pressed',c.dataset.cat===state.focus));
 renderDrawer();
}
function select(k){state.sel=(state.sel===k)?null:k;applyState();}

// ---------- tooltip
const tip=document.getElementById('tip');
function showTip(ev,n){tip.replaceChildren();h('b',null,tip,n.title);
 h('div',{class:'m'},tip,`${yr(n)} · ${catLabel(n.category)} · ${L.citations} ${n.citations??'?'} · ${L.local_in} ${n.local_in}`);
 if(n.roles.length)h('div',{class:'m'},tip,n.roles.map(r=>roleName[r]).join(' · '));
 const qp=QP[n.key];if(qp)h('div',{class:'m'},tip,`${qp.q} · ${L['st_'+qp.stance]||qp.stance} — ${qp.question}`);
 tip.style.display='block';moveTip(ev);}
function moveTip(ev){const pad=14,w=tip.offsetWidth,hgt=tip.offsetHeight;let x=ev.clientX+pad,y=ev.clientY+pad;
 if(x+w>innerWidth-8)x=ev.clientX-w-pad;if(y+hgt>innerHeight-8)y=ev.clientY-hgt-pad;tip.style.left=x+'px';tip.style.top=y+'px';}
const hideTip=()=>tip.style.display='none';

// ---------- legend (focus direction)
function legend(id){const box=document.getElementById(id);G.categories.forEach(c=>{const b=h('button',{class:'chip','data-cat':c.name,'aria-pressed':'false'},box);
 h('span',{class:'sw'+(c.slot?'':' o')},b).style.background=c.slot?`var(--s${c.slot})`:'';h('span',null,b,`${c.label} (${c.n})`);
 b.onclick=()=>{state.focus=state.focus===c.name?null:c.name;state.sel=null;applyState();};});}
function searchBox(id){const i=document.getElementById(id);i.oninput=()=>{state.q=i.value;document.querySelectorAll('input[type=search]').forEach(o=>{if(o!==i)o.value=i.value});applyState();};}

function bindNode(g,n,v,els){g.addEventListener('pointerenter',ev=>showTip(ev,n));g.addEventListener('pointermove',moveTip);g.addEventListener('pointerleave',hideTip);
 g.addEventListener('click',ev=>{ev.stopPropagation();select(n.key);});if(!v.nodes.has(n.key))v.nodes.set(n.key,[]);v.nodes.get(n.key).push(...els);}

// ---------- pan & zoom for every chart: Ctrl/⌘+wheel (also trackpad pinch) or buttons; drag to pan.
// Plain wheel keeps scrolling the page. Zooming in enlarges nodes, which makes crowded ones easy to click.
function panZoom(svg,onBg){let vb=svg.getAttribute('viewBox').split(/\s+/).map(Number);const vb0=vb.slice();
 const set=()=>svg.setAttribute('viewBox',vb.join(' '));
 const zoom=(z,fx=0.5,fy=0.5)=>{const nw=Math.min(vb0[2]*1.5,Math.max(vb0[2]/10,vb[2]*z)),k=nw/vb[2],nh=vb[3]*k;vb=[vb[0]+(vb[2]-nw)*fx,vb[1]+(vb[3]-nh)*fy,nw,nh];set();};
 const bar=h('div',{class:'zoombar'});svg.parentNode.insertBefore(bar,svg);
 [['＋',L.zoom_in,()=>zoom(1/1.4)],['－',L.zoom_out,()=>zoom(1.4)],['⟲',L.zoom_reset,()=>{vb=vb0.slice();set();}]].forEach(([t,lab,f])=>{const b=h('button',{class:'btn','aria-label':lab,title:lab},bar,t);b.onclick=f;});
 h('span',{class:'hint'},bar,L.zoom_hint);
 let drag=null,moved=false;const onNode=ev=>ev.target.closest('.hit,.qlabel,a,button');
 svg.addEventListener('pointerdown',ev=>{if(onNode(ev))return;drag={x:ev.clientX,y:ev.clientY,vb:vb.slice(),id:ev.pointerId};moved=false;});
 svg.addEventListener('pointermove',ev=>{if(!drag)return;const dx=ev.clientX-drag.x,dy=ev.clientY-drag.y;
  if(!moved&&Math.abs(dx)+Math.abs(dy)>4){moved=true;try{svg.setPointerCapture(drag.id)}catch(e){}svg.style.cursor='grabbing';}
  if(moved){const s=vb[2]/svg.clientWidth;vb[0]=drag.vb[0]-dx*s;vb[1]=drag.vb[1]-dy*s;set();}});
 svg.addEventListener('pointerup',ev=>{if(drag&&!moved&&onBg)onBg();drag=null;svg.style.cursor='';});
 svg.addEventListener('wheel',ev=>{if(!(ev.ctrlKey||ev.metaKey))return;ev.preventDefault();const r=svg.getBoundingClientRect();
  zoom(ev.deltaY>0?1.12:1/1.12,(ev.clientX-r.left)/r.width,(ev.clientY-r.top)/r.height);},{passive:false});}

// ---------- timeline: one lane per direction (lanes are facets, so identity never relies on color)
function buildTimeline(){legend('legend-tl');searchBox('q-tl');
 const svg=document.getElementById('tl');const W=1100,left=170,right=20,top=28,ROWH=30;
 const t=n=>(n.date&&Date.parse(n.date.slice(0,10)))||0;const ts=N.map(t).filter(x=>x>0);const UND=N.some(n=>!t(n));
 let t0=Math.min(...ts),t1=Math.max(...ts);const pad=(t1-t0)*0.03||864e5*30;t0-=pad;t1+=pad;
 const RW=UND?70:0,X=v=>v?left+(v-t0)/(t1-t0)*(W-left-right-RW):W-right-RW/2;  // undated papers: own column at the right
 // greedy packing into as many rows as needed: a node goes to the first row where it clears the previous one
 const lanes=G.categories.map(c=>{const ends=[];return N.filter(n=>n.category===c.name).sort((a,b)=>X(t(a))-X(t(b))).map(n=>{
   const r=Math.min(12,4+2*Math.log1p(n.citations||0)),x=X(t(n));let row=ends.findIndex(e=>x-e>=2*12+6);if(row<0){row=ends.length;ends.push(0);}ends[row]=x;return{n,x,r,row};});});
 const laneHs=lanes.map(l=>Math.max(70,28+ROWH*(1+Math.max(0,...l.map(p=>p.row)))));
 const laneTop=laneHs.map((_,i)=>top+laneHs.slice(0,i).reduce((a,b)=>a+b,0));
 const H=top+laneHs.reduce((a,b)=>a+b,0)+10;svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
 const ax=el('g',{class:'axis'},svg);const y0=new Date(t0).getFullYear(),y1=new Date(t1).getFullYear();
 const span=y1-y0,step=span>24?5:span>12?2:1;
 for(let y=y0;y<=y1+1;y++){if(y%step)continue;const x=X(Date.UTC(y,0,1));if(x<left||x>W-right-34-RW)continue;el('line',{x1:x,x2:x,y1:top-6,y2:H-6},ax);el('text',{x:x+3,y:top-10},ax,y);}
 if(UND)el('text',{x:W-right-RW/2,y:top-10,'text-anchor':'middle'},ax,L.undated);
 const pos=new Map();
 G.categories.forEach((c,i)=>{const yTop=laneTop[i],laneH=laneHs[i];if(i)el('line',{class:'lane-sep',x1:0,x2:W,y1:yTop,y2:yTop},svg);
  el('text',{class:'lane-label',x:8,y:yTop+laneH/2},svg,short(c.label,20));el('text',{class:'lane-count',x:8,y:yTop+laneH/2+16},svg,`${c.n} ${L.papers}`);
  lanes[i].forEach(({n,x,r,row})=>pos.set(n.key,{x,y:yTop+14+row*ROWH+ROWH/2,r}));});
 const v={nodes:new Map(),edges:[]};views.push(v);
 const eg=el('g',null,svg);
 G.edges.forEach(([s,tk])=>{const a=pos.get(s),b=pos.get(tk);if(!a||!b)return;const mx=(a.x+b.x)/2,my=Math.min(a.y,b.y)-Math.abs(a.x-b.x)*0.12-8;
  v.edges.push({s,t:tk,el:el('path',{class:'e',d:`M${a.x},${a.y} Q${mx},${my} ${b.x},${b.y}`},eg)});});
 const ng=el('g',null,svg);
 N.forEach(n=>{const p=pos.get(n.key);if(!p)return;const g=el('g',null,ng);
  const c=el('circle',{class:'n'+(isOther(n.category)?' o':''),cx:p.x,cy:p.y,r:p.r,fill:color(n.category)},g);
  el('circle',{class:'hit',cx:p.x,cy:p.y,r:p.r+6},g);bindNode(g,n,v,[c]);});
 panZoom(svg,()=>{if(state.sel){state.sel=null;applyState();}});
}

// ---------- network: force layout computed once, then pan/zoom
function buildNetwork(){legend('legend-net');searchBox('q-net');
 const svg=document.getElementById('net');
 let seed=7;const rnd=()=>(seed=(seed*16807)%2147483647)/2147483647;
 const ci=new Map(G.categories.map((c,i)=>[c.name,i]));const K=G.categories.length;
 const deg=k=>outE.get(k).size+inE.get(k).size;
 // simulate only connected papers; isolated ones go to a labelled band below (otherwise they drift far
 // away, the fit-to-view zooms out and every node and label becomes unreadably small)
 const conn=N.filter(d=>deg(d.key)>0),iso=N.filter(d=>deg(d.key)===0);
 const P=conn.map(d=>{const a=(ci.get(d.category)/K)*Math.PI*2;return{k:d.key,x:Math.cos(a)*200+rnd()*80,y:Math.sin(a)*200+rnd()*80,vx:0,vy:0,c:d.category};});
 const n=P.length,idx=new Map(P.map((p,i)=>[p.k,i]));const E=G.edges.map(([s,t])=>[idx.get(s),idx.get(t)]);
 const iters=n>400?200:n>200?320:480;
 for(let it=0;it<iters;it++){const alpha=1-it/iters;
  for(let i=0;i<n;i++)for(let j=i+1;j<n;j++){let dx=P[i].x-P[j].x,dy=P[i].y-P[j].y,d2=dx*dx+dy*dy+0.01;if(d2>90000)continue;const f=900/d2*alpha;dx*=f;dy*=f;P[i].vx+=dx;P[i].vy+=dy;P[j].vx-=dx;P[j].vy-=dy;}
  E.forEach(([a,b])=>{const dx=P[b].x-P[a].x,dy=P[b].y-P[a].y,d=Math.sqrt(dx*dx+dy*dy)+0.01,f=(d-60)*0.03*alpha;P[a].vx+=dx/d*f;P[a].vy+=dy/d*f;P[b].vx-=dx/d*f;P[b].vy-=dy/d*f;});
  const cen=new Map();P.forEach(p=>{const c=cen.get(p.c)||{x:0,y:0,n:0};c.x+=p.x;c.y+=p.y;c.n++;cen.set(p.c,c);});
  P.forEach(p=>{const c=cen.get(p.c);p.vx+=(c.x/c.n-p.x)*0.008*alpha-p.x*0.012*alpha;p.vy+=(c.y/c.n-p.y)*0.008*alpha-p.y*0.012*alpha;p.vx*=0.82;p.vy*=0.82;p.x+=p.vx;p.y+=p.vy;});}
 const R=d=>Math.min(18,4+2.4*Math.sqrt(d.local_in));
 // scale the connected layout into a fixed frame so radii and font sizes stay in screen-like units
 const FW=1100,FH=Math.max(420,Math.min(760,280+n*4)),m=50;
 let minX=1e9,minY=1e9,maxX=-1e9,maxY=-1e9;P.forEach(p=>{minX=Math.min(minX,p.x);minY=Math.min(minY,p.y);maxX=Math.max(maxX,p.x);maxY=Math.max(maxY,p.y);});
 const sc=Math.min((FW-2*m)/Math.max(1,maxX-minX),(FH-2*m)/Math.max(1,maxY-minY));
 const ox=(FW-(maxX-minX)*sc)/2,oy=(FH-(maxY-minY)*sc)/2;
 P.forEach(p=>{p.x=ox+(p.x-minX)*sc;p.y=oy+(p.y-minY)*sc;});
 const perRow=Math.max(1,Math.floor((FW-2*m)/30)),rows=Math.ceil(iso.length/perRow),bandY=FH+30;
 iso.sort((a,b)=>(ci.get(a.category)-ci.get(b.category))||String(a.date).localeCompare(String(b.date))).forEach((d,i)=>{
  const p={k:d.key,x:m+(i%perRow)*30+10,y:bandY+28+Math.floor(i/perRow)*30,c:d.category};idx.set(d.key,P.length);P.push(p);});
 let vb=[0,0,FW,iso.length?bandY+28+rows*30+10:FH];const vb0=vb.slice();const setVB=()=>svg.setAttribute('viewBox',vb.join(' '));setVB();
 if(iso.length){el('line',{x1:m,x2:FW-m,y1:bandY,y2:bandY,stroke:'var(--grid)'},svg);el('text',{x:m,y:bandY+16,'font-size':'12'},svg,`${L.isolated} (${iso.length})`);}
 const defs=el('defs',null,svg);const mk=el('marker',{id:'arw',viewBox:'0 0 10 10',refX:'10',refY:'5',markerWidth:'5',markerHeight:'5',orient:'auto-start-reverse'},defs);el('path',{d:'M0,0 L10,5 L0,10 z',fill:'var(--muted)'},mk);
 const v={nodes:new Map(),edges:[]};views.push(v);
 const eg=el('g',null,svg);
 G.edges.forEach(([s,t])=>{const a=P[idx.get(s)],b=P[idx.get(t)],rb=R(byKey.get(t))+2;const dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)||1;
  v.edges.push({s,t,el:el('line',{class:'e',x1:a.x,y1:a.y,x2:b.x-dx/d*rb,y2:b.y-dy/d*rb,'marker-end':'url(#arw)'},eg)});});
 const ng=el('g',null,svg),lg=el('g',null,svg);
 const top=new Set([...conn].sort((a,b)=>b.pagerank-a.pagerank).slice(0,Math.min(14,Math.ceil(n/8))).map(d=>d.key));
 const placed=[];// label boxes already drawn; skip a label rather than overlap one (approx. 6.2px per char)
 const fits=(x,y,w)=>!placed.some(b=>x<b.x+b.w&&x+w>b.x&&y-11<b.y&&y+3>b.y-11);
 N.forEach(d=>{const p=P[idx.get(d.key)];const g=el('g',null,ng);
  const c=el('circle',{class:'n'+(isOther(d.category)?' o':''),cx:p.x,cy:p.y,r:R(d),fill:color(d.category)},g);
  el('circle',{class:'hit',cx:p.x,cy:p.y,r:R(d)+6},g);const els=[c];
  if(top.has(d.key)){const txt=short(d.title,34),w=txt.length*6.2;
   for(const dy of [4,-10,18]){const x=p.x+R(d)+3,y=p.y+dy;if(fits(x,y,w)){placed.push({x,y,w});els.push(el('text',{class:'nl',x,y},lg,txt));break;}}}
  bindNode(g,d,v,els);});
 panZoom(svg,()=>{if(state.sel){state.sel=null;applyState();}});
}

// ---------- question lineage: one lane per research question (tree order), shape = stance
function drawMark(parent,stance,x,y,r,attrs){const a=Object.assign({},attrs);
 if(stance==='evaluates')return el('rect',Object.assign(a,{x:x-r*0.9,y:y-r*0.9,width:r*1.8,height:r*1.8,rx:1.5}),parent);
 if(stance==='challenges'){const s=r*1.3;return el('path',Object.assign(a,{d:`M${x},${y-s}L${x+s},${y}L${x},${y+s}L${x-s},${y}Z`}),parent);}
 if(stance==='surveys'){const s=r*1.25;return el('path',Object.assign(a,{d:`M${x},${y-s}L${x+s*0.95},${y+s*0.7}L${x-s*0.95},${y+s*0.7}Z`}),parent);}
 return el('circle',Object.assign(a,{cx:x,cy:y,r}),parent);}
function stanceLegend(box){['proposes','extends','reframes','evaluates','challenges','surveys'].forEach(s=>{
 const sp=h('span',{class:'chip'},box);sp.style.cursor='default';const svg=el('svg',{width:'14',height:'14',viewBox:'0 0 14 14',class:'mk'},sp);svg.style.width='14px';
 drawMark(svg,s==='extends'||s==='reframes'?'proposes':s,7,7,4.2,{fill:'var(--ink2)'});if(s==='reframes')el('circle',{cx:7,cy:7,r:6.3,fill:'none',stroke:'var(--ink2)','stroke-width':'1.1'},svg);
 sp.appendChild(document.createTextNode(L['st_'+s]));});}
function focusQuestion(id){state.qfocus=(id&&state.qfocus===id)?null:id;state.sel=null;renderQCard(state.qfocus);applyState();
 const sec=document.getElementById('tab-questions');if(!sec.hidden&&state.qfocus)document.getElementById('qcard').scrollIntoView({behavior:'smooth',block:'nearest'});}
function buildQuestions(){stanceLegend(document.getElementById('legend-q'));searchBox('q-q');
 const svg=document.getElementById('qv');const W=1100,left=320,right=20,top=28;
 const rows=QL.map(q=>({q,h:q.depth===0?30:Math.max(40,Math.min(76,24+q.n*3.2))}));
 const H=top+rows.reduce((s,r)=>s+r.h,0)+10;svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
 const t=n=>(n.date&&Date.parse(n.date.slice(0,10)))||0;const ts=N.map(t).filter(x=>x>0);const UND=N.some(n=>!t(n));
 let t0=Math.min(...ts),t1=Math.max(...ts);const pad=(t1-t0)*0.03||864e5*30;t0-=pad;t1+=pad;const RW=UND?70:0,X=v=>v?left+(v-t0)/(t1-t0)*(W-left-right-RW):W-right-RW/2;
 const ax=el('g',{class:'axis'},svg);const y0=new Date(t0).getFullYear(),y1=new Date(t1).getFullYear(),step=(y1-y0)>24?5:(y1-y0)>12?2:1;
 for(let y=y0;y<=y1+1;y++){if(y%step)continue;const x=X(Date.UTC(y,0,1));if(x<left||x>W-right-34-RW)continue;el('line',{x1:x,x2:x,y1:top-6,y2:H-6},ax);el('text',{x:x+3,y:top-10},ax,y);}
 if(UND)el('text',{x:W-right-RW/2,y:top-10,'text-anchor':'middle'},ax,L.undated);
 const pos=new Map();let yc=top;
 rows.forEach(({q,h:rh})=>{const bg=el('rect',{class:'qsel-bg'+(q.depth===0?' qband':''),'data-q':q.id,x:0,y:yc,width:W,height:rh},svg);
  el('line',{class:'lane-sep',x1:0,x2:W,y1:yc,y2:yc},svg);
  const lx=8+q.depth*16,lab=el('text',{class:'qlabel'+(q.depth===0?' root':''),x:lx,y:yc+(q.depth===0?19:rh/2-2)},svg,`${q.id} ${short(q.short,q.depth===0?26:22)}`);
  lab.addEventListener('click',ev=>{ev.stopPropagation();focusQuestion(q.id);});lab.appendChild(el('title',null,null,q.text));
  if(q.depth>0){const st=q.status.map(s=>L['status_'+s]||s).join(' · ');el('text',{class:'qmeta',x:lx,y:yc+rh/2+13},svg,`${q.n} ${L.papers}${st?' · '+st:''}`);}
  else el('text',{class:'qmeta',x:W-right,y:yc+19,'text-anchor':'end'},svg,`${q.n_all} ${L.papers}`);
  const mem=q.papers.map(k=>byKey.get(k)).filter(Boolean).sort((a,b)=>X(t(a))-X(t(b)));const slots=[];
  mem.forEach(n=>{const r=Math.min(10,4+1.8*Math.log1p(n.citations||0)),x=X(t(n)),nr=Math.max(1,Math.floor((rh-12)/16));
   let best=0,bg2=-1;for(let k=0;k<nr;k++){const g2=x-(slots[k]??-1e9);if(g2>22){best=k;break;}if(g2>bg2){bg2=g2;best=k;}}
   slots[best]=x;pos.set(n.key,{x,y:yc+8+(nr===1?(rh-16)/2:(best+0.5)*(rh-16)/nr),r});});
  yc+=rh;});
 const v={nodes:new Map(),edges:[]};views.push(v);const eg=el('g',null,svg);
 G.edges.forEach(([s,tk])=>{const a=pos.get(s),b=pos.get(tk);if(!a||!b)return;const mx=(a.x+b.x)/2,my=Math.min(a.y,b.y)-Math.abs(a.x-b.x)*0.1-6;
  const ch=QP[s]&&QP[s].stance==='challenges';v.edges.push({s,t:tk,el:el('path',{class:'e'+(ch?' ch':''),d:`M${a.x},${a.y} Q${mx},${my} ${b.x},${b.y}`},eg)});});
 const ng=el('g',null,svg);
 N.forEach(n=>{const p=pos.get(n.key);if(!p)return;const g=el('g',null,ng);const st=(QP[n.key]||{}).stance;
  const els=[drawMark(g,st,p.x,p.y,p.r,{class:'n'+(isOther(n.category)?' o':''),fill:color(n.category)})];
  if(st==='reframes')els.push(el('circle',{class:'ring',cx:p.x,cy:p.y,r:p.r+3.5},g));
  el('circle',{class:'hit',cx:p.x,cy:p.y,r:p.r+6},g);bindNode(g,n,v,els);});
 panZoom(svg,()=>{if(state.sel){state.sel=null;applyState();}else if(state.qfocus){focusQuestion(null);}});
 renderQCard(state.qfocus);}
function qChip(parent,id,count){const q=QM.get(id);if(!q)return;const b=h('button',{class:'qchip'},parent,`${q.id} ${q.short}${count?' ×'+count:''}`);b.title=q.text;b.onclick=()=>focusQuestion(id);}
function renderQCard(id){const box=document.getElementById('qcard');if(!box)return;box.replaceChildren();
 if(!id){h('h2',{class:'sec'},box,L.q_overview);
  table(box,QL,[{label:L.q_col,cell:(td,q)=>{td.style.paddingLeft=(8+q.depth*16)+'px';const a=h('a',{href:'#'},td,`${q.id} ${q.text}`);if(!q.depth)a.style.fontWeight='600';a.onclick=ev=>{ev.preventDefault();focusQuestion(q.id);};}},
   {label:L.q_papers,num:1,cell:(td,q)=>td.textContent=q.n_all},
   {label:L.q_period,num:1,cell:(td,q)=>td.textContent=q.first?`${q.first.slice(0,4)}–${q.last.slice(0,4)}`:''},
   {label:L.q_momentum,num:1,cell:(td,q)=>td.textContent=q.momentum},
   {label:L.q_status,cell:(td,q)=>q.status.forEach(s=>h('span',{class:'tag'},td,L['status_'+s]||s))},
   {label:L.q_builds_on,cell:(td,q)=>q.builds_on.slice(0,3).forEach(b=>h('span',{class:'tag'},td,`${b.q} ×${b.count}`))}]);return;}
 const q=QM.get(id);h('button',{class:'btn'},box,L.back).onclick=()=>focusQuestion(null);
 const t=h('h2',{class:'sec'},box,`${q.id} ${q.text}`);t.style.marginTop='12px';
 const meta=h('div',{class:'meta'},box);meta.style.color='var(--ink2)';meta.style.fontSize='13px';
 meta.textContent=`${L.q_period} ${q.first||'?'} – ${q.last||'?'} · ${q.n_all} ${L.papers} · ${L.q_momentum} ${q.momentum}`;
 const tags=h('div',null,box);q.status.forEach(s=>h('span',{class:'tag'},tags,L['status_'+s]||s));
 Object.entries(q.stances).forEach(([s,c])=>h('span',{class:'tag st-'+s},tags,`${L['st_'+s]||s} ${c}`));
 if(q.builds_on.length){h('h4',null,box,L.q_builds_on);const d=h('div',null,box);q.builds_on.forEach(b=>qChip(d,b.q,b.count));}
 if(q.led_to.length){h('h4',null,box,L.q_led_to);const d=h('div',null,box);q.led_to.forEach(b=>qChip(d,b.q,b.count));}
 const kids=QL.filter(x=>x.parent===q.id);if(kids.length){h('h4',null,box,'⤷');const d=h('div',null,box);kids.forEach(k=>qChip(d,k.id,0));}
 h('h4',null,box,`${L.q_papers} (${q.papers.length})`);
 q.papers.map(k=>byKey.get(k)).filter(Boolean).sort((a,b)=>String(a.date).localeCompare(String(b.date))).forEach(n=>{const p=QP[n.key]||{};const it=h('div',{class:'qitem'},box);
  const top=h('div',null,it);h('span',{class:'tag st-'+p.stance},top,L['st_'+p.stance]||p.stance||'?');paperLink(top,n.key);
  if(p.question)h('div',{class:'qq'},it,p.question);
  const sub=[p.approach?`${L.q_approach}:${p.approach}`:'',p.finding?`${L.q_finding}:${p.finding}`:''].filter(Boolean).join('  ·  ');if(sub)h('div',{class:'qa'},it,sub);});}

// ---------- detail drawer
function paperLink(parent,k){const n=byKey.get(k);const a=h('a',{href:'#',class:'linkish'},parent,`${short(n.title,90)} (${yr(n)})`);a.onclick=ev=>{ev.preventDefault();state.sel=k;applyState();};return a;}
function renderDrawer(){const dr=document.getElementById('drawer'),main=document.getElementById('main');
 if(!state.sel){dr.hidden=true;main.classList.add('nodrawer');return;}
 dr.hidden=false;main.classList.remove('nodrawer');dr.replaceChildren();const n=byKey.get(state.sel);
 h('h3',null,dr,n.title);
 const meta=h('div',{class:'meta'},dr);const sw=h('span',{class:'sw'+(isOther(n.category)?' o':'')},meta);sw.style.display='inline-block';sw.style.marginRight='6px';if(!isOther(n.category))sw.style.background=color(n.category);
 meta.appendChild(document.createTextNode(`${catLabel(n.category)} · ${yr(n)} · ${L.citations} ${n.citations??'?'} · ${L.cpy} ${n.cpy} · ${L.local_in} ${n.local_in}${n.withdrawn?' · '+L.withdrawn:''}`));
 if(n.authors&&n.authors.length)h('div',{class:'meta'},dr,n.authors.join(', ')+(n.venue?' — '+n.venue:''));
 if(n.pub){const b=h('div',null,dr);b.style.margin='2px 0 6px';pubBadges(b,n.pub);}
 if(n.roles.length){const r=h('div',null,dr);n.roles.forEach(x=>h('span',{class:'role'},r,roleName[x]));}
 const qp=QP[n.key];
 if(qp){h('h4',null,dr,L.research_q);const qq=QM.get(qp.q);
  const line=h('div',null,dr);h('span',{class:'tag st-'+qp.stance},line,L['st_'+qp.stance]||qp.stance);
  if(qq){const c=h('button',{class:'qchip'},line,`${qq.id} ${qq.short}`);c.onclick=()=>{show('questions');focusQuestion(qq.id);};}
  h('div',{class:'abs'},dr,qp.question).style.color='var(--ink)';
  if(qp.approach)h('div',{class:'abs'},dr,`${L.q_approach}:${qp.approach}`);
  if(qp.finding)h('div',{class:'abs'},dr,`${L.q_finding}:${qp.finding}`);}
 const act=h('div',{class:'toolbar'},dr);act.style.marginTop='10px';
 if(n.url){const a=h('a',{href:n.url,target:'_blank',rel:'noopener',class:'btn'},act,L.open);a.style.textDecoration='none';}
 h('button',{class:'btn'},act,L.show_tl).onclick=()=>show('timeline');h('button',{class:'btn'},act,L.show_net).onclick=()=>show('network');
 h('button',{class:'btn'},act,L.clear).onclick=()=>{state.sel=null;applyState();};
 if(n.note){h('h4',null,dr,L.note);h('div',{class:'abs'},dr,n.note);}
 const lin=lineage(n.key);
 const sec=(title,set,direct)=>{h('h4',null,dr,`${title} — ${set.size}`);if(!set.size){h('div',{class:'muted'},dr,L.none);return;}
  const ul=h('ul',null,dr);[...set].sort((a,b)=>(direct.has(b)-direct.has(a))||String(byKey.get(a).date).localeCompare(String(byKey.get(b).date))).slice(0,40).forEach(k=>{const li=h('li',null,ul);paperLink(li,k);if(direct.has(k))li.style.fontWeight='600';});};
 sec(L.builds_on,lin.anc,outE.get(n.key));sec(L.built_upon,lin.desc,inE.get(n.key));
 if(n.abstract){h('h4',null,dr,L.abstract);h('div',{class:'abs'},dr,n.abstract+(n.abstract.length>=700?'…':''));}
}

// ---------- tables (question overview, publication)
function table(parent,rows,cols){const w=h('div',{class:'tablewrap'},parent),t=h('table',null,w),tr=h('tr',null,h('thead',null,t));
 cols.forEach(c=>h('th',{class:c.num?'num':''},tr,c.label));const tb=h('tbody',null,t);
 rows.forEach(r=>{const row=h('tr',null,tb);cols.forEach(c=>{const td=h('td',{class:c.num?'num':''},row);c.cell(td,r);});});}

// ---------- publication status & venue tiers (ordinal ramp --t1..--t4; unranked = --other)
const PUBD=['conference','journal','workshop','published'],ZONES=['1区','2区','3区','4区'];
const zoneLabel=k=>L.zone?k:'Zone '+k[0];  // stats keys are always '1区'…
function pubBadges(parent,p){const add=(t,cls)=>h('span',{class:'tag'+(cls?' '+cls:'')},parent,t);
 add(L['pt_'+p.pub_type]||p.pub_type);
 if(p.ccf)add(`CCF-${p.ccf}`,'tier');
 if(p.cas_zone)add(`${L.cas} ${p.cas_zone}${L.zone}${p.cas_top?' Top':''}`,'tier');
 if(p.jcr_q)add(`JCR ${p.jcr_q}${p.jcr_if?' · IF '+p.jcr_if:''}`,'tier');
 if(p.xr_zone)add(`${L.xr} ${p.xr_zone}${L.zone}${p.xr_top?' Top':''}`);
 if(p.warning)add(`⚠ ${L.warning}: ${p.warning}`,'warn');
 if(p.has_arxiv&&p.pub_type!=='arxiv-only')add('+ arXiv');}
function barTip(b,title,v){b.addEventListener('pointerenter',ev=>{tip.replaceChildren();h('b',null,tip,title);h('div',{class:'m'},tip,`${v} ${L.papers}`);tip.style.display='block';moveTip(ev);});
 b.addEventListener('pointermove',moveTip);b.addEventListener('pointerleave',hideTip);}
function hbars(parent,title,rows,note){const card=h('div',{class:'card'},parent);h('h5',null,card,title);
 const W=320,lw=96,rh=26,H=rows.length*rh+4,mx=Math.max(1,...rows.map(r=>r.v));
 const svg=el('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':title},card);
 el('line',{x1:lw,x2:lw,y1:0,y2:H,stroke:'var(--axis)'},svg);
 rows.forEach((r,i)=>{const y=i*rh+4,bw=r.v/mx*(W-lw-40);el('text',{x:0,y:y+14},svg,r.label);
  if(r.v){const b=el('rect',{x:lw,y:y+3,width:Math.max(3,bw),height:rh-10,rx:3,fill:r.fill},svg);barTip(b,`${title} · ${r.label}`,r.v);
   const hit=el('rect',{x:lw,y:y,width:W-lw,height:rh,fill:'transparent'},svg);barTip(hit,`${title} · ${r.label}`,r.v);}
  el('text',{class:'val',x:lw+(r.v?Math.max(3,bw):0)+6,y:y+14},svg,r.v);});
 if(note)h('div',{class:'hint'},card,note);}
function zoneRows(counts,prefix,keys,fills){return keys.map((k,i)=>{const v=Object.entries(counts).filter(([z])=>z.split(' ')[0]===k).reduce((s,[,c])=>s+c,0);
 const top=counts[k+' Top']||0;return{label:prefix(k)+(top?` (Top ${top})`:''),v,fill:fills[i]};});}
function buildPub(){const box=document.getElementById('pubview'),A=VS.all,T=A.types;
 const sum=(o,ks)=>ks.reduce((s,k)=>s+(o[k]||0),0);const pubd=sum(T,PUBD),jn=T.journal||0;
 const tiles=h('div',{class:'tiles'},box);
 const tile=(v,k,sub)=>{const t=h('div',{class:'tile'},tiles);h('div',{class:'v'},t,v);h('div',{class:'k'},t,k);if(sub)h('div',{class:'s'},t,sub);};
 tile(pubd,L.published,`${Math.round(100*pubd/A.n)}% · ${A.n} ${L.papers}`);
 tile(sum(T,['arxiv-only','preprint']),L.preprint_only,`${L.arxiv_only} ${T['arxiv-only']||0}`);
 tile(sum(A.ccf,['A','B']),L.ccf_ab,`${pubd} ${L.of_published}`);
 tile(Object.entries(A.cas).filter(([k])=>/^[12]/.test(k)).reduce((s,[,c])=>s+c,0),L.cas12,`${jn} ${L.of_journals}`);
 h('h2',{class:'sec'},box,L.pub_status);let mult=h('div',{class:'mult'},box);
 hbars(mult,L.pub_status,['conference','journal','workshop','published','arxiv-only','preprint','thesis','unknown'].filter(k=>T[k]).map(k=>({label:L['pt_'+k],v:T[k],fill:PUBD.includes(k)?'var(--t2)':'var(--other)'})));
 h('h2',{class:'sec'},box,L.pub_tiers);mult=h('div',{class:'mult'},box);
 const F=['var(--t1)','var(--t2)','var(--t3)','var(--t4)'];
 hbars(mult,'CCF',[...['A','B','C'].map((k,i)=>({label:`CCF-${k}`,v:A.ccf[k]||0,fill:F[i]})),{label:L.unranked,v:A.ccf['无']||0,fill:'var(--other)'}],L.ccf_note);
 hbars(mult,L.cas,[...zoneRows(A.cas,zoneLabel,ZONES,F),{label:L.unranked,v:A.cas['未收录']||0,fill:'var(--other)'}],L.cas_note);
 hbars(mult,'JCR',[...['Q1','Q2','Q3','Q4'].map((k,i)=>({label:k,v:A.jcr[k]||0,fill:F[i]})),{label:L.unranked,v:A.jcr['未收录']||0,fill:'var(--other)'}],L.jcr_note);
 if(A.xr)hbars(mult,L.xr,zoneRows(A.xr,zoneLabel,ZONES,F),L.xr_note);
 // by year: stacked columns, published / preprint only / thesis (2px surface gap between segments)
 h('h2',{class:'sec'},box,L.pub_by_year);
 const lg=h('div',null,box);[[L.published,'var(--t2)'],[L.preprint_only,'var(--t4)'],[L.thesis,'var(--other)']].forEach(([t,c])=>{const s=h('span',{class:'lg'},lg);h('i',null,s).style.background=c;s.appendChild(document.createTextNode(t));});
 const Y=Object.entries(VS.by_year).map(([y,B])=>[(!y||y==='None'||y==='null')?L.undated:y,B]),W=1100,H=220,b=22,l=30;const mx=Math.max(1,...Y.map(([,B])=>B.n));
 const svg=el('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':L.pub_by_year},h('div',{class:'card'},box));
 const bwid=Math.min(46,(W-l-10)/Y.length-8);
 for(let g=0;g<=mx;g+=Math.max(1,Math.ceil(mx/4/5)*5)){const y=H-b-g/mx*(H-b-16);el('line',{x1:l,x2:W,y1:y,y2:y,stroke:'var(--grid)'},svg);el('text',{x:0,y:y+4,'font-size':'11'},svg,g);}
 Y.forEach(([y,B],i)=>{const x=l+8+i*((W-l-10)/Y.length);let base=H-b;
  [[sum(B.types,PUBD),'var(--t2)',L.published],[sum(B.types,['arxiv-only','preprint','unknown']),'var(--t4)',L.preprint_only],[B.types.thesis||0,'var(--other)',L.thesis]].forEach(([v,c,t])=>{if(!v)return;
   const hh=v/mx*(H-b-16);const r=el('rect',{x,y:base-hh+1,width:bwid,height:Math.max(1,hh-2),rx:2,fill:c},svg);barTip(r,`${y} · ${t}`,v);base-=hh;});
  el('text',{class:'val',x:x+bwid/2,y:base-4,'text-anchor':'middle','font-size':'11'},svg,B.n);
  el('text',{x:x+bwid/2,y:H-6,'text-anchor':'middle','font-size':'11'},svg,y);});
 const yt=Y.map(([y,B])=>({y,B}));
 table(box,yt,[{label:L.year,cell:(td,r)=>td.textContent=r.y},{label:L.papers,num:1,cell:(td,r)=>td.textContent=r.B.n},
  {label:L.published,num:1,cell:(td,r)=>td.textContent=sum(r.B.types,PUBD)},{label:L.arxiv_only,num:1,cell:(td,r)=>td.textContent=r.B.types['arxiv-only']||0},
  {label:'CCF A/B',num:1,cell:(td,r)=>td.textContent=sum(r.B.ccf,['A','B'])},{label:L.cas12,num:1,cell:(td,r)=>td.textContent=Object.entries(r.B.cas).filter(([k])=>/^[12]/.test(k)).reduce((s,[,c])=>s+c,0)}]);
 h('h2',{class:'sec'},box,L.pub_by_dir);
 table(box,Object.entries(VS.by_category).map(([c,B])=>({c,B})),[{label:L.direction,cell:(td,r)=>td.textContent=catLabel(r.c)},{label:L.papers,num:1,cell:(td,r)=>td.textContent=r.B.n},
  {label:L.published,num:1,cell:(td,r)=>td.textContent=sum(r.B.types,PUBD)},{label:L.arxiv_only,num:1,cell:(td,r)=>td.textContent=r.B.types['arxiv-only']||0},
  ...['A','B','C'].map(k=>({label:'CCF-'+k,num:1,cell:(td,r)=>td.textContent=r.B.ccf[k]||0})),
  {label:L.cas12,num:1,cell:(td,r)=>td.textContent=Object.entries(r.B.cas).filter(([k])=>/^[12]/.test(k)).reduce((s,[,c])=>s+c,0)},
  {label:'JCR Q1',num:1,cell:(td,r)=>td.textContent=r.B.jcr.Q1||0}]);
 // paper list with filters
 h('h2',{class:'sec'},box,L.pub_list);const bar=h('div',{class:'toolbar'},box),listBox=h('div',null,box);
 const filters=[[L.all,()=>true],['CCF-A',p=>p.ccf==='A'],['CCF-B',p=>p.ccf==='B'],['CCF-C',p=>p.ccf==='C'],[L.cas12,p=>p.cas_zone&&p.cas_zone<=2],['JCR Q1',p=>p.jcr_q==='Q1'],
  [L.published,p=>PUBD.includes(p.pub_type)],[L.arxiv_only,p=>p.pub_type==='arxiv-only'],[L.thesis,p=>p.pub_type==='thesis']];
 const score=p=>(p.ccf?{A:100,B:60,C:30}[p.ccf]:0)+(p.cas_zone?(5-p.cas_zone)*6:0)+(p.jcr_q?(5-+p.jcr_q[1]):0)+(PUBD.includes(p.pub_type)?1:0);
 const sorts={tier:(a,b)=>score(b.pub)-score(a.pub)||String(b.date).localeCompare(String(a.date)),
  new:(a,b)=>String(b.date||'').localeCompare(String(a.date||''))||score(b.pub)-score(a.pub),
  old:(a,b)=>String(a.date||'9').localeCompare(String(b.date||'9'))||score(b.pub)-score(a.pub),
  title:(a,b)=>a.title.localeCompare(b.title)};
 const ctl=h('div',{class:'toolbar'},bar.parentNode);bar.parentNode.insertBefore(ctl,listBox);
 const qi=h('input',{type:'search',placeholder:L.pub_search,'aria-label':L.pub_search},ctl);
 const lab=h('label',{class:'hint'},ctl,L.sort+' ');const sel=h('select',{'aria-label':L.sort},lab);
 [['tier',L.sort_tier],['new',L.sort_new],['old',L.sort_old],['title',L.sort_title]].forEach(([v,t])=>h('option',{value:v},sel,t));
 let cur=0;const draw=()=>{listBox.replaceChildren();bar.querySelectorAll('.chip').forEach((c,i)=>c.setAttribute('aria-pressed',i===cur));
  const q=qi.value.trim().toLowerCase();
  const rows=N.filter(n=>n.pub&&filters[cur][1](n.pub)&&(!q||n.title.toLowerCase().includes(q)||(n.pub.venue||'').toLowerCase().includes(q)||String(yr(n)).includes(q))).sort(sorts[sel.value]);
  h('div',{class:'hint'},listBox,`${rows.length} ${L.papers}`);
  table(listBox,rows,[{label:L.title,cell:(td,n)=>paperLink(td,n.key)},{label:L.year,num:1,cell:(td,n)=>td.textContent=yr(n)},
   {label:L.direction,cell:(td,n)=>td.textContent=catLabel(n.category)},{label:L.type,cell:(td,n)=>td.textContent=L['pt_'+n.pub.pub_type]||n.pub.pub_type},
   {label:L.venue,cell:(td,n)=>td.textContent=n.pub.venue||''},{label:'CCF',cell:(td,n)=>td.textContent=n.pub.ccf||''},
   {label:L.cas,cell:(td,n)=>td.textContent=n.pub.cas_zone?`${n.pub.cas_zone}${L.zone}${n.pub.cas_top?' Top':''}`:''},
   {label:'JCR',cell:(td,n)=>td.textContent=n.pub.jcr_q||''},{label:L.xr,cell:(td,n)=>td.textContent=n.pub.xr_zone?`${n.pub.xr_zone}${L.zone}`:''},
   {label:L.warning,cell:(td,n)=>{if(n.pub.warning){td.textContent='⚠ '+n.pub.warning;td.style.color='var(--warn)';}}}]);};
 filters.forEach(([t],i)=>{const c=h('button',{class:'chip','aria-pressed':'false'},bar,t);c.onclick=()=>{cur=i;draw();};});
 qi.oninput=draw;sel.onchange=draw;draw();
 h('p',{class:'hint'},box,L.pub_src);}

// ---------- narrative paper refs
document.getElementById('report').addEventListener('click',ev=>{const a=ev.target.closest('a.pref');if(!a)return;ev.preventDefault();if(byKey.has(a.dataset.key)){state.sel=a.dataset.key;applyState();}});
document.querySelectorAll('a.pref').forEach(a=>{const n=byKey.get(a.dataset.key);if(!n)return;a.title=n.title;if(!/^\d{4}\./.test(a.dataset.key))a.textContent=short(n.title,28);});

// deep links: #tab or #tab:paperKey (opens that paper's lineage)
const [startTab,startKey]=decodeURIComponent((location.hash||'#report').slice(1)).split(/:(.+)/);
if(!QG)document.getElementById('qtabbtn').hidden=true;
const startQ=startTab==='questions'&&startKey&&QM.has(startKey)?startKey:null;
if(!VS)document.getElementById('pubtabbtn').hidden=true;
show(['report','questions','timeline','network','pub'].includes(startTab)&&(startTab!=='questions'||QG)&&(startTab!=='pub'||VS)?startTab:'report');
if(startQ){focusQuestion(startQ);}else
if(startKey&&byKey.has(startKey)){state.sel=startKey;applyState();}
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
