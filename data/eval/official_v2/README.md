# Official evaluation v2: a spent hold-out, now a regression set

official_v1 is the development set: planner prompts v42 and v43 were tuned on it, so its
scores are optimistic. official_v2 was built as the held-out test set and covers what
official_v1 barely tests: follow-up questions (official_v1 has no case with history),
several requests in one message, several entities, and cohort comparisons.

**Its hold-out status is spent.** The first run on 2026-09-12 scored 92.2% deterministic,
and that number stands as the one and only hold-out measurement (see [RESULTS.md](RESULTS.md)).
Reading its failures then exposed a real defect - case 003, where the composer read the
wrong row out of two applicable K51 grade scales and called a failing mark a pass - and
the fix for it (`536169fc`) came from that reading. Every later run of official_v2 is
therefore a post-fix measurement on a **seen** set, not a second independent hold-out, and
must be labelled that way. A genuinely fresh hold-out requires a new bundle.

**Status: frozen on 2026-09-11 (the commit that adds `manifest.json`), run as a hold-out once on 2026-09-12, re-run afterwards as a regression set.**
The per-case `review_status` and `frozen` fields keep their drafting values; `manifest.json`
is the record of approval.

## Provenance

The questions were written from the handbook content in the phrasing students use,
including informal and unaccented typing. They were not collected from real students.
Gold answers come from the source catalogs (reviewed tables, directories, formula rules
and regulation articles) through the same selector compiler as official_v1. No gold was
taken from system output.

## Files

| File | Content |
|---|---|
| `deterministic_authoring.yaml` | The single gold source: 154 questions with selectors, UI cohort, slice, history and, for each regulation task, an authored answer fact |
| `retrieval_authoring.yaml` | 47 retrieval-only regulation questions with source anchors |
| `slice_weights.yaml` | Expected share of real questions per slice family, for the reweighted overall score |
| `deterministic_tool_cases.json` | 154 compiled planner and execution contracts |
| `generated_answer_cases.json` | 154 answer cases for Generate + Judge |
| `retrieval_cases.json` | 93 retrieval cases: 46 derived from regulation tasks, plus the 47 retrieval-only questions |

Rebuild the compiled files with:

```bash
python -m scripts.build_official_deterministic --bundle official_v2
python -m scripts.build_holdout_suites --bundle official_v2
```

## Slices

A slice is named `family.detail`. Cohorts are balanced (K48-K49 51, K50 51, K51 52).

| Family | Slice | Cases | What it tests |
|---|---|---:|---|
| single | scoring, foreign_language, study_duration, scholarship_classification, formula, office, faculty, program, student_service | 42 | Each structured lookup on its own |
| single | regulation | 26 | One regulation question answered from articles |
| boundary | clarify, partial_clarify, out_of_domain | 13 | Missing input, one missing input among answerable requests, questions outside the handbook |
| multi_intent | struct_regu, struct_struct, regu_regu, three_plus | 27 | Two or three independent requests in one message; more than three must be declined with a request to choose |
| multi_entity | same_table, cross_table | 12 | The same question about several units, scores or certificates, from one table or from different ones |
| multi_cohort | structured, regulation | 9 | One question comparing two cohorts |
| memory | cohort_switch, entity_switch, value_switch, pronoun, topic_switch | 25 | Follow-ups that need the earlier turns, and traps where they must be ignored |

Stress is a cross-cutting label on 32 cases (21%), each with a `stress_type`: cohort
difference, informal spelling, dense request, boundary value, context trap, similar
sub-requests, tool boundary, handbook words inside an unrelated request, and partial
missing input.

## Gold rules

- Structured tasks: the compiler selects the catalog row. A unique row for a grounded
  input requires a `resolved_result` (fact lock); a whole table or several rows require
  those rows as evidence.
- Regulation tasks: a literal anchor must appear in the named article of that cohort.
  The planner is judged on mode and cohort only; retrieval quality is measured in the
  retrieval suite. A task may list equivalent articles that state the same rule.
- Equivalent plans are listed as alternatives: several directory entities as one grouped
  task, two cohorts as one task with execution units, a whole table instead of two rows.
- Memory cases pass up to four earlier turns. Follow-ups take the cohort from the query,
  then the history, then the UI selection, as the planner contract states.

## Overlap with official_v1

`python -m scripts.check_bundle_overlap --bundle official_v2 --threshold 0.7` finds no
official_v2 question with token similarity of 0.7 or more to any of the 500 official_v1
questions, after folding case and diacritics. The two sets do share handbook facts. That
is unavoidable for a handbook of about 460 articles, and short table questions differ
mainly in their values.

## Protocol

1. The owner reviews every question, selector and fact. Corrections are made in the
   authoring files only, then the compiled files are rebuilt.
2. Freeze: commit `manifest.json`. That commit is the frozen version, and the builders
   refuse to overwrite a bundle that has a manifest. Before a run, check that nothing in
   the folder changed since then (no output means unchanged):

   ```bash
   git diff --stat $(git log -1 --format=%H -- data/eval/official_v2/manifest.json) -- data/eval/official_v2 ':!data/eval/official_v2/RESULTS.md'
   ```

   `RESULTS.md` is written after a run and is excluded from the check.

3. Run each suite once on the final runtime, with response and router caches disabled:

   ```bash
   python -m scripts.run_official_deterministic --bundle official_v2 --current-worktree
   python -m scripts.run_official_answers --bundle official_v2 --suite retrieval
   python -m scripts.run_official_answers --bundle official_v2 --suite answers
   ```

4. Report per slice and per family with 95% intervals (Wilson for pass/fail, bootstrap
   for graded scores), plus the overall score reweighted with `slice_weights.yaml`:

   ```bash
   python -m scripts.report_official_slices <run>/deterministic.json
   ```

5. The gold never changes because of a result. Code may change when a result exposes a
   real defect, but then the hold-out is spent: verify the fix on official_v1, keep the
   original official_v2 numbers as reported, and label every later official_v2 run as a
   post-fix regression measurement rather than a hold-out. This is what happened on
   2026-09-12; see the note at the top.

## Limitations

- One author wrote the questions and the gold; a second reviewer has not checked them.
- The questions imitate student phrasing but are not a sample of real traffic, so the
  reweighted score depends on estimated slice weights.
- 154 questions give wide intervals for small slices (for example 9 multi-cohort cases),
  so slice results show direction rather than precise rates.
