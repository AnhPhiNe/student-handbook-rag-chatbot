# Root-cause audit after deterministic rerun

Scope: saved live execution `official_v1_deterministic_20260907T050445Z`; offline code inspection and synthetic correct-plan probes. No new model calls. The saved report contains normalized plans, not original model payloads, so absence of a slot cannot automatically be attributed to Planner.

## Confirmed common mechanisms

1. **Cross-task alias inference can corrupt a correct control slot.** `_normalize_task` supplies the complete original compound question to `normalize_router_decision`. `_ground_declared_literal_slots` can overwrite an existing canonical operation if its natural-language span is not a registered alias. Reproduction: a correct `letter_to_grade_4` task with span `đổi ra hệ 4`, followed by an academic-classification task, becomes `academic_classification` for both tasks. This reproduces case 120's observed shape without a Planner error. Historical raw model output is unavailable; this does not prove the historical Planner was correct.
2. **Optional grounding rejection is silent.** A supplied scholarship `aspect=amount` with literal span `Tiền học bổng` is removed because that phrase is absent from its aliases. Revalidation clears errors, so the final plan has no explanation. A synthetic correct-plan probe confirms the loss. This can affect paraphrased selectors across domains; it does not prove every missing selector was present in the historical payload.
3. **Conservative selection exposes missing inputs instead of inventing values.** Replaying the 11 structured failures gives no fact-lock grounding errors except 014 (`missing_fact_lock_value`). Cases 003/012/013/018 still select multiple tables. Five scholarship cases select all four scholarship tables because `aspect` is absent. Case 040 selects one table but multiple program rows. These are selection/interpretation gaps, not evidence merge dropping an already-created result.

## Case accounting

| Cases | Observed cause / unresolved provenance |
|---|---|
| 003 | Missing foundation scope; two grade tables. Registry has formal phrases but not the shorter wording. |
| 012, 018 | Ungraded scope absent; three tables. Do not infer graded scope from a substring inside negated GPA wording. |
| 013 | Explicit /10 input and pass operation survive; general graded and ungraded tables both remain. No permission to arbitrarily choose the first. |
| 014 | Numeric input absent; original Planner payload unavailable. |
| 040 | First-degree paraphrase not recognized; one table, multiple rows. |
| 051, 053, 055, 058, 059 | Aspect absent; multiple tables. Alias rejection is reproducible for a correct amount payload, but historical payload unknown. |
| 054, 057, 113 | RAG/structured contract difference; final answer has not been evaluated. |
| 081, 093, 097, 114, 119, 122 | Routing/service matching/dependent-entity issues require separate evidence; not solved by changing merge. |
| 120 | Correct-plan synthetic reproduction demonstrates operation overwrite from a sibling. |

## Minimal implementation authorized to Luna Max

- Restrict alias inference to the task question; retain original user context for literal input grounding.
- Preserve valid canonical control slots already classified by Planner; do not reinterpret them from an unrelated exact alias. A correction may use the supplied literal span itself when it uniquely identifies a different declared operation, preserving the existing local correction contract. Continue validating enum/type and real input values.
- Record optional-slot removal reasons separately as normalization warnings, without turning a safe evidence-only fallback into a fatal validation error.
- Add positive and negative regression tests through `normalize_query_plan`, including reversed task order, task-local missing-operation inference, invalid numeric grounding and warning visibility.

No prompt, catalog, evaluator/gold, resolver arithmetic or matching-threshold changes in this bounded patch. In particular, do not globally exempt course scope/program type from grounding and do not add numeric guessing. Broader semantic-selector policy or directory dependency execution remains a separate decision. This patch is not claimed to fix all 21 failures or produce a new benchmark metric.

## Follow-on fixes proposed, not implemented here

- Review the distinction between semantic selectors (operation/aspect) and source-extracted inputs (score, cohort, program scope). A semantic selector should not require the English enum to appear in Vietnamese text, but relaxing selector validation must not authorize unsupported personal facts.
- Add source-backed terminology variants only as catalog metadata with negative/negation tests. For example, `đại cương` is currently rejected even when a correct foundation slot is supplied; broad matching of `tính GPA` would be unsafe inside `không tính GPA`.
- Do not manufacture a missing score, select the first of several applicable tables, or fill a dependent faculty from an unrelated task. A general dependency mechanism would change orchestration and is outside this bounded repair.
- Capture compact normalization warnings before a future live audit. Old normalized-only reports cannot establish which missing slots were generated and then removed.

Directory probe without an embedding model: `xin giấy chứng nhận điểm` (K51) ranks another service at 0.611; `in giáo trình` (K48–K49) ranks an unrelated student-policy service at 0.600. Both are below the 0.62 service threshold, while source catalogs do contain the gold service descriptions. These lexical-only probes explain a plausible matching failure, not the exact live semantic scores. Lowering the threshold would admit the wrong candidates in these probes and is not an authorized remedy.

## Implemented and independently checked

Luna (`gpt-5.6-luna`, reasoning `max`) produced the bounded patch, then stopped on a usage limit before final handoff. The parent reviewed the actual diff, required preservation of the existing explicit-span correction behavior, caught a missing-span regression, added varied-value and invented-input negative tests, and completed verification. No existing test expectation was changed to conceal that regression.

- Alias inference now uses the task question; original user/history context remains the grounding source.
- A valid canonical control is preserved when its paraphrase is absent from aliases. A missing span may be recovered only for that same value. A supplied grounded span can still correct a control if it uniquely names another registered operation.
- Optional-slot removal reasons survive as `normalization_warnings`, including when identical tasks deduplicate. They do not become fatal validation errors.
- Pipeline v69 / normalizer v22 invalidate old cache semantics.
- **841 tests passed**, Ruff passed, diff whitespace check passed. An offline correct-plan probe through normalization and canonical dispatcher resolves `B+ → 3.5` and `GPA 3.17 → Khá` independently in one compound request.

This is not a new live Planner/evaluation result. The saved 114/135 metric remains attached to v68; no metric gain is claimed for v69. Alias coverage, absent original Planner payloads, semantic selector policy, directory matching and dependent entity execution remain limitations. No commit, push, deployment or evaluation rerun performed in this audit/repair turn.

## Follow-on service metadata repair (2026-09-07)

Luna Max implemented two source-backed service alias rules after parent approval: `giấy chứng nhận điểm / chứng nhận điểm` and `in ấn giáo trình / in giáo trình`. Existing source descriptions identify the examination office and publisher respectively in all three cohort groups. Only `configs/office_aliases.yaml` and the generated service/office-profile catalogs changed; no matcher, threshold, prompt, resolver, corpus or database changed.

Independent JSON comparison against HEAD confirms 239 services and 65 office profiles remain. Exactly six records per catalog changed, only in `aliases` and the generated alias line in `raw_text`. Source, contact and cohort fields are unchanged. The existing focused builders regenerated these artifacts; faculty and manifest counts did not require updates.

The 14 new offline tests cover original service-description binding, combined production candidate pool, case/accent variants, generic ambiguity and task-local cross-cohort lookups. Parent verification: targeted tests **14 passed**, Ruff passed; full suite **853 passed, 2 failed**. Both remaining failures are authoring snapshot equality checks: the saved datasets embed the old catalog records. A read-only rebuild comparison found differences only in `gold_evidence[].record.aliases` and `raw_text` for deterministic 072/093/097/116/122 and answer 118/120. Questions, answer facts and execution assertions are unchanged. Saved datasets/results were deliberately not rewritten in this metadata repair. Source snapshots need an explicit refresh before claiming a fully green authoring suite or freezing a new evaluation.

The short foundation alias `đại cương` was deferred: metadata-only substring matching cannot distinguish its occurrence in a negated phrase. Generic-service ambiguity tests do not prove negation understanding. Dependent `program -> faculty -> email` remains an accepted limitation; no dependency executor was added. No new live evaluation metric, commit, push or deployment is claimed.
