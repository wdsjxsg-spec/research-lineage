# Scheduled updates: setting up automation for a project

Read this when the user wants the lineage kept up to date automatically — new papers tracked, the map rebuilt, the
report revised (定时更新, 自动追踪新论文, 每天/每周自动跑, keep it updated). The tools live in `automation/` next to
SKILL.md; everything topic-specific goes into one project file, `research-lineage.json`, which **you write**. The engine
stays generic so that `git pull` on the skill improves every project without touching its config.

## What runs

| Job | Command | Does |
|---|---|---|
| daily | `run.py daily` | crawl → pending additions → collection.csv → collect → analyze → questions build → venues → render → placeholder list → papers/README.md |
| weekly | `run.py weekly` | `claude -p` phase A (review auto-ingested papers and the inbox against the scope) → rebuild → `claude -p` phase B (label new papers, revise the narrative incrementally, write `lineage/updates.md`) → rebuild → narrative check |

The weekly job needs the `claude` CLI and runs with a narrow permission list (read/write files, the move/check/build
commands, `ls`; no web access). Long commands are run by `run.py`, never by the model, because `claude -p` stalls on
backgrounded commands.

Per-project files the jobs create in the state folder (default `automation/`): `seen.json` (every candidate ever seen —
keeps rejected papers from returning), `abstracts.json`, `auto_ingested.csv`, `openalex_anchors.json`,
`weekly_state.json`, `weekly_prompt.rendered.md`, logs. `pending_add.txt` (lines `<category>|<ID>`) is a queue the
daily job retries until the papers are added — use it when an API is rate-limited.

## Setup procedure

1. **Prerequisites.** The collection already exists in `papers/<NN-category>/` (one folder per direction) and the lineage
   has been built once (steps 1–5 of SKILL.md), so there is a `lineage/` folder and ideally a `questions.json`.
2. **Scope first.** The crawler can only be as good as the field definition. If `lineage/prompts/scope.md` does not
   exist, draft it with the user from `prompts.example/scope.md` (anchor papers, inclusion test, exclusions) and get
   their agreement. Everything below is derived from it.
3. **Ask only what you cannot infer:** daily/weekly times (default 09:00 daily, Monday 10:00 weekly), whether the
   weekly model review should run, and whether strict auto-ingest is wanted or every candidate should wait in the inbox
   (default: inbox only, until the eval below looks clean).
4. **Write `research-lineage.json`** in the project root, starting from `automation/config.example.json`:
   - `categories`: the existing folders with one-line descriptions; `title`, `lang` as used for the page.
   - `arxiv_queries` / `openalex_queries`: 4–10 queries, each pairing a topic phrase with the scope's angle (e.g.
     defense words AND attacker words). Broad queries are fine — scoring filters; narrow ones lose recall silently.
   - `anchors`: arXiv IDs of 5–10 core papers from the collection (their new citers are the best candidates);
     `anchor_titles` for core papers without arXiv IDs.
   - `scoring`: translate the scope's inclusion test into `groups` (required concept groups with title/text weights),
     its exclusions into `exclude`, `vetoes` and `penalties`. The semantics are in the `Rules` docstring of
     `automation/crawl.py`. Use lowercase regexes; JSON needs `\\b` for `\b`.
   - `auto_ingest`: `null`, or strict title-only rules (titles must name the scope's core concepts explicitly).
5. **Measure before enabling** — offline, no network:
   `python3 -I <skill>/automation/crawl.py --config research-lineage.json --eval`
   It scores the papers already in the collection (should mostly reach the inbox) and those in `archive/` (should mostly
   not; none should auto-ingest). Show the user the numbers and the misses; tighten or loosen the rules and re-run until
   recall on the collection is high and auto-ingest has no false hits. Papers without an offline abstract are scored on
   their title, which understates recall.
6. **Dry run** (network): `crawl.py --config research-lineage.json --dry-run --auto-ingest` lists what tomorrow's run
   would pick. Check that the picks look in scope.
7. **Weekly prompt check:** `run.py weekly --config research-lineage.json --print` shows the filled-in task and the
   permission list. The template is `automation/weekly_prompt.md`; per-project additions go in
   `<state>/weekly_prompt.local.md` (the user's file; the job reads it with priority).
8. **First full run:** `run.py daily --config research-lineage.json --no-crawl` (rebuild only), then without
   `--no-crawl`. Read the log for `[FAIL]` lines.
9. **Schedule:** `run.py cron --config research-lineage.json` prints the crontab lines. Show them and install with
   `--install` only after the user agrees (it replaces this project's previous lines and nothing else). Mention that the
   machine must be on at those times, and that a `claude -p` run uses their Claude plan.
10. **Tell the user** where the logs are (`<state>/daily.log`, `weekly.log`), that weekly decisions appear in
    `lineage/updates.md`, and which files they edit to steer things: `lineage/prompts/*.md`, the local weekly prompt,
    and `research-lineage.json` for queries and rules.

## Building a collection from nothing

The same config drives `crawl.py --bootstrap --since <year>`: no recency limit, relevance-sorted arXiv and OpenAlex
queries, the anchors' references (backward) and citations (forward), scored by the rules, listed in
`<inbox>/bootstrap-<date>/candidates.tsv` without downloading. Approved papers are added with `add_papers.py`
(`<category>|<id>`, id may be `title:<exact title>`). The full user-facing procedure is step 0 of SKILL.md. Candidates
listed once are recorded in `seen.json`, so neither a second bootstrap round nor the daily crawler repeats them.

## Changing scope later

Edit `scope.md` first, then the queries and scoring in `research-lineage.json`, then re-run `--eval`. Papers moved out
go to `archive/` (never delete: the crawler de-duplicates against it).

## Platform notes

Cron is Linux/macOS. On Windows, create two Task Scheduler tasks running the same `run.py daily|weekly --config …`
commands. On macOS, cron may need Full Disk Access for the project folder. Set `S2_API_KEY` and `OPENALEX_MAILTO` in
the crontab (e.g. a `VAR=value` line above the jobs) if the user has them — cron does not read shell profiles.
