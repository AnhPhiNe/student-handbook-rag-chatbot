# Luna medium strict-schema smoke — 2026-09-27

## Scope

This was the approved 18-case contract/execution portion of the Luna smoke.
The run used the current worktree, contract v10, prompt V49, normalizer
`v31-null-slot-omission`, OpenAI `gpt-6-luna`, reasoning `medium`, strict
JSON Schema, explicit output limit 8192, timeout 20 seconds per attempt and
one retry. Router cache was disabled.

Artifact:
`data/eval/reports/deepseek_v48_smoke_deterministic_20260927T053426Z/`.
The folder keeps the existing dataset-bundle name; the run snapshot identifies
the actual provider and model. `post_run_hashes_match=true`.

## Result

| Metric | Result |
| --- | ---: |
| Cases | 18/18 completed |
| Passed contract cases | **12/18 (66.7%)** |
| Evaluation failures | 6 |
| Runtime/planner/execution/evaluator errors | 0 |
| Request success after retry | 100% |
| Planner p95 | **8.59 s** |
| Cross-cohort leak | 0 |
| Structured execution accuracy | 88.9% |
| Structured evidence accuracy | 77.8% |
| Structured source accuracy | 91.7% |
| Structured row accuracy | 75.0% |
| Resolved-result accuracy | 90.0% |

The latency gate is met, but the deterministic accuracy gate of 95% is not.
This run evaluates planning and execution contracts; it does not evaluate the
composer's final prose answer.

## Failed cases

- **014 — scale clarification.** The model asked which score scale `4,3`
  used, while the scoring table contract expects the `graded` pass-threshold
  lookup. This is a semantic contract miss. The clarification is conservative,
  but it does not satisfy this authored case.
- **033 — over-splitting one lookup.** “TCF hay DELF” became two
  `foreign_language` tasks. The expected answer is one task containing both
  certificates because they are rows in one table. Execution retrieved the
  table, but task count failed.
- **047 — unnecessary clarification.** The comparison of first degree, both
  bridge types and second degree was split around a clarification instead of
  being represented as one whole-table comparison. This also failed in the
  previous JSON-mode run.
- **093 and 096 — legal enum, wrong intent.** Strict schema changed the raw
  field from the earlier illegal description `"địa chỉ"` to the legal enum
  `office`. The contract still requires `unit` for these service-responsibility
  questions, so the semantic failure remains. Strict output solved the shape
  error but not the unit/office distinction.
- **122 — missed catalog relationship.** The model emitted one RAG task and
  one clarification instead of a structured `student_service` task for the
  unit/email relationship. This is a planner routing/decomposition failure;
  no runtime exception occurred.

## Comparison with the earlier Luna JSON-mode smoke

The earlier same-size smoke with JSON mode recorded **15/18 (83.3%)**. The
strict run records **12/18 (66.7%)**. The comparison is informative but not a
perfect isolated experiment: the strict run also uses the current normalizer
revision and strict nullable-slot serialization. The raw outputs show the
three additional misses above, so strictness should not be presented as an
accuracy improvement.

Strict schema did achieve one concrete contract improvement: the two service
cases no longer produced an illegal `requested_field` value. It cannot decide
between two legal semantic values such as `unit` and `office`.

## Decision

Do not make strict Luna the production planner based on this run. Keep the raw
report and the earlier JSON-mode report as separate measurements. The next
work should be offline analysis of the three new semantic misses and the
provider-format trade-off. A prompt or schema change should be tested on the
same 18 cases before any full 135-case run or production switch.
