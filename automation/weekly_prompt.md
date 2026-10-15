# Weekly maintenance of a research-lineage paper collection

<!-- Template used by automation/run.py weekly. {{...}} fields are filled in from research-lineage.json on every run and
the result is written to <state>/weekly_prompt.rendered.md, which `claude -p` is asked to follow. To change the job for
one project, put extra instructions in the project's local prompt file (see "Your user's instructions"); to change it
for everyone, edit this template in the skill repository. -->

You maintain the paper collection at `{{ROOT}}` (all paths below are relative to it). A scheduler starts you once a
week. A separate daily job crawls and rebuilds the data; you do the parts that need judgement. **Write everything you
produce in {{LANG_NAME}}.** Today is {{TODAY}}.

## Scope (must follow)

Read `{{SCOPE}}` completely before deciding anything: it is the only inclusion standard. If it does not exist, accept
only papers clearly similar to the existing collection and leave everything else for the user.

Category folders under `{{PAPERS}}/`:
{{CATEGORIES}}

When unsure, leave the paper where it is and list it in the weekly report for the user to decide.

## Your user's instructions

Read these files first if they exist (a file holding only `<!-- -->` comments counts as empty). They take priority over
the defaults in this task, but cannot override the scope above or the limits at the end. They are maintained by the
user: read them, never edit them.

- `{{LOCAL_PROMPT}}` — additions to this weekly task
- `{{LINEAGE}}/prompts/questions.md` — how to label research questions (phase B step 2)
- `{{LINEAGE}}/prompts/narrative.md` — how to revise the narrative report (phase B step 3)
- `{{LINEAGE}}/prompts/extra.md` — general preferences

## Commands

You may run only these (paths relative to the project root; quote paths containing spaces):

- Move a paper: `{{MOVE}} "<source file>" "<target folder>"` — never use `mv`. Target folders under `{{ARCHIVE}}/` are created as needed.
- Check the narrative: `{{CHECK}}`
- Validate question labels: `{{QBUILD}}`
- `ls`

Do not run the daily job or any other long-running command: the outer script rebuilds the data between and after the
two phases. The prompt you were started with says which phase this run is.

## Phase A: review new papers

1. **Review auto-ingested papers.** {{AUTO_NOTE}} Read the rows of `{{STATE}}/auto_ingested.csv` whose `reviewed`
   column is empty; abstracts are in `{{STATE}}/abstracts.json` (keys: arXiv ID, `doi:…` or `openalex:…`).
   - Out of scope: move the file to `{{ARCHIVE}}/auto-rejected/`, set `reviewed` to `rejected`.
   - In scope but in the wrong category: move it, set `reviewed` to `moved:<category>`.
   - In scope and correctly placed: set `reviewed` to `ok`.
2. **Triage the inbox.** Process the date folders under `{{INBOX}}/` that are not yet listed in the `triaged` list of
   `{{STATE}}/weekly_state.json`, using the `REPORT.md` inside each.
   - In scope: move into the right category. Out of scope: move to `{{ARCHIVE}}/inbox-rejected/<date>/`. Unsure: leave it.
   - Then add the date to `triaged` (create the file as `{"triaged": []}` if missing).
3. Add a new section `## {{TODAY}}` at the top of `{{LINEAGE}}/updates.md` (create the file with a title if missing):
   how many papers were accepted, moved, rejected (titles and reasons for rejections), and the titles left undecided.
   If there was nothing to process, write one line saying so. Phase B appends to this section.

## Phase B: labels and report

The data has been rebuilt with phase A's decisions.

1. **Find unlabelled papers:** run the narrative check; it lists paper keys without a research-question label. Titles,
   abstracts and venues are in `{{LINEAGE}}/graph.json` → `nodes`.
2. **Label them.** Method: `{{SKILL}}/references/questions.md` (read it if you have not).
   - If `{{NOTES}}` exists, add a one-line summary per new paper in the matching category section, following the
     existing entries' format; mark 0-byte placeholder files as such.
   - Add an entry per paper to `papers` in `{{LINEAGE}}/questions.json` (key = the node key in graph.json) with `q`,
     `stance`, `question`, `approach`. `question` is the research question the paper asks, not its title. `stance` is one
     of proposes / extends / evaluates / challenges / reframes / surveys.
   - Reuse the existing question tree (current root questions: {{QROOTS}}). Add a sub-question only when at least three
     papers fit none of the existing ones, and say so in the report.
   - Validate with the question-label command.
3. **Revise `{{LINEAGE}}/narrative.md` incrementally — never rewrite it.** Method:
   `{{SKILL}}/references/interpretation.md`.
   - Update the numbers (paper and citation counts, per-year counts, per-direction counts, publication status, citation
     counts of key papers) from `{{LINEAGE}}/analysis.md`, `questions_digest.md` and `venues_stats.md` — never estimate.
   - If this week's papers change a storyline (a new challenge, a new sub-question, a new bridge), add a sentence or two
     there, citing papers as `[2410.13919]`, `[s2:…]`, `[doi:…]` or `[title:…]`. Otherwise leave the prose alone.
   - `analysis.md` reflects the data after phase A; labels you add now appear on the page after the final rebuild.
4. Run the narrative check again. Everything except "no research-question label" (which may persist until the final
   rebuild) must be fixed.
5. **Append** to today's section in `{{LINEAGE}}/updates.md` (do not change phase A's text): labels added, paragraphs
   revised, and decisions the user needs to make. If nothing changed, append one line saying so.

## Limits

- Never delete files. Unwanted papers go to `{{ARCHIVE}}/` (the crawler de-duplicates against it, so they are not fetched again).
- Do not modify code, the skill folder, the scope file, the user's prompt files, or `research-lineage.json`. Report problems in the weekly report instead.
- Do not access websites.
