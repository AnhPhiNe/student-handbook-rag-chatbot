# Deterministic rerun preparation

Owner requested evaluator corrections and a fresh 135-case run after structured runtime v68.

- Retain the list-slot comparison fix and its negative fixture. Lists are not implicitly equivalent to `all`.
- Preserve raw retrieval output, exception class, stage and traceback when evaluation fails. A runtime exception and a grading exception are not interchangeable.
- Case 115 accepts a grouped directory outcome only when both required office records and their requested fields are present, alongside the faculty phone. Missing either office record still fails. The original three-task outcome remains valid.
- Case 013 now explicitly says `3,6/10`; previously its gold assumed a scale the question did not specify. Source values and thresholds are unchanged. This is a dataset clarification, not a like-for-like comparison with the previous wording.
- Other previously failed structured contracts, including required fact-locks, are not waived merely because RAG can retrieve an article.
- Use `--current-worktree` to record current code/config/artifact hashes before and after the run. Keep the historical runtime snapshot and prior results unchanged. No resume, no runtime edits during execution, router cache disabled.

Review is AI-assisted, not independent human audit. Results describe the revised dataset/evaluator and changed runtime; differences cannot be attributed solely to runtime improvements.

Post-run evaluator audit (no further inference): case 017 accepts both faculty emails in a grouped task, with both source-backed records required. Directory `all` gold explicitly accepts the requested field list; this fixes 123 without treating every list as `all`. Execution clarification is recognized only with matching task ID, target cohort coverage and a nonempty clarification question (124). Negative fixtures reject missing fields, missing questions and wrong bindings. Test fixtures deep-copy source fields so mutation tests cannot accidentally mutate their own gold.

Regraded the complete saved 135-case execution with `scripts/regrade_official_deterministic.py`. This retains the live source report, uses the same queries/cohorts/history, records new evaluator/dataset hashes and performs no model calls. Final report: `data/eval/reports/official_v1_deterministic_20260907T050445Z/deterministic_regraded.json`.
