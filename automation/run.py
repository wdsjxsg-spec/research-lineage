#!/usr/bin/env python3
"""Scheduled updates for a research-lineage project.

  daily  [--no-crawl]        crawl new papers (if enabled) -> pending additions -> collection -> collect -> analyze ->
                             questions build -> venues -> render -> placeholder list -> papers index
  weekly [--print]           claude -p phase A (review) -> daily --no-crawl -> claude -p phase B (labels, narrative) ->
                             daily --no-crawl -> narrative check. --print shows the prompt and permissions only.
  cron   [--install]         print (or install into the user's crontab) the schedule from research-lineage.json

Run from anywhere: python3 -I <skill>/automation/run.py daily --config <project>/research-lineage.json
A failing step is reported as [FAIL] and does not stop later steps (e.g. a rate-limited API still lets the page render
from cache). Setup guide: references/automation.md.
"""
import argparse, datetime as dt, os, re, shlex, shutil, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Config, config_arg, load_json, HERE, SKILL  # noqa: E402

PY = sys.executable or "python3"
SCRIPTS = os.path.join(SKILL, "scripts")
LANG_NAME = {"zh": "Chinese (简体中文)", "en": "English"}
MARK = "# research-lineage:"


def py(script, *args):
    return [PY, "-I", script, *args]


def step(name, cmd, cwd):
    print(f"--- {name}", flush=True)
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode:
        print(f"[FAIL] {name} (exit {r.returncode})", flush=True)
    return r.returncode == 0


def daily(cfg, no_crawl=False):
    c = ["--config", cfg.file]
    L = cfg["lineage"]
    crawl = cfg.get("crawl") or {}
    print(f"===== {dt.datetime.now():%F %T} daily ({cfg.root}) =====", flush=True)
    if crawl.get("enabled") and not no_crawl:
        args = ["--days", str(crawl.get("days", 14))] + (["--auto-ingest"] if crawl.get("auto_ingest") else [])
        step("crawl", py(os.path.join(HERE, "crawl.py"), *c, *args), cfg.root)
    pending = cfg.state("pending_add.txt")
    if os.path.exists(pending) and os.path.getsize(pending):
        if step("pending_add", py(os.path.join(HERE, "add_papers.py"), *c, pending), cfg.root):
            os.replace(pending, cfg.state(f"pending_add.done.{dt.date.today()}.txt"))
    step("collection", py(os.path.join(HERE, "make_collection.py"), *c), cfg.root)
    step("collect", py(os.path.join(SCRIPTS, "collect.py"), "--csv", os.path.join(L, "collection.csv"), "--out", L), cfg.root)
    labels = os.path.join(L, "labels.json")
    step("analyze", py(os.path.join(SCRIPTS, "analyze.py"), "--out", L, *(["--labels", labels] if os.path.exists(labels) else [])), cfg.root)
    if os.path.exists(os.path.join(L, "questions.json")):  # analyze rewrites graph.json, so these two come after it
        step("questions", py(os.path.join(SCRIPTS, "questions.py"), "build", "--out", L), cfg.root)
    step("venues", py(os.path.join(SCRIPTS, "venues.py"), "--out", L), cfg.root)
    r = ["--out", L, "--lang", cfg.lang]
    if os.path.exists(cfg["notes"]): r += ["--notes", cfg["notes"]]
    if cfg.get("title"): r += ["--title", cfg.get("title")]
    step("render", py(os.path.join(SCRIPTS, "render.py"), *r), cfg.root)
    step("placeholders", py(os.path.join(HERE, "placeholders.py"), *c), cfg.root)
    step("index", py(os.path.join(HERE, "build_index.py"), *c), cfg.root)
    print(f"===== {dt.datetime.now():%F %T} done =====", flush=True)


def claude_bin(cfg):
    b = cfg.get("claude_bin") or shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
    return b if os.path.exists(b) else None


def weekly_prompt(cfg):
    """Fill the template and write <state>/weekly_prompt.rendered.md; return (path, allowed tools)."""
    c = f"--config {shlex.quote(cfg.file)}"
    move = f"{PY} -I {shlex.quote(os.path.join(HERE, 'move_paper.py'))} {c}"
    check = f"{PY} -I {shlex.quote(os.path.join(HERE, 'check_narrative.py'))} {c}"
    qbuild = f"{PY} -I {shlex.quote(os.path.join(SCRIPTS, 'questions.py'))} build --out {shlex.quote(cfg.rel(cfg['lineage']))}"
    q = load_json(os.path.join(cfg["lineage"], "questions.json"), {})
    roots = [f"{x['id']} {x.get('short') or x.get('text', '')}" for x in q.get("questions", []) if not x.get("parent")]
    cats = "\n".join(f"- `{k}` — {v}" for k, v in cfg.categories.items()) or "- (see the folders under papers/)"
    auto = (cfg.get("crawl") or {}).get("auto_ingest")
    local = cfg.get("weekly", {}).get("local_prompt", os.path.join(cfg.rel(cfg["state"]), "weekly_prompt.local.md"))
    fields = {
        "ROOT": cfg.root, "TODAY": dt.date.today().isoformat(), "LANG_NAME": LANG_NAME.get(cfg.lang, cfg.lang),
        "SCOPE": cfg.rel(cfg["scope"]), "PAPERS": cfg.rel(cfg["papers"]), "INBOX": cfg.rel(cfg["inbox"]),
        "ARCHIVE": cfg.rel(cfg["archive"]), "LINEAGE": cfg.rel(cfg["lineage"]), "STATE": cfg.rel(cfg["state"]),
        "NOTES": cfg.rel(cfg["notes"]), "SKILL": SKILL, "CATEGORIES": cats, "LOCAL_PROMPT": local,
        "QROOTS": "; ".join(roots) or "(none yet — design the tree as references/questions.md describes)",
        "MOVE": move, "CHECK": check, "QBUILD": qbuild,
        "AUTO_NOTE": (f"Auto-ingest is on (into `{auto.get('category')}`)." if auto
                      else "Auto-ingest is off for this project, so there is usually nothing to do here."),
    }
    text = open(os.path.join(HERE, "weekly_prompt.md"), encoding="utf-8").read()
    text = re.sub(r"<!--.*?-->\n*", "", text, count=1, flags=re.S)  # the maintainer note at the top is not for the model
    for k, v in fields.items():
        text = text.replace("{{" + k + "}}", str(v))
    out = cfg.state("weekly_prompt.rendered.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(text)
    allowed = ["Read", "Edit", "Write", "Glob", "Grep", f"Bash({check})", f"Bash({qbuild})", f"Bash({move} *)", "Bash(ls *)"]
    return out, allowed


def weekly(cfg, print_only=False):
    prompt_file, allowed = weekly_prompt(cfg)
    rel = cfg.rel(prompt_file)
    task = lambda phase: (f"Follow {rel} to do {phase} of this week's collection maintenance. "
                          f"Do not run the daily job (the outer script does). Finish with a two- or three-line summary.")
    if print_only:
        print(open(prompt_file, encoding="utf-8").read())
        print("\n--- claude -p task:", task("phase A: review new papers"))
        print("--- allowedTools:"); [print("   ", t) for t in allowed]
        return
    claude = claude_bin(cfg)
    if not claude:
        sys.exit("claude CLI not found; set \"claude_bin\" in research-lineage.json")
    print(f"===== {dt.datetime.now():%F %T} weekly ({cfg.root}) =====", flush=True)
    os.makedirs(cfg["state"], exist_ok=True)

    def run_claude(phase):
        r = subprocess.run([claude, "-p", task(phase), "--allowedTools", *allowed, "--disallowedTools", "WebFetch", "WebSearch"],
                           cwd=cfg.root)
        print(f"--- claude [{phase}] exit {r.returncode}", flush=True)

    run_claude("phase A: review new papers")
    daily(cfg, no_crawl=True)
    run_claude("phase B: labels and report")
    daily(cfg, no_crawl=True)
    step("check", py(os.path.join(HERE, "check_narrative.py"), "--config", cfg.file), cfg.root)
    print(f"===== {dt.datetime.now():%F %T} weekly done =====", flush=True)


def cron(cfg, install=False):
    """Every line carries a "# research-lineage:<project root>" tag, so re-installing replaces exactly this project's lines."""
    sch = cfg.get("schedule") or {}
    log = lambda n: shlex.quote(cfg.state(f"{n}.log"))
    base = f"cd {shlex.quote(cfg.root)} && {PY} -I {shlex.quote(os.path.abspath(__file__))}"
    tag = f"  {MARK}{cfg.root}"
    lines = []
    if sch.get("daily"):
        lines.append(f"{sch['daily']} {base} daily --config {shlex.quote(cfg.file)} >> {log('daily')} 2>&1{tag}")
    if sch.get("weekly") and (cfg.get("weekly") or {}).get("enabled", True):
        lines.append(f"{sch['weekly']} {base} weekly --config {shlex.quote(cfg.file)} >> {log('weekly')} 2>&1{tag}")
    if not install:
        print("\n".join(lines)); return
    cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout.splitlines()
    new = "\n".join([l for l in cur if not l.endswith(tag)] + lines) + "\n"
    subprocess.run(["crontab", "-"], input=new, text=True, check=True)
    os.makedirs(cfg["state"], exist_ok=True)
    print("installed:\n" + "\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["daily", "weekly", "cron"])
    config_arg(ap)
    ap.add_argument("--no-crawl", action="store_true")
    ap.add_argument("--print", action="store_true", help="weekly: show the prompt and permissions without running claude")
    ap.add_argument("--install", action="store_true", help="cron: write the schedule into crontab")
    a = ap.parse_args()
    cfg = Config(a.config)
    if a.cmd == "daily":
        daily(cfg, a.no_crawl)
    elif a.cmd == "weekly":
        weekly(cfg, a.print)
    else:
        cron(cfg, a.install)


if __name__ == "__main__":
    main()
