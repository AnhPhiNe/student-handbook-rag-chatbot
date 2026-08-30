# Architecture v5 unseen holdout

This bundle is the frozen, one-shot evaluation set for source commit `71e5ad5c`.
It replaces development-era headline metrics; older suites remain regression sets.

| Suite | Cases | Headline metrics |
|---|---:|---|
| Deterministic | 140 | exact path/tool/cohort/resolution accuracy |
| Retrieval | 160 | Hit@1/3/5, MRR, nDCG, observed cohort leakage |
| Generate + Judge | 150 | correctness, completeness, groundedness, citation correctness |
| Production | 60 | success rate, TTFT p50/p95, latency p50/p95, stream/cache contract |

The retrieval suite contains 120 realistic questions and 40 controlled stress
questions. The answer suite contains 101 realistic and 49 stress cases, spanning
72 regulation RAG, 30 structured, 18 mixed, 10 clarification, 10 unanswerable and
10 out-of-domain cases. Stress coverage includes missing diacritics, multi-intent
requests, ambiguous references, insufficient evidence and cohort comparisons.

The 60-case RAGAS set is a frozen subset of answerable answer cases. The 40-case
human template is also selected before generation. Both subsets are stratified by
cohort and answer path. Every automatic failure must be human-reviewed in addition
to those 40 cases.

## Anti-contamination policy

- Questions, expected paths and ground truth are frozen before execution.
- Retrieval primary topics are absent from every earlier tracked evaluation anchor.
- Exact normalized queries are checked across historical evaluation JSON files.
- Lexical nearest neighbors are reported for manual inspection.
- The system is evaluated once. Failures become regression cases for a later version;
  this holdout is not rerun after tuning and cannot be reused as a headline test set.

Report denominators with every percentage and distinguish automatic judge, RAGAS and
human-review metrics. `evaluated_system_commit` identifies the code under evaluation;
dataset hashes in `manifest.json` pin the immutable data contract.
