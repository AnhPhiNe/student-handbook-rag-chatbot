# Planner prompt v62 (shorter wording) — pre-registered check

Written 2026-10-18, before any v62 run. The owner asked whether the Luna
planner prompt (v61) is too convoluted; v62 rewrites it shorter without adding,
removing or reversing a rule. This file fixes how v62 is judged.

## What changes

- `PLANNER_SYSTEM_PROMPT` in `src/retrieval/core/ai_router.py`: one statement of
  the ">3 requests → one clarify task" rule (it appears three times in v61), one
  merge/split rule set in BƯỚC 2, simpler wording of the optional-filter and
  optional-slot rules, and BƯỚC 6 no longer repeats BƯỚC 3's structured-vs-RAG
  check.
- `configs/structured_lookup_registry.yaml`: tool `description` texts and slot
  descriptions that reach TOOLS and the strict schema, notably
  `student_service.requested_field`, reduced to general rules.
- No change to the normalizer, executor, schema shape, model or reasoning effort.
- Nothing in v62 is derived from official_v4 (owner rule: no tuning on v4).

Only-if conditions ("Chỉ gộp … khi", "Chỉ chọn RAG khi", "bảng tham chiếu không
tự xác lập …") keep their direction; the v51 rewrite that turned them into
sufficient conditions caused over-merging on official_v3.

## Runs

Planner-only, production Luna config
(`configs/ai_router.yaml`), router cache off. Same storage for both prompts.
No composer, judge or answer generation.

| Suite | Cases | v61 (main 57181ed0) | v62 |
| --- | --- | --- | --- |
| official_v1 deterministic, contract v10 | 135 | once | once |
| official_v2 deterministic, its own case file (spent hold-out, regression only) | 154 | once | once |
| `data/eval/development/pass_fail_course_cases.yaml` | 8 | once | once |
| contact probes `prompt_v47_contact_intent_cases.yaml` (rubric v2) | 8 | once | once |

v61 is rerun now rather than taken from September reports, because those used
older prompts.

## Acceptance rule

v62 is accepted when all of these hold:

1. On official_v1 and on official_v2 separately, v62 passes at least
   (v61 passes − 3) cases. ±2–3 cases is the measured planner noise.
2. No new failure category: a category is the first false check of a failed
   case in the evaluator's order (task_count, task_modes, task_semantics,
   out_of_domain, clarification, structured_execution, structured_evidence,
   structured_source, structured_row, resolved_result, relationship,
   outcome_contract) or a planner/execution error. A category that has no v61
   failure on a suite but two or more v62 failures on it counts as new. Also
   reported: structured↔RAG selection errors (false positives / missed
   structured tasks); v62 may not exceed v61 by more than 2 on either suite.
3. Pass/fail probes: the 5 pass/fail cases (pf01–pf04, pf08) get
   `pass_fail_ungraded` in at least 4 of 5, and no control (pf05, pf06) gets
   `pass_fail_ungraded`. pf07 (foundation) is reported only.
4. Contact probes: v62 passes at least (v61 passes − 1) of 8.

If v62 fails the rule, the failing cases are read only to find which rewritten
sentence they trace to; that sentence goes back to its v61 wording and the
affected cases are rerun, reported as post-fix. No new rule is added for a
case.

## Addendum before the v62b run (2026-10-18)

v62 met the rule only at its limits (official_v1 132 = 132; official_v2 139 vs
142, structured false positives 3 vs 1). Four cases (v1 014, 054; v2 008, 068)
gained an extra RAG task beside the table lookup on "does this value pass"
questions, a pattern v61 never showed. It traces to one v62 edit: the clause
"giá trị có đạt điều kiện không" moved from BƯỚC 3 into the BƯỚC 2 split
bullet. v62b puts that clause back in its v61 place and wording; nothing else
changes. Both suites are rerun in full under the same rule; v62b results are
post-fix measurements on v1/v2.

## Result (2026-10-18): rejected, v61 stays

| Suite | v61 | v62 | v62b |
| --- | --- | --- | --- |
| official_v1 (135) | 132 | 132 | 132 |
| official_v2 (154) | 142 | 139 | **136** |
| v2 structured false positives | 1 | 3 | 3 |
| pass/fail probes, pass_fail_ungraded on pf01–04, pf08 | 4/5 | 5/5 | 5/5 |
| contact probes (rubric v2) | 7/8 | 7/8 | 7/8 |

v62b fails rule 1 on official_v2 (136 < 142 − 3). Restoring the value-passes
clause fixed the four over-split cases (v1 014, 054; v2 008, 068), but v2 059,
085 and 112 fail on both v62 and v62b and pass on v61. They are the same kind of
error each time (059 table instead of RAG, 085 directory instead of RAG for
"nộp đơn ở đâu", 112 second score left out), so the shorter wording is likely
the cause, not noise. No further rewrite was measured on v1/v2. Reports:
`data/eval/reports/official_v{1,2}_deterministic_20261018T{114343,115716}Z` (v61,
baseline worktree), `…T115155Z / T120552Z` (v62), `…T123154Z / T123005Z` (v62b).
