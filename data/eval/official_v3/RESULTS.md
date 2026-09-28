# official_v3 results

## Run 1: the only clean hold-out run (2026-09-27)

- **System:** planner prompt v52 (`structured-regulation-v52-v1-review`), registry v10, strict schema v2, at commit `65c194a7`.
- **Planner:** OpenAI `gpt-6-luna`, reasoning `medium`, strict JSON schema. The config is `configs/experiments/ai_router_openai_luna_medium_strict.yaml`, with the planner cache disabled.
- **Report:** `data/eval/reports/official_v3_deterministic_20260927T103000Z`
- **Scope:** planner, normalizer and structured execution. Regulation tasks are judged on mode and cohort only. Retrieval and the final answer are not measured here.
- **Before the run:** the owner saw a random 20-case sample of questions and gold and approved it.

| | Result | 95% Wilson interval |
|---|---:|---:|
| **Overall** | **115/132 = 87.1%** | 80.3–91.8% |
| Excluding the three known runtime gaps declared before the run | 115/129 = 89.1% | |
| single | 30/34 = 88.2% | 73.4–95.3% |
| multi_intent | 50/61 = 82.0% | 70.5–89.6% |
| compare | 15/17 = 88.2% | 65.7–96.7% |
| memory | 8/8 | 67.6–100% |
| boundary | 6/6 | 61.0–100% |
| relation | 6/6 | 61.0–100% |

By cohort the results are 38/44, 39/44 and 38/44. There were no request failures, fallbacks, execution errors or cross-cohort leaks. Out-of-domain accuracy was 100% and clarification accuracy 81.8%. Planner p95 latency was 7.7 s.

### Failures

These are classified for reporting only; no system change follows from them.

| Kind | Cases | Count |
|---|---|---:|
| Two independent regulation questions merged into one RAG task | 052, 053, 054, 055, 057, 059, 062, 068 | 8 |
| Known runtime gaps, declared before the run | 005 ("57d" is not a score), 016 ("mượn micro"), 076 ("đóng học phí") | 3 |
| Table question routed to RAG at the boundary between a table value and a policy ("có phải học lại", "đạt chuẩn", "yêu cầu … loại gì") | 003, 007, 085 | 3 |
| Two comparison values kept in one task instead of one task each | 100 | 1 |
| Unneeded clarification on a cross-cohort score comparison | 088 | 1 |
| Plan matched the gold, but the resolved row did not; not investigated | 046 | 1 |

### Reading the gap with official_v1

On official_v1 the same planner scored 133/135. That set is not a hold-out: prompts v50 and v52 were written from its failures.

The largest v3 failure kind explains most of the gap. v1 has **2** cases whose gold is two separate RAG tasks, v2 has 10 and v3 has 22. Tuning on v1 never exercised this decomposition, and the hold-out found it.

It is still open whether merging two related regulation questions into one retrieval query hurts the final answer. An end-to-end measurement has to answer that; this suite cannot.

### Rule

These numbers are reported as they came out. If any failure above is later used to change the system, every later official_v3 run is a post-fix regression measurement and must be labelled that way.
