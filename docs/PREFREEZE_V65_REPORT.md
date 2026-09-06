# Pre-freeze v65 verification — release gate not passed

Date: 2026-09-06. Reviewed base: `6269542945c8ed6a5bc9a055578b2f81c91ac421`.
The changes described here remain uncommitted. No push, HF deployment, official
evaluation run, or evaluation-data cleanup was performed in this verification.

## Implemented scope

- Updated the three ignored local `.env` collection settings to v33. No secrets
  are tracked. Verified the actual retriever collection and Mongo collection
  after component initialization, not just environment values before startup.
- Isolated fact-locks by execution cohort when a source document is validated
  for multiple cohorts. The regression exercises structured execution, citation
  merge and packet construction for one task with two cohorts, checking both
  input and result. Resolver arithmetic is unchanged.
- Changed the per-component input guard to use row-declared requirements and
  numeric operands. Field/level names no longer count as personal scores.
  Decimal-comma and decimal-point operands are equivalent.
- Bumped the pipeline/cache identity to `v65-cohort-fact-lock-reference-inputs`.
  Gemini remains `gemini-3.1-flash-lite`; prompt instruction version remains
  `student-handbook-answer-v3.24-grounded-table-context`. Packet metadata changed.

## Verification

- Final unit/integration run: **739 passed**; XML: `work/pytest_v65_reviewed.xml`.
- Changed Python files: Ruff passed. Git whitespace check passed.
- Runtime artifact/manifest audit passed.
- HF dry-run passed with explicit Qdrant/Mongo v33 targets. This is packaging
  verification, not a remote deployment or an actual Docker image build.
- One initial pytest invocation encountered temporary-directory setup errors.
  It was rerun with `--basetemp` inside the workspace; no production code was
  changed to address that environment issue.
- Eight local live API smoke requests completed once: all HTTP 200. Response
  and router caches were disabled. These are development diagnostics, not
  official accuracy measurements or an independent human audit.

Effective stores after initialization:

- Qdrant: `student_handbook_semantic_v33`.
- MongoDB: `parent_docs_v33`.
- Build: `build-934f1caf384f99ad96e9`.
- Evidence: `work/prefreeze_v65_live/effective_collections.json` and readiness JSON.

## Answer audit

| Smoke | Observed outcome |
|---|---|
| K51 5.2, sync | Correct D+/not passed, but no fact-lock in the packet. |
| K51 5.2, stream | Incorrect C; contradictory passed/not-passed wording. |
| K50/K51 comparison | Incorrect C/passed for both. K50 lock actually says D+/passed; K51 has no lock. |
| TOEIC one output column | Correct speaking level-4 range, without unnecessary clarification. |
| TOEIC two output columns | Correct level-3/4 component ranges. |
| TOEIC missing personal skills | Correctly declines a personal pass conclusion and requests comparison of remaining skills; Composer answered rather than a runtime clarification terminal. |
| Scholarship exclusion | Includes the bridging-program exclusion and relevant credit exceptions. |
| Compound | Correct academic classification and highest-score improvement rule. |

The missing-skills trace uses `certificate_or_language="TOEIC Nói"` and scalar
`score_or_level="160"`; this does not exercise the same exact entity match as
the unit-test row guard. Its final answer is appropriately conditional, but
the runtime clarification path is not proven universally by this smoke.

The scoring requests also differ in Planner operations: sync uses
`grade_10_to_letter`, stream omits the operation, and comparison uses
`pass_threshold`. These are recorded observations, not proof of the complete
root cause. Further diagnosis is needed before changing routing/resolution.

### Offline authorization check

Replayed the pre-fix `_normalize_source` and `_source_supports_unit` functions
from `62695429` on the captured citations. They expose the same absence of K51
locks and the same correct K50 D+ lock. The new cohort filter did not remove
these K51 results: they were already absent from its input.

This is a narrow offline evidence-authorization comparison, **not** a full
old/new pipeline A/B test and not proof that every upstream stage is equivalent.
The K50 final answer demonstrably contradicts a lock present in Composer input.

Local evidence:

- `work/prefreeze_v65_live/answers.jsonl`
- `work/prefreeze_v65_live/summary.json`
- `work/prefreeze_v65_live/authorization_audit.json`
- Answer-file SHA-256: `c691977249b4d0e23ad112f12338cc34207a7a248bd5cdc7ad3acf4397c60e5f`.

The decimal-comma guard refinement was made after the live smoke during review;
it passed the final offline tests and has not received a second live run.
No unsuccessful live output was discarded or rerun to obtain a better answer.

## Standards review

No documented standards violation. Review found a decimal-comma parsing edge
and duplicated slot derivation; both were addressed within the existing guard.
No additional abstraction or orchestration was introduced.

## Spec review

The two scoped runtime fixes conform to the approved requirements. This does
not mean the broader release plan has passed: the final-answer smoke gate failed.
Reviews and answer audit were AI-assisted, not independent human reviews.

## Decision required

Do not deploy/freeze or start official evaluation as a passed release.
Owner decision is required on a separately bounded diagnosis/fix of the scoring
smoke failures versus explicitly accepting them as release limitations.
No additional Planner, Composer, or resolver change has been made automatically.
The nine existing local commits remain unpushed; v32 remains available for rollback.

## Follow-up diagnosis authorized by the owner

Only offline inspection/replay was performed in this follow-up. No runtime,
prompt, model, corpus, or configuration was edited; no further paid model call
was made. Reproduction script: `work/diagnose_scoring_v65.py`. Detailed output:
`work/prefreeze_v65_live/scoring_diagnosis.json`.

### 1. Pre-routing replacement and post-routing aliases disagree

`hcmue_slang_dictionary.yaml` replaces `qua môn` with `học phần đạt`. In the
captured question this produces `có học phần đạt không?`. The scoring registry
declares `qua môn` and `có đạt không` for `pass_threshold`, but neither this
replacement nor `quy ra chữ gì` matches its declared operation aliases.

Using the same minimal decision with only grounded score 5.2:

- Original question: the normalizer infers `operation=pass_threshold`.
- Captured normalized question: the normalizer leaves operation absent.

The captured stream task indeed has no operation. Therefore the selector is
absent, broad scoring evidence includes academic/conduct classification tables,
and the numeric scoring resolver returns no result. The trace captures the
normalized plan, not the raw Planner response: it does not independently prove
whether the raw Planner omitted the operation or an earlier stage changed it.

### 2. K51 lacks grounded course scope, not a computed lock lost in merge

All three observed scoring tasks lack `course_scope`. The registry only declares
literal remaining-course aliases such as `học phần còn lại`; `môn chuyên ngành`
is not declared. A general synonym must not be added without establishing that
it denotes the same applicability category in the handbook/curriculum.

Offline resolver results:

| Observed execution | Result before the unique-row gate |
|---|---|
| K51 sync, grade-to-letter | Three matches: foundation D+/passed, remaining D+/not passed, ungraded P/passed. |
| K51 stream, operation missing | No scoring result. |
| K50 comparison, pass-threshold | One match: D+/passed. |
| K51 comparison, pass-threshold | The same three K51 matches. |

All captured tasks pass `validate_fact_lock_inputs`. The K51 lock is absent
because the resolver has no result or multiple matches, not because the new
cohort filter removes it. Supplying both a grade operation and a hypothetical
`remaining` scope yields a unique D+/not-passed result offline. This proves the
dependency, **not** the semantic validity of guessing that scope from the query.

There is also a candidate-contract inconsistency: `grade_10_to_letter` selects
only `grade_scale` tables for table evidence, but `_unique_reference_resolution`
calls the separate scoring catalog without that selector constraint. Its lookup
group includes the ungraded P table. For this K51 query, excluding P alone would
still leave two applicable graded results, so it would not alone restore a lock.

### 3. Composer contradicts correct evidence

The comparison packet contains a K50 D+/passed fact-lock and a table whose C
range is 5.5–6.2, not 5.2. The actual sent prompt contains the instruction to copy
`resolved_result` exactly. The answer nevertheless says C/passed for K50.
This is a demonstrated generation/obedience failure, not missing evidence or
wrong database selection. K51's C output is also unsupported by its grade rows.

The lock currently carries the full resolver payload, including `display_rows`,
`items` and `result`, alongside separate table evidence. A compact projection
could reduce duplication, but this is only a mitigation hypothesis. No controlled
generation comparison was run, so no improvement claim can be made.

### Bounded options, not implemented

1. Remove the unnecessary pre-router replacement of already clear pass/fail
   wording, or align it with the registry; characterize the complete
   normalization chain rather than adding an exact-query branch.
2. Keep operation/applicability constraints consistent between the existing
   table selector and fact resolver. Retain conditional answers whenever course
   scope is genuinely unknown; do not force a single result to satisfy smoke.
3. If approved, test a compact fact-lock projection containing only grounded
   input, cohort/scope, selected row/result and source identity. Do not keep
   extending the prompt or claim an LLM fact-lock guarantees output correctness.

These observations do not prove the deployed baseline would produce the same
answers: no full baseline run was performed. They identify concrete current
failure paths and leave the release decision with the owner.
