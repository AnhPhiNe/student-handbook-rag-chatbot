# Final Release Evaluation

## Status

This document records the final post-refactor regression for the HCMUE Student Handbook RAG release candidate.

- Runtime and evaluator checkout: `13aef9e63e4384e0ee1a52cf2cd9327db2e97944`
- Deployed Hugging Face artifact: `d26c6f6`
- Dataset: `architecture_v9_1_corrected`, version `9.1.0-corrected-evaluation`, revision `1`
- Run kind: `post_fix_regression_not_original_holdout`
- Run date: 2026-09-05 (UTC)
- Planner: `qwen/qwen3.8-27b`, reasoning `low`, native JSON Schema
- Composer: `gemini-3.1-flash-lite`
- Judge: `openai/gpt-oss-120b`, fixed project rubric
- Retrieval: `vector_primary_graph_supplement`, PhoRanker disabled
- Storage: Qdrant `student_handbook_semantic_v32`, MongoDB `parent_docs_v32`

The dataset manifest was frozen against runtime `7f1fc82b` and evaluator `943d9b38`. The evaluator therefore reports an identity mismatch for this run. That mismatch is expected and is retained as evidence that this is a post-fix regression, not a new holdout. The dataset and document-store hashes remained fixed.

## Reproducibility

| Artifact | SHA-256 |
|---|---|
| Deterministic dataset | `a89528de83bd824e084428278991f0b5189b9ca3f9002f238936f86929a0da5e` |
| Retrieval dataset | `280bbcecc643478be9d58112ec95fc8a2039bac9bce5971442772acbd528df10` |
| Answer dataset | `63e578e3f6b295a4cadff404acf6ea00b36735409051b76aec04cb792cbd626c` |
| Production dataset | `99fb21e11ae63a75b5e75b999d899048f13264470baf3d7d21e08e372605ae20` |
| Parent document store | `4d410553cfaddeaef51fc096ffd0025d52e585b4c5dfe7ee0807e73570648143` |

The four suites have separate contracts and denominators. No aggregate score is reported.

## 1. Deterministic architecture

The 135-case suite measures Planner output, task structure, structured routing, cohort-aware evidence, row selection, optional fact locks, clarification, and out-of-domain behavior. It does not use Composer prose as its pass criterion.

| Metric | Result |
|---|---:|
| Passed cases | **123/135 (91.11%)** |
| Structured-selection precision | **98.84%** |
| Structured-selection recall | **96.59%** |
| Structured false-positive rate | **2.13%** |
| Plan-structure accuracy | **95.56%** |
| Task-semantics accuracy | **95.56%** |
| Structured-execution accuracy | **95.56%** |
| Structured-evidence accuracy | **95.45%** |
| Structured-source accuracy | **89.47%** |
| Structured-row accuracy | **93.18%** |
| Resolved-result accuracy | **40/46 (86.96%)** |
| Outcome-contract accuracy | **123/135 (91.11%)** |
| Cross-cohort leakage | **0/135** |
| Planner fallback | **1/135 (0.74%)** |

Breakdown:

| Case type | Passed | Cases | Pass rate |
|---|---:|---:|---:|
| Single structured lookup | 53 | 60 | 88.33% |
| Capability boundary | 24 | 24 | 100.00% |
| Compound query | 24 | 28 | 85.71% |
| Missing or ambiguous | 11 | 12 | 91.67% |
| Unsupported but in-domain | 3 | 3 | 100.00% |
| Out of domain | 8 | 8 | 100.00% |

The realistic split passed 99/107 (92.52%); the stress split passed 24/28 (85.71%). The fixed legacy gate failed only false-positive rate: 2.13% observed against a 2.00% limit. Failed IDs: `v9_det_001`, `v9_det_003`, `v9_det_014`, `v9_det_015`, `v9_det_017`, `v9_det_018`, `v9_det_039`, `v9_det_085`, `v9_det_096`, `v9_det_099`, `v9_det_105`, and `v9_det_114`.

## 2. Regulation retrieval

The 155-case suite runs through the Planner and the production retrieval adapter. Cohort filters are applied before top-k, and the reported run does not use PhoRanker.

| Metric | Result |
|---|---:|
| Hit@1 | **134/155 (86.45%)** |
| Hit@3 | **146/155 (94.19%)** |
| Hit@5 | **149/155 (96.13%)** |
| Primary-source Hit@5 | **96.13%** |
| MRR | **0.9085** |
| nDCG@5 | **0.8697** |
| Required-source Recall@5 | **91.29%** |
| Parent-section match | **96.13%** |
| Citation binding | **96.13%** |
| Content-type match | **96.13%** |
| Cohort match | **100.00%** |
| Cross-cohort leakage | **0/155** |
| Empty retrieval | **6/155 (3.87%)** |
| Realistic Hit@5 | **117/123 (95.12%)** |
| Stress Hit@5 | **32/32 (100.00%)** |
| Latency p50 / p95 / max | **2.303 s / 3.944 s / 5.581 s** |

The fixed gate failed only content-type match: 96.13% observed against a 98% target. Six cases were empty or primary-source misses: `v8_ret_057`, `v8_ret_097`, `v8_ret_112`, `v8_ret_116`, `v8_ret_124`, and `v8_ret_142`. Some compound cases also retrieved only part of their required source set, reflected in required-source Recall@5.

## 3. Answer generation

All 141 cases completed without a lost API-error case.

| Metric | Result |
|---|---:|
| Literal `answered` status | **126/141 (89.36%)** |
| `needs_clarification` status | **9/141 (6.38%)** |
| Out-of-domain status | **6/141 (4.26%)** |
| Mean latency | **5.414 s** |
| Latency p50 / p90 / p95 | **5.468 s / 7.698 s / 8.087 s** |
| Maximum latency | **16.618 s** |

The literal `answered` percentage is a status distribution, not an answer-quality score. Clarification and out-of-domain responses may be the expected outcome.

## 4. LLM Judge

All 141 cases were parsed successfully by `openai/gpt-oss-120b`.

| Metric | Result |
|---|---:|
| Faithfulness | **89.95%** |
| Answer relevancy | **94.38%** |
| Answer correctness | **90.37%** |
| Context precision | **58.55%** |
| Context recall | **82.00%** |
| Citation correctness | **92.37%** |
| Abstention correctness | **95.74%** |
| Question-handling correctness | **97.16%** |
| Answer success | **100.00%** |
| Raw unsupported-claim flags | **18/141 (12.77%)** |
| Packet required-fact coverage | **83.33%** |
| Realistic score | **90.23%** |
| Stress score | **90.90%** |

The fixed gate passed answer correctness, citation correctness, abstention, and the critical-failure limit. Faithfulness missed its 90% target by 0.05 percentage points. The raw unsupported-claim gate failed and was therefore human-audited rather than accepted at face value. Numeric accuracy is N/A because this suite declares no independent numeric assertion contract.

## 5. Human audit

The audit checked a fixed, stratified 40-answer sample and every one of the 27 automatically flagged cases against the query, frozen gold, required facts, citations, and authorized evidence packet.

| Metric | Result |
|---|---:|
| Stratified sample completed | **40/40** |
| Mean audit score | **97.41%** |
| Human–Judge MAE | **0.0650** |
| Agreement within ±0.15 | **87.50%** |
| Critical false passes in sampled 40 | **0** |
| Automatic-risk cases reviewed | **27/27** |
| Human-adjudicated meaningful unsupported/scope overreach | **5/141 (3.55%)** |

Automatic-risk classification:

| Classification | Cases |
|---|---:|
| Judge false positive or acceptable scope | 16 |
| Runtime failure | 6 |
| Minor answer quality | 5 |

The six runtime failures were:

1. `v8_ans_rag_029`: one coordinated policy heading was split into more than three tasks, causing unnecessary clarification.
2. `v8_ans_rag_065`: three coordinated nouns in one section title were treated as independent choices.
3. `v8_ans_rag_076`: the response handled a shared-regulation applicability transition incorrectly or incompletely.
4. `v8_ans_rag_081`: the core graduation answer was correct, but the Composer added a large foreign-language section outside the requested scope. This was the single critical runtime failure.
5. `v8_ans_struct_020`: the query specified a remaining-course category, but runtime selected the foundation table and returned the wrong grade/pass result.
6. `v8_ans_unanswerable_004`: the answer stated the general two-grader rule but did not say that the system cannot identify the person currently grading the user's exam.

The five minor-quality cases involved verbosity, compressed details, one omitted timing detail, an irrelevant tangent, or wording that should have been more cautious. The remaining 16 flags were not substantiated as runtime failures after direct evidence review.

This is a single-reviewer audit. Inter-rater agreement and Cohen's kappa are not claimed.

## 6. Production transport

The 60-case suite ran against the deployed Hugging Face API.

| Metric | Result |
|---|---:|
| HTTP transport success | **60/60 (100.00%)** |
| Successful payload | **58/60 (96.67%)** |
| Expected response status | **57/60 (95.00%)** |
| Error rate | **2/60 (3.33%)** |
| HTTP 429 / timeout rate | **0% / 0%** |
| Overall latency p50 / p95 / max | **7.844 s / 11.676 s / 39.677 s** |
| Cold RAG latency p50 / p95 | **8.720 s / 12.927 s** |
| Streaming TTFT p50 / p95 | **6.286 s / 10.280 s** |
| Streaming TTFT coverage | **100.00%** |
| Warm-cache hit rate | **9/10 (90.00%)** |
| Warm-cache latency p50 / p95 | **1.885 s / 5.691 s** |
| Source utilization | **73.33%** |
| Realistic score | **100.00%** |
| Stress score | **90.00%** |

Scenario results:

| Scenario | Passed | Cases |
|---|---:|---:|
| Cold regulation RAG | 20 | 20 |
| Structured | 10 | 10 |
| Warm cache | 10 | 10 |
| SSE streaming | 10 | 10 |
| Burst, concurrency 5 | 8 | 10 |

The two failures, `v8_prod_burst_06` and `v8_prod_burst_09`, occurred only in the burst scenario. Both completed at the HTTP transport layer but returned a `retrieval_error` payload. There were no HTTP 429 responses or evaluator timeouts.

The fixed production gate failed payload success (96.67% vs 98%), public telemetry coverage (0% vs 100%), warm-cache p95 (5.691 s vs 2 s), and streaming TTFT p95 (10.280 s vs 10 s). Telemetry is not exposed in public response payloads, so the telemetry result is an observability-contract limitation rather than an answer-correctness failure.

## Release verification

Before this evaluation, the release checkout passed:

- cache tests: 14/14;
- readiness plus sync/stream tests: 52/52;
- complete backend test suite: 640/640;
- Ruff checks;
- deploy-artifact validation and Hugging Face dry run;
- deployed health, readiness, synchronous chat, and SSE smoke checks.

The local developer virtual environment has a stale mixed OpenTelemetry installation reported by `pip check`; those packages are not part of the clean deployment constraint set. The deployed application is built in a clean container.

## Interpretation

The release demonstrates strong retrieval, cohort isolation, structured-routing precision, citation quality, and graceful transport behavior under ordinary scenarios. It does not establish production capacity, security, or real-user effectiveness. The main remaining limitations are compound-query over-splitting, a small number of structured selector errors, evidence scope control, six retrieval misses, burst admission under concurrency five, and warm-cache tail latency.

For a portfolio or CV, claims should include denominators and identify this as a final post-refactor regression. For a paper, the next evaluation should be a prospectively registered or external test set with independent multi-reviewer annotation; these V9.1 results should be treated as development/regression evidence rather than a new blind holdout.
