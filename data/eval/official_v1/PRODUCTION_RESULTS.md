# official_v1 production suite — results

The fourth suite, and the only one that touches the deployed service rather than the
library. It sends the 60 official production requests over HTTP to a running API and
measures transport, cache protocol, streaming and latency, then applies the release
gates in `src/evaluation/gates.py`.

Run on 2026-09-12 against the live Hugging Face Space
(`https://anhfeee-hcmue-handbook-rag-api.hf.space`), runtime commit `6eba6d4a`,
pipeline `v76`, planner Qwen3 prompt `v43` on Groq, composer Gemini 3.1 Flash-Lite
prompt `v3.25`. Report: `data/eval/reports/official_v1_production_20260912T145857Z`
(not in git).

```bash
python -m scripts.run_official_answers --suite production --base-url <url>
```

## Headline

**Release gates: FAILED — 7 of 12 checks pass.** Every failure is explained below, and
three of the five are artefacts of how the gate or the run was set up rather than
defects in the service.

| Measure | Result |
|---|---|
| Transport success (HTTP layer) | **100%** — no connection, timeout or 5xx failure |
| Payload success | 96.7% (58/60) |
| HTTP 429 rate | **0%** |
| Warm-cache hit rate | 90% |
| Cold-cache hit rate | 0% (correct: a cold request must not be served from cache) |
| Cache protocol valid | yes |
| Streaming TTFT coverage | 100% |
| Source utilization | 80% |

Latency by scenario, milliseconds:

| Scenario | n | success | p50 | p95 | max |
|---|---:|---:|---:|---:|---:|
| warm_cache | 10 | 1.00 | 2,396 | 4,313 | 5,090 |
| streaming | 10 | 0.90 | 3,411 | 15,084 | 21,838 |
| deterministic | 10 | 1.00 | 5,147 | 20,054 | 31,219 |
| cold_rag | 20 | 1.00 | 6,852 | 9,111 | 9,235 |
| burst | 10 | 0.90 | 7,555 | 15,308 | 20,244 |

## The five failing gates

| Gate | Actual | Threshold | Verdict |
|---|---:|---:|---|
| `success_rate` | 96.7% | ≥ 98% | Half self-inflicted, half unexplained |
| `telemetry_coverage` | 0.0 | ≥ 1.0 | Not a defect: configuration expectation |
| `deterministic_p95_ms` | 20,054 | ≤ 3,000 | Threshold calibrated on localhost |
| `warm_cache_p95_ms` | 4,313 | ≤ 2,000 | Threshold calibrated on localhost |
| `streaming_ttft_p95_ms` | 13,050 | ≤ 10,000 | Threshold calibrated on localhost |

### The three latency gates measure the wrong baseline

`PRODUCTION_P95_LIMITS_MS` was calibrated against a **local** backend. The earlier
`production_hardening_20260808` smoke run recorded `deterministic p95 = 2,940 ms`, just
under the 3,000 ms limit — on localhost, with no network hop and the developer's CPU.

The deployed target is a free-tier Space: 2 vCPU, a network round trip, and two LLM
round trips per structured question (Groq planner, then Gemini composer). Its
deterministic p50 alone is 5,147 ms, already above the limit before any tail is
considered. The only latency gate that passes, `rag_p95_ms`, is the one with a generous
45,000 ms limit.

These thresholds should be recalibrated against the deployment they are meant to
govern, with the new numbers justified rather than fitted to this run. Lowering them
until the run turns green would make the gate meaningless.

### `telemetry_coverage` requires a flag production does not set

The gate counts responses carrying a `telemetry` object, which the API emits only when
`STUDENT_RAG_EVAL_TELEMETRY=true`. The Space runs with it off, which is correct for
ordinary serving. The gate silently assumes the Space is put into evaluation mode for
the duration of a production run. Either the Space sets the flag for such a run, or the
gate should be marked not-applicable when the flag is absent.

### The two payload failures

| Case | Scenario | Error | Latency |
|---|---|---|---:|
| `official_prod_052` | burst | `rate_limit` | 20,244 ms |
| `official_prod_042` | streaming | `RuntimeError`, no message | 21,838 ms |

`prod_052` is largely self-inflicted. Evaluation and production share one Groq/Gemini
key pool by decision, so the burst scenario competes for quota with itself. It is a
real limit of the current key setup, not of the code: `http_429_rate` is 0, so the
throttling happened upstream at the model provider rather than at this service.

`prod_042` is **unexplained**. A `RuntimeError` with no message on the streaming path,
at 21.8 s. Diagnosing it needs the Space logs, which the evaluation harness cannot
reach. It is recorded here rather than dismissed.

### One outlier worth naming

The slowest request of the run was 31.2 s, for the structured directory lookup *"Bộ
phận nào hỗ trợ in tài liệu và giáo trình cho sinh viên"* — roughly six times the 5.1 s
median of its own scenario. Whether this is provider backoff or something else is not
established.

## What this suite does and does not tell you

- It exercises the real transport, the real cache protocol and the real streaming path;
  no other suite does.
- It does **not** judge answer quality. Correctness, faithfulness and citations are
  measured by the generate+judge suite on the library, not here.
- It was run once, against a free-tier deployment, while sharing an API key pool with
  the service under test. Latency figures should be read as "this deployment on this
  day", not as a property of the design.
