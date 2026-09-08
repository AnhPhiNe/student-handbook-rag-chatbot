# Official evaluation v1 — local results and retained authoring record

The three quality suites have now been run locally. See
[RESULTS_AND_LIMITATIONS.md](RESULTS_AND_LIMITATIONS.md) for the measured
deterministic, retrieval, and Generate + Judge results, and
[RESULTS_PROVENANCE.json](RESULTS_PROVENANCE.json) for runtime, dataset, and
report hashes. These are development measurements, not an independent holdout
or production certification.

Measured runtime identity: evaluated base `2a293721ff7998ba5ace0d81ca194d10f67581f3`,
pipeline `v73-planner-owned-structured-inputs`, Gemini 3.1 Flash-Lite, Composer
prompt v3.24, corpus build v33. Production60 was **not run** in this scope, so
there is no current production metric. The authoring and review documents below
are retained as original protocol/reference material, not as a next required
step.

## Authored suites

| Suite | Cases | Realistic | Stress/compound/ambiguity |
|---|---:|---:|---:|
| Deterministic | 135 | 108 | 27 |
| Retrieval | 155 | 124 | 31 |
| Generate + Judge | 150 | 120 | 30 |
| Production | 60 | 48 | 12 |

The table records authored casebook sizes. Only the first three rows are
represented in the current official-v1 local results; the Production casebook
was not executed for a current Production60 metric.

Balance the three cohort groups within each suite. Questions must arise from
handbook content and student needs, not previous failures. Shared topics are
allowed. Historical overlap screening is omitted by owner decision. This is
a system evaluation benchmark, not a claim of independent research holdout.

## Original authoring and execution protocol

The following instructions are retained from the original draft protocol for
provenance; they do not describe a pending gate after the completed local
quality-suite run.

1. Author source-grounded questions and gold from the source inventory. Include
   cohort, applicability, exceptions and equivalent acceptable sources.
2. Use natural student questions and review their intended meaning against gold.
   Do not compare questions against historical suites as a freeze gate.
3. Review every question and assertion. Non-applicable checks are N/A, not pass.
   Do not require unique fact-lock for policy, directories or ambiguous/multi-row
   requests. Keep graph UI references separate from Composer evidence.
4. Self-test existing evaluator using fixtures only. Record its commit and hashes
   separately from the runtime commit. No official case may enter the pipeline.
5. AI-assisted review covers the complete suite; there is no separate owner
   approval gate for 30 samples. Ask the owner only when gold genuinely cannot
   be determined. Do not claim independent human audit.
6. Finish and freeze all four datasets, rubric and evaluator hashes before any
   official inference run. Then run each quality suite once
   with response/router caches disabled. Report each suite before the next.

## Final stages

Audit all failures and 40 generated answers sampled with seed `20260906`.
Report x/n, percentages, cohort/type/style breakdown and limitations, no combined
score. Infrastructure/evaluator-invalid runs need a recorded reason before retry.
Do not change runtime because of low metrics.

Original protocol reference: after local evaluation/audit, a later release may
push/deploy a candidate to HF, verify build/readiness, and run Production 60
with separate cold/warm measurements. Tag the historical state before deleting
old evaluation artifacts, keep evaluator/regression fixtures and provenance,
and update README only with measured results.

`runtime_freeze.json` freezes the local runtime only. `prior_eval_inventory.json`
is a hash inventory, **not an overlap audit**. `source_inventory.json` identifies
source articles, **not reviewed gold answers**. These caveats remain part of the
authoring provenance; see the measured-results report for current status.

## Original authoring record

The entries below describe the authored casebooks retained for provenance, not
unfinished current release gates.

The previous 66 retrieval drafts were discarded at the owner's request.
`deterministic_authoring.yaml` now contains all 135 deterministic questions;
`deterministic_tool_cases.json` is compiled from those questions and source
catalogs without calling the production resolver or a model. Each cohort has
45 cases. This is still a draft, not a frozen dataset or an evaluation result.

`retrieval_authoring.yaml` now contains 155 source-driven questions across 31
content groups. The compiled `retrieval_cases.json` has 52 K48-K49, 52 K50 and
51 K51 cases (124 realistic, 31 contextual/compound). Every case has a checked
literal source anchor, source hash and explicit cohort. Article-number changes
are recorded in authoring metadata, not inferred from a shared article number.
Eleven single-source questions have been replaced with multi-source questions;
two now explicitly compare cohorts. Actual request cohorts are 52 K48-K49,
51 K50, 50 K51 and 2 general/multi-cohort (the allocation above is not the actual
single-cohort count). See `COVERAGE_REVIEW.md` for coverage and remaining limits.
The question/source-anchor review covers 155 cases, with targeted full-parent
checks and equivalent-source decisions documented in `RETRIEVAL_REVIEW.md`.
These are draft relevance judgments, not measured retrieval results.

`answer_authoring.yaml` contains 150 answer drafts, compiled into
`generated_answer_cases.json`: 120 realistic and 30 stress, 50 per allocation
cohort. Explicit multi-cohort questions retain their requested cohorts in answer
units; allocation is not a claim that all requests are single-cohort. Gold uses
complete parents and selected catalog fields, not retrieval previews or model
outputs. Compound cases retain separate required meanings, including partial
clarification. Literal anchors, cohort identity, semantic gold and evaluator compatibility have been reviewed offline. Review is AI-assisted, not independent human audit.
`production_authoring.yaml` and `production_cases.json` contain 60 authored transport requests: 20 cold RAG, 10 structured, 10 warm-cache, 10 streaming and 10 burst. Repeated requests are deliberate transport/cache probes, not independent answer questions. The casebook was not run for a current Production60 metric.

Questions use student-facing wording, not internal table, row, column or routing
instructions. Removing such hints must also trigger a gold review: missing
course scope must not be silently supplied by the evaluator. Natural requests
for a table are not inherently invalid, but artificial table vocabulary must
not be used to steer otherwise ordinary student questions.

Contract self-tests use synthetic fixtures, not model responses. Complete gold
review and the measured-run provenance are recorded in the linked report and
manifest. Older stratification/authoring scaffolding is superseded and is not
evidence for additional current metrics.
