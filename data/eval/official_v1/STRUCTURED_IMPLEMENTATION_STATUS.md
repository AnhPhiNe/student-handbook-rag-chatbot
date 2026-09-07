# Structured simplification: bounded execution changes

Implemented:

- Preserve tasks with different slots (including operations, values, entities and output fields); deduplicate only identical slot sets within the same lookup/intent/cohort. Remove destructive slot merging and re-grounding after merge.
- Add internal resolution status (`resolved`, `evidence_only`, `needs_clarification`, `unavailable`) alongside existing evidence coverage. Propagate it per cohort through execution to the authorized Composer packet. `resolved` means a fact-lock exists, not that a directory needs a fact-lock.
- Select canonical reference tables once and pass only that selection to the row resolver. Scoring values now come from those same canonical rows through a column adapter, not the separate legacy scoring catalog. Multiple selected tables do not produce a fact-lock. Remove obsolete `resolver_table_ids` metadata.
- Preserve an explicit Planner clarification for unresolved direct-value requests. List requests remain evidence-only; a successfully resolved input takes precedence over a stale clarification. This does not infer personal intent from keywords.
- Bump pipeline v68 and retain normalizer v21. Existing HTTP response schema is unchanged. No model, prompt text, corpus or matching-threshold changes. The range reader now recognizes the canonical lower-bound wording `trở lên`; scoring thresholds remain source-defined.

Not implemented in this change:

- Inferring missing operands when Planner supplied neither the input nor a clarification. Evidence-only can be legitimate for general questions; it is not automatically treated as failure.
- Program-to-faculty dependency execution or retrieval routing changes.

These remaining limitations are not claimed as fixed. Existing evaluation results describe the prior runtime, not v68. Do not restart the old evaluator runner against v68 without refreshing identity and auditing the remaining contract revisions. No new evaluation run, push or deployment performed.

Verification: 196 targeted tests passed across scoring contracts, structured lookup, task preservation, query planning and prompt packet construction. The full `tests/` suite passed: 826 tests. Ruff passed for changed runtime modules and focused tests; `git diff --check` passed. These offline tests do not establish a new live evaluation metric.
