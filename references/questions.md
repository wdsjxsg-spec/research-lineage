# Question lineage

A field is easiest to understand through the **questions** its papers put forward: which questions were asked first, which papers answered, extended or overturned them, which questions migrated into new ones, and which are still open. Citations between papers, rolled up to the questions those papers ask, show how one question led to the next. This view usually explains a domain better than grouping by method or venue.

## What you produce: `<lineage-dir>/questions.json`

```json
{
  "questions": [
    {"id": "Q1",   "parent": null, "short": "≤ 14 words / 18 字", "text": "The full root question?"},
    {"id": "Q1.1", "parent": "Q1", "short": "...", "text": "A sub-question?"}
  ],
  "papers": {
    "2309.00155": {"q": "Q1.2", "stance": "proposes",
                   "question": "The question THIS paper puts forward, in one sentence?",
                   "approach": "How it answers (method/data), ≤ 1 line",
                   "finding": "Optional: the answer, only if the abstract states it"},
    "s2:<id>": {"...": "non-arXiv papers use their graph key"}
  }
}
```

Every paper key in `graph.json` should appear exactly once. `questions.py build` validates ids, parents and stances and fails loudly; fix and re-run.

## Designing the question tree

- **3–6 root questions** — the field's fundamental problems, phrased as real questions ("Can deception still work when the attacker is an AI?"), not topic labels ("LLM honeypots").
- **2–5 sub-questions per root**, total roughly 12–25 for ~100 papers. A sub-question should hold ≥ 2 papers; merge singletons upward unless the question is genuinely new (a new question with one paper is itself a finding — keep it and say so).
- Papers attach to **leaf** questions (sub-questions); roots summarise their children.
- Build the tree from the papers, not from a textbook: read the worksheet (`questions_todo.md`), jot each paper's question, then cluster. Expect to revise the tree once after mapping everything.
- Questions can cut across the folder categories — that is the point. A paper in "surveys" can belong to "Is the threat real?"; an autonomous-defence paper can belong to a deception question.
- Use the user's language for all text.

## Per-paper fields

- **question** — what the paper itself asks, specific to it. Good: "Can an LLM generate a shell realistic enough to fool human attackers?" Bad: "LLM honeypots." If the abstract is too thin to tell, write what the title supports and say "(title only)".
- **approach** — the means, briefly; no evaluation adjectives.
- **finding** — only when the abstract states a result. Do not invent numbers.
- **stance** — the paper's relation to its question:

| stance | use when the paper… |
|---|---|
| `proposes` | offers a new method/system/answer |
| `extends` | improves or adapts an existing answer to the same question |
| `evaluates` | measures, benchmarks or empirically tests answers (incl. field measurements) |
| `challenges` | shows a prior answer or assumption fails (attacks, impossibility results, contrary evidence) |
| `reframes` | opens a new question or redefines the problem (position papers, new framings) |
| `surveys` | reviews or systematises existing work |

`challenges` and `reframes` carry the most interpretive weight: dashed "challenge" citations mark where the field's assumptions are being contested, and reframing papers mark question shifts. Be deliberate with them.

## Workflow

```bash
python3 -I scripts/questions.py prepare --out <lineage-dir> [--notes summaries.md]   # worksheet
# read questions_todo.md (in chunks of ~30 papers if large), write questions.json with the Write tool
python3 -I scripts/questions.py build --out <lineage-dir>                            # validate + roll up
python3 -I scripts/render.py --out <lineage-dir> ...                                  # adds the 问题脉络 / Question lineage tab
```

`analyze.py` rewrites `graph.json`; if you re-run it, re-run `questions.py build` before rendering.

## Reading `questions_digest.md`

- **status**: `emerging` (first paper in the last 12 months), `active` (≥ 3 papers in the last 12 months), `dormant` (nothing in the last 18 months), `contested` (has `challenges` papers).
- **builds on Qx ×n**: papers of this question cite papers of Qx n times. Following these gives the question-to-question branches.
- **Challenge links**: citations made by `challenges` papers — the contested branches.
- **seeds**: earliest papers of a question that cite no other paper of the same question — where the question started.

Patterns worth naming in the narrative:
1. **Question shift** — an old question goes dormant while a newer one builds on it heavily (e.g. "optimal static defence" → "co-evolving defence").
2. **Reopened question** — a dormant/contested question is challenged again by recent papers but has no new answers yet: a strong research opportunity.
3. **Contested premise** — challenge links concentrated on one question: the field's assumption there is under pressure.
4. **Orphan question** — emerging question with no internal citations yet: open ground.
5. **Isolated communities** — questions in different roots that never cite each other although they address the same threat.
