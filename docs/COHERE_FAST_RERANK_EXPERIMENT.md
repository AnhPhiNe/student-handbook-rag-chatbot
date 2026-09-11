# Cohere Fast top-16 reranking experiment

Date: 2026-09-09

Experiment runtime HEAD: `8a172ebd014b64cafacceb71bdfed0a6be2813cc`

The experiment runners (`scripts/evaluate_cohere_rerank.py`,
`scripts/evaluate_cohere_answers.py`) were removed after commit `07bf10e7`; check
out that commit to rerun them. The reranker itself remains in the runtime.

Dataset: `data/eval/official_v1/generated_answer_cases.json`

Reranker: `rerank-v4.0-fast` over the first 16 RRF-ranked child candidates

## Scope

This was an evaluation-only experiment used to decide whether the candidate
runtime should add hosted child reranking. It did not change the frozen
official-v1 metrics. The experiment preserved Planner, structured execution,
parent grouping, graph supplementation, evidence preparation, Composer, and
Judge behavior; only the child order immediately before parent grouping was
changed.

## Retrieval-layer result

The saved-candidate comparison contained 157 retrieval events derived from 155
cases. Each arm used the same saved RRF candidates and the same final grouping
rule.

| Metric | RRF | Cohere Fast-16 | Delta |
|---|---:|---:|---:|
| Hit@5 | 0.9490 | 0.9745 | +0.0255 |
| MRR | 0.8737 | 0.9397 | +0.0660 |
| nDCG@5 | 0.8904 | 0.9447 | +0.0543 |
| Required-source recall@5 | 0.9469 | 0.9724 | +0.0255 |

Paired nDCG@5 changed on 28 events: 23 improved, 5 regressed, and 129
were unchanged. Cohere call latency in this rate-limited research run was not a
production latency benchmark: mean 3.069 s, p50 1.109 s, p95 14.036 s.

## Generate + Judge result

All 150 answer cases were generated and judged. Seventy-seven cases entered
retrieval and produced 80 rerank calls because three compound cases made two
retrieval calls.

| Metric | Historical RRF | Cohere Fast-16 |
|---|---:|---:|
| Faithfulness | 0.9684 | 0.9745 |
| Answer relevancy | 0.9768 | 0.9796 |
| Answer correctness | 0.9514 | 0.9599 |
| Context precision | 0.5704 | 0.5493 |
| Context recall | 0.8768 | 0.8896 |
| Citation correctness | 0.9590 | 0.9657 |
| Hallucination rate | 0.0667 | 0.0533 |

The Cohere run completed without Cohere, Planner, Composer, or Judge API
failures. Cohere calls averaged 0.690 s and the complete pipeline averaged
7.508 s (p50 7.348 s, p95 10.475 s). The historical RRF pipeline averaged
5.861 s.

## Interpretation and release decision

The retrieval-layer comparison shows a useful ranking improvement. The
answer-level changes are smaller and their confidence intervals overlap, while
context precision decreased. Historical RRF/BGE answers were produced at
commit `2ea5f270`; the Cohere answers were produced at `8a172ebd`, so the
answer table is directional evidence rather than a strict causal A/B.

The release candidate therefore integrates Cohere Fast as a bounded,
fail-open stage rather than treating it as a correctness dependency:

```text
dense + BM25 -> RRF (up to 24 children)
             -> Cohere Fast (top 16 children)
             -> parent grouping and loading
```

Missing keys, unavailable quota, timeouts, HTTP failures, or malformed results
leave the original full RRF list unchanged. This preserves availability and
makes the additional quality/latency trade-off explicit. A new frozen
evaluation is required before reporting v74 metrics as official.

## Provenance

The raw outputs remain outside the runtime deployment package. Their recorded
SHA-256 identities are:

| Artifact | SHA-256 |
|---|---|
| Saved-candidate retrieval report | `6bab2f5d99300e29cc3797d44af1d6cac4a72f2ef436c8759947a8f28d3c1071` |
| Answer generation | `56f6967bae4e6ebccc2b292eb1d9655ed6f1e1c83f6dbd89776f97cec37755c6` |
| Judge output | `56933438fd0e2540e506a47d5c2b489a8938460b1d392b775e6da7dc1053b172` |
| Experiment summary | `3d9078659e4865ecefdf7a50074f49814083533051bfc20636cdd33dc5a7b6bb` |
