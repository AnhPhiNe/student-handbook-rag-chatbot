# Evaluation

The datasets, the suites and how to run them. The current headline numbers are
in the [README](../README.md#evaluation); every official_v4 run, its
pre-registration and its result are in
[official_v4/SPEC.md](../data/eval/official_v4/SPEC.md) and
[official_v4/RESULTS.md](../data/eval/official_v4/RESULTS.md).

## Datasets

| Bundle | Cases | Role |
|---|---:|---|
| `official_v1` | 135 deterministic, 155 retrieval, 150 answers, 60 production | Development set; the planner prompts were tuned on it ([notes](../data/eval/official_v1/README.md)) |
| `official_v2` | 154 deterministic, 93 retrieval, 154 answers | Spent hold-out (one run, 2026-09-12), now a regression set ([notes](../data/eval/official_v2/README.md)) |
| `official_v3` | deterministic only | **Archived**: still labelled with the retired K48-K49 cohort; not migrated to K49 |
| `official_v4` | 246 answers (228 in scope) | Answer-quality benchmark for every change since 2026-09-30; not a hold-out after its first runs ([SPEC](../data/eval/official_v4/SPEC.md)) |
| `development/` | small sets | Probes for one feature each (directory matching, social replies, catalog referral, numeric spans, …); never used as a benchmark |

## Suites

| Suite | v1 / v2 cases | What it measures |
|---|---:|---|
| Deterministic | 135 / 154 | Planning and structured execution against accepted outcomes: task split, lookup choice, cohort, grounded slots and the exact table value |
| Retrieval | 155 / 93 | Ranking of the retrieved evidence: Hit@k, MRR, nDCG@5 and required-source recall |
| Generate + judge | 150 / 154 | End-to-end answers scored by a pinned LLM judge (`openai/gpt-oss-120b`): correctness, faithfulness, citation correctness, context recall and precision, hallucination rate |
| Production | 60 / — | Requests against the deployed API: success rate, 429s, cache behavior, streaming time to first token and p95 latency, with pass/fail release gates |

## Historical results: official_v2 hold-out (2026-09-12)

> [!NOTE]
> The section below measures the stack of 2026-09-12 (Qwen3 planner on Groq,
> Gemini 3.1 Flash-Lite composer, local `bge-m3`, Cohere reranking, v33 data).
> It is kept because it is the only hold-out measurement the project has; it
> does not describe the current system.

`official_v2`'s hold-out run: 2026-09-12, commit `d09e970`, planner Qwen3 `v43` on Groq,
composer Gemini 3.1 Flash-Lite, judge `openai/gpt-oss-120b`. Production: `official_v1`'s
60 requests against the live Space the same day, commit `6eba6d4a`. Intervals are 95%:
Wilson for pass rates, bootstrap for judge scores.

### Deterministic — 92.2% (142/154), CI 86.9–95.5

| Capability | Cases | Pass rate | Answer correctness¹ |
|---|---:|---:|---:|
| Single lookup or single regulation | 68 | 94.1% | 96.8 |
| Follow-up question with history | 25 | 92.0% | 94.2 |
| Missing input, clarify, or out of domain | 13 | 92.3% | 99.2 |
| Two or three requests in one message | 27 | 88.9% | 94.8 |
| Several entities in one question | 12 | 100.0% | 95.0 |
| Cohort comparison | 9 | 77.8% | 100.0 |
| **Reweighted to expected traffic mix²** | 154 | **93.1%** | **96.5** |

¹ From the paired generate+judge run on the same questions.
² Weights from [`slice_weights.yaml`](../data/eval/official_v2/slice_weights.yaml), an estimate — see notes below.

Cohorts score within 4 points of each other (K48–K49, built from the K48 handbook then, 90.2, K50 94.1, K51 92.3); the 32
stress-tagged cases score 90.6% deterministic / 100 answer correctness. Running the suite twice separates real failures
from planner noise: 11 of the 12 failing cases fail both times, 3 more flip on only one
run. `official_v1` (development set, same runtime): 129/135, unchanged since before this
session's refactors, same six failing cases.

**One real defect surfaced this way.** K51 grades foundation and remaining courses on
different scales; without a `course_scope` slot the resolver returned every table and the
composer picked the wrong interval, calling a failing 5.2 a pass. Fixed in `536169fc` by
resolving the row inside each table instead of leaving it to the composer. `official_v1`
re-run: 129/135, no regression. `official_v2` re-run: 141/154 — **not a new hold-out
number**, since the fix came from reading a v2 failure; 92.2% above stands as the one
hold-out result the bundle will ever produce.

### Retrieval

| Metric | Result |
|---|---:|
| Hit@1 | 77.4% |
| **Hit@5** | **94.6%**, CI 88.0–97.7 |
| MRR | 84.8 |
| nDCG@5 | 85.3 |
| Required-source recall@5 | 91.9% |

### Generate + judge

| Metric | Result |
|---|---:|
| **Answer correctness** | **96.3**, CI 93.4–98.6 |
| Faithfulness | 96.0 |
| Answer relevancy | 98.8 |
| Citation correctness | 96.6 |
| Context recall | 84.5 |
| Context precision | 60.8³ |
| Hallucination rate | 6.5% |
| Critical false passes | 3 of 154 |

³ The composer is handed more evidence than a given answer draws on — a token-spend cost, not a correctness one.

### Production — release gates: 7 of 12 pass

| Gate | Result |
|---|---:|
| `success_rate` | 96.7% |
| `telemetry_coverage` | 0% |
| `warm_cache_hit_rate` | 90% |
| `cold_cache_status_coverage` | 100% |
| `warm_cache_status_coverage` | 100% |
| `streaming_ttft_coverage` | 100% |
| `http_429_rate` | 0% |
| `cold_cache_hit_rate` | 0% |
| `deterministic_p95_ms` | 20,054 ms |
| `warm_cache_p95_ms` | 4,313 ms |
| `rag_p95_ms` | 9,111 ms |
| `streaming_ttft_p95_ms` | 13,050 ms |

| Scenario | p50 | p95 | Success |
|---|---:|---:|---:|
| Warm cache | 2,396 ms | 4,313 ms | 100% |
| Streaming | 3,411 ms | 15,084 ms | 90% |
| Deterministic | 5,147 ms | 20,054 ms | 100% |
| Cold RAG | 6,852 ms | 9,111 ms | 100% |
| Burst | 7,555 ms | 15,308 ms | 90% |

Five gates fail. `telemetry_coverage` needs `STUDENT_RAG_EVAL_TELEMETRY=true`, which
production correctly leaves off — a configuration mismatch, not a defect. The three
p95 latency gates (`deterministic_p95_ms`, `warm_cache_p95_ms`, `streaming_ttft_p95_ms`)
were calibrated on a **local** backend: a 2026-08-08 smoke run hit 2,940 ms on localhost
against the same 3,000 ms limit that the deployed free-tier Space's 5,147 ms
deterministic p50 alone cannot meet, since the Space pays for two LLM round trips and a
network hop that localhost never did. Recalibrating those thresholds against the real
deployment target — not lowering them to pass — is the fix. `success_rate` misses its
98% target because of two payload failures: one (`official_prod_052`) is a Groq/Gemini
rate limit hit since evaluation and production share a key pool by choice, and the other
(`official_prod_042`) is an unexplained streaming `RuntimeError`, left open rather than
explained away. Thresholds, per-gate verdicts and the 31.2 s outlier:
[PRODUCTION_RESULTS.md](../data/eval/official_v1/PRODUCTION_RESULTS.md).

## Notes on these numbers

- The questions were written from handbook content in student phrasing, not collected
  from real students, so the reweighted score's traffic mix is the author's estimate —
  several administrative lookups in the set may be questions nobody asks.
- Directory lookup was probed separately over all 239 service records: every one
  resolves correctly when the query stays close to the catalog wording, and 220 of 239
  survive a mechanical shortening. The 9 that don't all land on one unit whose name
  matches the common word `đào tạo` ("training"); the only real pattern among them is postgraduate
  services this undergraduate handbook doesn't cover.
- One author wrote both datasets; no second reviewer checked them.
- The judge is an LLM whose agreement with a human rater hasn't been measured.

## Running the suites

```bash
python -m scripts.run_official_deterministic --bundle official_v2 --current-worktree
python -m scripts.run_official_answers --bundle official_v2 --suite retrieval
python -m scripts.run_official_answers --bundle official_v2 --suite answers
python -m scripts.run_official_answers --bundle official_v1 --suite production --base-url https://<your-space>.hf.space
python -m scripts.report_official_slices <run>/deterministic.json --bundle official_v2
```

Each run writes its report and a `run_snapshot.json` under `data/eval/reports/`. `--limit N` runs a smoke subset, and `--output DIR` resumes an interrupted run. `--retrieval-mode no_graph` or `--retrieval-mode vector_only` runs a retrieval ablation. [`regrade_official_deterministic.py`](../scripts/regrade_official_deterministic.py) rescores a saved run without any model calls. The suites disable the router cache, and they call paid providers.
