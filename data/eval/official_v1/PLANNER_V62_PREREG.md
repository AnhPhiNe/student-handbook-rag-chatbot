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
