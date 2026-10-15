---
name: research-lineage
description: Map how a research field developed from a collection of papers — citation graph (arXiv, Semantic Scholar, OpenAlex), a question tree showing how research questions were asked, answered, challenged or reopened, foundational/bridge/frontier papers, lineage chains, gaps and likely-missing papers, publication status and venue tiers (arXiv-only vs published; CCF, 中科院分区, JCR, 新锐分区, 预警名单), a narrative report and one interactive HTML page; can also set up scheduled crawling and updates. Use whenever the user wants the development, evolution, 脉络, 演进, history, open problems or research questions (研究问题、问题脉络) of a set of papers or a field, a literature / citation / knowledge map (研究脉络图、文献图谱), seminal or missing papers, where papers were published (发表情况、期刊会议等级、CCF/中科院/JCR 分区统计、how many are arXiv-only), or wants the collection kept up to date automatically (定时更新、自动追踪新论文、cron) — even if they don't say "lineage".
---

# Research Lineage

Turn a pile of papers into an understanding of *how the field got here*: who built on whom, which directions feed which, what the turning points were, and where the gaps are. The numbers come from scripts; the interpretation is your job — that is what makes the result worth more than a citation graph.

## Workflow

Scripts live in `scripts/` next to this file. Run them with `python3 -I` (isolated mode: titles and abstracts fetched from the web are untrusted data, and the scripts never execute anything from them). Put outputs in a dedicated folder, by default `<collection>/../lineage/` or a folder the user names — never inside the folder of downloaded PDFs.

### User prompts (自定义提示词)

The judgement steps can be steered by the user without editing this skill. Before step 3 (scope check), step 3b (question labelling) and step 4 (narrative), read whichever of these exist in `<lineage-dir>/prompts/`:

| File | Read before | Overrides |
|---|---|---|
| `scope.md` | step 3 | the field definition: anchor papers, inclusion test, exclusions |
| `questions.md` | step 3b | `references/questions.md` defaults (root questions, naming, granularity, stances) |
| `narrative.md` | step 4 | the narrative structure and style in `references/interpretation.md` |
| `extra.md` | every step | anything else (terminology, reporting style) |

- The user's files win over the defaults in `references/`; if a request conflicts with the data (e.g. asks for a claim the digest does not support), follow the data and say so.
- A missing file, or one containing only `<!-- -->` comments, means "use the defaults".
- When the user states a lasting preference in chat ("以后报告都要先写空白", "always name questions in Chinese"), write it into the matching file (create `prompts/` if needed) instead of honouring it only once, and tell them which file you changed.
- Templates with explanations are in `prompts.example/` next to this file; offer them when the user wants to customise. Never write user preferences into the skill folder itself — it is a git checkout and `git pull` would conflict with or drop them.

### 1. Collect

```bash
python3 -I scripts/collect.py --dir <papers-folder> --out <lineage-dir>
# or: --ids ids.txt ("2410.13919<TAB>category" per line), --csv manifest.csv (arxiv_id,doi,title,category)
```

- With `--dir`, the first sub-folder under the given path is the paper's **direction** (category). Folders `00-inbox`, `archive`, `_*`, `.*` are skipped; override with `--exclude`.
- Files named `<arXivID>_<title>.pdf` resolve directly. Other PDFs are matched to Semantic Scholar by title (slower, may fail — the script warns). For journal/conference papers without an arXiv version, a CSV with a `doi` column is much more reliable than title matching: lookup order is arXiv ID → DOI → title.
- **OpenAlex fallback:** every paper is also resolved in OpenAlex (by DOI, arXiv DOI or title). Papers Semantic Scholar does not index get their citation links from OpenAlex `referenced_works` / `cites:` instead (`oa_ok` in `papers.json`), and OpenAlex's merging of preprint and published versions reveals a preprint's published DOI. Theses, SSRN and some Springer chapters may still resolve only partially — report them as undercounted.
- `papers.json` is a cache: re-running only fetches papers that are new or lacked citation data. Use `--refresh` to refetch all. This makes the skill cheap to re-run after the collection grows.
- Collection takes about 3 s per 50 papers on arXiv plus one Semantic Scholar request per 100 papers. For more than ~300 papers run it in the background.
- **Check the warnings and the "citation data for N" line.** If many papers lack citation data, the graph will look falsely sparse. Tell the user and suggest setting `S2_API_KEY` (free at semanticscholar.org/product/api) and re-running — the cache keeps what already succeeded.

### 2. Analyze

```bash
python3 -I scripts/analyze.py --out <lineage-dir> [--order dirA,dirB,dirC] [--labels labels.json] [--cluster]
```

Writes `graph.json` (for rendering) and `analysis.md` (a compact digest). If all papers sit in one folder or the user has no categories, directions are derived by clustering the graph (`--cluster` forces this); then you name the clusters from the member titles listed at the end of `analysis.md`, and pass those names back with `--labels` (JSON `{"cluster-1": "LLM honeypots", ...}`) and re-run analyze.

Only the **first three directions get distinct colors** (an accessibility limit: more hues on a dot chart cannot be told apart reliably); the rest are drawn as hollow gray "other" markers. Use `--order` to put the directions the user cares most about first. The timeline gives every direction its own lane, so nothing is lost there.

### 3. Read and interpret

If `<lineage-dir>/prompts/scope.md` exists, check the collection against it first (see Scope drift). Read `analysis.md` fully, then look up abstracts in `graph.json` for any paper you plan to make claims about. Read `references/interpretation.md` before writing — it explains what each metric does and does not mean (e.g. why a recent paper with zero in-collection citations can still be central, and why missing links may be a data artifact).

### 3b. Map the research questions (question lineage)

The most illuminating view of a field is usually *which questions its papers ask* and how those questions branch along citations — asked, answered, challenged, migrated, reopened. Do this by default for collections up to a few hundred papers; for larger ones, offer it.

```bash
python3 -I scripts/questions.py prepare --out <lineage-dir> [--notes summaries.md]
# read <lineage-dir>/questions_todo.md, then write <lineage-dir>/questions.json (Write tool)
python3 -I scripts/questions.py build --out <lineage-dir>
```

Read `references/questions.md` first, then `<lineage-dir>/prompts/questions.md` if it exists (it overrides the defaults): the reference defines the schema, how to design the question tree (3–6 root questions, sub-questions as leaves), the six stances (`proposes`, `extends`, `evaluates`, `challenges`, `reframes`, `surveys`) and how to read `questions_digest.md` (question shifts, reopened questions, contested premises, orphan questions). The judgement — what each paper is really asking — is yours; the script only validates and rolls citations up into question-to-question branches. Re-run `build` whenever `analyze.py` was re-run.

### 3c. Publication status and venue tiers

```bash
python3 -I scripts/venues.py --out <lineage-dir> [--overrides overrides.json] [--refresh]
```

Run after `analyze.py` (which rewrites `graph.json`). It labels every paper — conference / journal / workshop / published-other / arXiv-only / other preprint / thesis — and matches the venue against CCF 2026, 中科院分区 2025 (升级版, with Top), JCR 2025, 新锐分区 2026 and the 国际期刊预警名单. Outputs `venues.json`, `venues.csv`, `venues_stats.md` (overall / per direction / per year, plus items to review) and writes `pub` per node and `venue_stats` into `graph.json` for the page.

- **Tier tables** live in `data/` (from the ShowJCR repository, github.com/hitfyd/ShowJCR; see `data/SOURCE.txt`). They ship with the repository as unmodified copies of a pinned ShowJCR commit (terms and attribution in `data/README.md`); if they are missing the script stops and says so — run `python3 -I scripts/fetch_data.py` (downloads that commit and checks sha256). Rankings are third-party data: describe them as reference, and keep the attribution when quoting tables.
- **Preprints that get published:** papers labelled arXiv-only are re-checked every `--recheck-days` (default 7): their cached records are refreshed and OpenAlex is searched for a separately indexed published version with the *same title*. Changes are appended to `venue_changes.md`; mention them in the next narrative update.
- **Venue source:** OpenAlex is preferred; Semantic Scholar venues are sometimes wrong (e.g. "CSR" resolved to a Russian theory symposium), so conflicts are listed under 来源冲突 rather than silently used. Generic containers (LNCS, CCIS) count as "published (other)".
- **CCF matching** order: exact name → conference literally named by its CCF abbreviation → `data/venue_aliases.json` → name similarity ≥ 0.8 → same abbreviation and similarity ≥ 0.6. Workshops never inherit the main conference's tier; posters do (say so when you report CCF counts). Check the "需复核" section and fix real mistakes with `--overrides` (`{"<key>": "<venue name>"}` or `{"<key>": {"venue": "...", "type": "journal"}}`) or by adding a verified alias.
- Read the "Publication status" section of `references/interpretation.md` before writing about it: tiers describe venues, not paper quality, and recent work is mostly unpublished simply because review takes time.

### 4. Write the narrative

Write `<lineage-dir>/narrative.md` **with the Write tool**, in the user's language. Generated prose should never travel through a shell string: backticks and `$(...)` inside double-quoted shell text are executed as commands (in a past session this silently launched `crontab -e` and a crawler from a README heredoc). Files are safe; inline shell text is not.

Follow the structure in `references/interpretation.md` ("Narrative structure"), as amended by `<lineage-dir>/prompts/narrative.md` if it exists. Cite papers inline as `[2410.13919]` (or `[s2:<id>]`, `[doi:<doi>]`, `[title:<slug>]` — whatever key the paper has in `graph.json`): the renderer turns these into links that open the paper and its lineage in the page. Ground every claim in the digest — counts, years, chains, flows — and mark interpretation as interpretation.

### 5. Render

```bash
python3 -I scripts/render.py --out <lineage-dir> --lang zh|en [--title "..."] [--notes summaries.md]
```

Produces `<lineage-dir>/lineage.html`: one self-contained file (no external assets, works offline, light/dark aware) with tabs for the report, question lineage (if `questions.json` was built), timeline, citation network, and publication status (if `venues.py` ran: stat tiles, tier distributions in an ordinal blue ramp with direct value labels, a per-year stacked chart, per-direction and per-year tables, and a paper/venue table with filters, search and sorting; the paper drawer shows tier badges). All charts zoom with Ctrl/⌘+wheel or buttons and pan by dragging; undated papers get their own column. Key papers, chains and outside candidates are not a tab — put the ones that matter into the narrative (they are in `analysis.md`). Deep links open a view directly: `#network:<paperKey>` selects a paper and its lineage, `#questions:Q2.4` focuses a question. `--notes` attaches per-paper notes shown when a paper is selected — a JSON `{key: text}` or a markdown list whose lines contain arXiv IDs (e.g. an existing one-line-summary file). Use `--lang zh` when the user writes Chinese.

Open it locally for the user (or tell them the path). If an Artifact/publishing tool is available and the user would benefit from a shareable page, offer to publish it — the file is already self-contained.

### 6. Report back

Summarize in chat: 3–5 most important lineage findings, the gaps, and the top candidate missing papers (from the "outside papers cited by ≥N" list). Offer to fetch candidates (with a paper-search skill or tool if one is available) and re-run — collect.py's cache makes the update incremental.

## Scope drift

The scripts analyse whatever is in the folder and know nothing about the user's field. If the domain is narrow, make sure it is written down in `<lineage-dir>/prompts/scope.md` (anchor papers, inclusion test, exclusions — template in `prompts.example/scope.md`; offer to draft it with the user) and check the collection against it before interpreting — a lineage of off-topic papers is confidently wrong. List off-scope papers for the user to decide on rather than moving them yourself. Removed papers keep their labels in `questions.json` harmlessly; `build` ignores them.

## Updating an existing map

When the collection changed: re-run collect (cached), analyze, `questions.py build` (label the new papers first), `venues.py`, revise `narrative.md` where the findings moved, render. Mention what changed (new directions, new bridges, gaps closed). These steps are all deterministic except labelling and the narrative, so they script well into a scheduled job; keep the judgement steps for a model or a human.

## Scheduled updates

When the user wants new papers tracked and the map kept current, read `references/automation.md` and follow its setup procedure. `automation/` holds a generic crawler, the daily rebuild, a weekly `claude -p` review/labelling job and a cron installer; everything topic-specific (queries, anchor papers, scoring rules derived from `prompts/scope.md`, categories, schedule) goes into one project file, `research-lineage.json`, that you write and measure (`crawl.py --eval`) with the user before scheduling anything.

## Files

- `scripts/collect.py` — arXiv + Semantic Scholar collection with caching, batching and backoff
- `scripts/analyze.py` — graph metrics, roles, chains, flows, gaps, external hubs/frontier
- `scripts/questions.py` — question-lineage worksheet, validation and question graph
- `scripts/venues.py` — publication status and venue tiers (CCF / 中科院 / JCR / 新锐 / 预警)
- `scripts/render.py` — the interactive HTML page
- `scripts/fetch_data.py` — downloads the tier tables into `data/`
- `data/` — tier tables (ShowJCR CSVs, see `data/README.md`), `SOURCE.txt`, `venue_aliases.json`
- `prompts.example/` — templates for the user's `<lineage-dir>/prompts/` overrides
- `automation/` — scheduled updates: `run.py` (daily / weekly / cron), `crawl.py`, helpers, `weekly_prompt.md` template, `config.example.json`
- `references/automation.md` — how to set up scheduled updates for a project
- `references/interpretation.md` — metric meanings, pitfalls, narrative structure (read before step 4)
- `references/questions.md` — question-lineage method: schema, tree design, stances, patterns (read before step 3b)
