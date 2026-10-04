# official_v4 results

246 cases, 229 clusters. The metrics, the cluster bootstrap and the rerun rules
were fixed in `SPEC.md` before the runs; `scripts/report_v4_run.py` computes
them and writes `v4_report.json` into each run directory.

## The two runs

| | Run A | Run B |
|---|---|---|
| System | frozen v4 stack, Voyage `rerank-3` | run A plus the five fixes of 2026-09-30 |
| Commit | `d3db167e` | `c23e027a` |
| Report | `student_handbook_rag_voyage/.../official_v4_answers_20260930T112153Z` | `data/eval/reports/official_v4_answers_20260930T152637Z` |
| Status | **hold-out** | **after fixes, not a hold-out** |

Run A is the hold-out figure: its code predates any knowledge of v4 answers.
The five fixes were written after the 4B ablation was read, so run B measures
the system as it will be deployed but cannot be read as a hold-out.

## Headline

| | Run A | Run B |
|---|---:|---:|
| **answer_correctness** | **0.926** | **0.942** |
| 95% CI over clusters | 0.899 – 0.950 | 0.920 – 0.962 |
| Cases judged | 246 / 246 | 246 / 246 |
| Exceptions, missing reranker, missing dense retrieval | 0 | 0 |

Paired over the 229 clusters, run B minus run A is **+0.016**, 95% CI
**[-0.008, +0.041]**. Over the whole set the difference is not established.

## Where the difference is

Before run B was read, the expectation recorded in the session was that the
fixes should move unaccented questions (the BM25 fix) and directory or service
lookups (the `catalog_relationship` fix), and nothing else. Paired, by cluster:

| Subset | n | B − A | 95% CI |
|---|---:|---:|---|
| Unaccented / typo questions | 37 | **+0.124** | +0.034 – +0.233 |
| Directory and service cells | 30 | +0.063 | −0.003 – +0.148 |
| Everything else | 182 | −0.013 | −0.036 – +0.007 |

Only the unaccented subset clears zero. Its cell figures move with it:
`no_diacritics_or_typos` 0.834 → 0.958 and `D.service_contact` 0.767 → 0.967.

These three subsets are three separate tests, and the subsets were named in the
session rather than written into `SPEC.md` before the run, so this is weaker
than a pre-registration.

## Secondary metrics

| | Run A | Run B |
|---|---:|---:|
| Family A (single lookup, n 90) | 0.934 | 0.955 |
| Family B (several requests, n 66) | 0.885 | 0.910 |
| Family C (cohort comparison, n 24) | 1.000 | 0.987 |
| Family E (conversation, n 24) | 0.942 | 0.929 |
| Family F (boundary, n 30) | 0.960 | 0.957 |
| Hallucination rate | 0.093 | 0.130 |
| Critical false passes | 0 | 0 |
| Faithfulness | 0.958 | 0.955 |
| Citation correctness | 0.944 | 0.965 |
| Context precision / recall | 0.657 / 0.850 | 0.657 / 0.872 |
| Latency p50 / p95 | 16.4 s / 41.8 s | 10.9 s / 23.8 s |

Family D (12 cases) is descriptive: 0.833 → 0.925.

The latency figures are not a property of the system. Both runs were made from
one home network on a day when every provider was slow (a request that runs no
model took 1.5–2.4 s), and run A's higher figure includes its embedding
timeouts. Production latency has to be measured from the deployment.

### The hallucination rate rose while wrong answers fell

Run B flags 32 cases as carrying an unsupported claim against run A's 23, but
23 of those 32 score 1.0 on correctness: the answer is right and the judge
objected to detail beyond the sources. Counting answers instead of flags:

| Correctness | Run A | Run B |
|---|---:|---:|
| 1.0 | 207 | 210 |
| 0.7 – 0.99 | 16 | 18 |
| 0.4 – 0.69 | 13 | 13 |
| below 0.4 | 10 | 5 |
| 0.0 | 5 | 2 |

Most answers below 1.0 in both runs are incomplete rather than false: the judge
rationale is "missing phone", "missing internal number", "missing email", with
faithfulness 1.0.

## The two wrong answers in run B, and what caused them

| Case | What happened |
|---|---|
| V4-003 "GPA 3.75 on the 4-point scale" | Answered "Giỏi", contradicting itself in the same sentence ("3.6 to 4.0 is Xuất sắc"). The correct answer is Xuất sắc, which run A gave. |
| V4-204 "what does the student support centre do" | Refused. Run A answered correctly. |

Neither follows from a fix. In V4-003 the query plan and the resolved
structured row are byte-for-byte the same in both runs — the same table, the
same row — so only the composer differs. In V4-204 the planner classified the
question as `scholarship_classification` instead of `office` and so read the
wrong table; both runs were in `standalone` mode, which the `query_plan` fix
does not touch.

Both are run-to-run variance, and both cases are single-case clusters, so no
near-duplicate corroborates either score. The system produces a different
answer to the same question on a rerun often enough to turn a correct answer
into a wrong one; the paired interval above already carries this noise.

## Reruns

The timeout rules of `SPEC.md` were applied from the run logs, before any score
was opened.

| | Cases rerun | Reason |
|---|---:|---|
| Run A, attempt 1 | 108 | at least one search fell back to BM25 because the embedding call passed 5 s |
| Run A, attempt 2 | 3 | reranker lost to a connection error |
| Run A, judge retry | 1 | V4-056, the judge returned an empty string (the full rerun in attempt 1 judged it) |
| Run B, attempt 1 | 2 | reranker lost to a connection error |

The dense-retrieval rule was added **after** run A's first scores had been
read, so run A's first-run figure is reported beside it: 0.927 over the 245
cases the judge answered on, against 0.926 over 246 after the reruns. The 108
degraded cases had scored 0.932 and the 138 intact ones 0.924, so the fallback
to BM25 did not cost run A its headline.

Reruns and run B used `configs/retrieval_eval_patient.yaml`, which raises the
embedding and reranker waits to 30 s and changes nothing else. Deployment keeps
`configs/retrieval.yaml`.

## Ablations

Two earlier v4 runs, both on the frozen stack, both before the Voyage switch:

| Run | Reranker | Note |
|---|---|---|
| `official_v4_answers_20260930T060046Z` | Qwen3-Reranker-8B on DeepInfra | 105 of 246 cases lost the reranker to endpoint stalls; not comparable |
| `official_v4_answers_20260930T063041Z` | Qwen3-Reranker-4B on DeepInfra | complete after 5 timeout reruns |

The reranker choice itself was measured on `official_v1` with one shared set of
24 candidates per question (`data/eval/reports/reranker_compare_v1/`):

| Reranker | Gold first | Gold in top 5 | Latency p50 |
|---|---:|---:|---:|
| RRF only | 0.826 | 148/155 | — |
| Qwen3-Reranker-4B | 0.903 | 153/155 | 1.40 s |
| Qwen3-Reranker-8B | 0.923 | 155/155 | ~2 s, p90 4.7 s |
| **Voyage rerank-3** | **0.942** | **155/155** | **0.76 s** |
| Voyage rerank-3-lite | 0.929 | 154/155 | — |

## Run C: the system after reading the v4 answers (2026-10-01)

Run C contains every fix of 2026-10-01: the registry fields, the directory
labels, the handbook labels and currency notes, the minimum levels, and
planner v56 (see `docs/DESIGN_DECISIONS.md`). Most of them were written after
reading v4 answers, so run C is **not a hold-out**.

| | |
|---|---|
| Commit | `1a9ccd3d`, clean tree |
| Report | `data/eval/reports/official_v4_answers_20261001T082203Z` |
| Retrieval | patient config, Voyage `rerank-3` |
| Answers | 246/246, no exceptions |
| Dense-retrieval failures | 0 (log check), so no rerun |
| Reranker fallbacks | 0 (log check), so no rerun |
| Latency p50 / p95 | 10.3 s / 18.9 s (run B: 10.9 s / 23.7 s) |

**Judge provider.** The Groq keys reached their daily token cap after 7 of
246 judgements. Run C and run B were therefore both judged again by the same
model, gpt-oss-120b, served by DeepInfra (`scripts/rejudge_run.py`, results in
each run's `judge_deepinfra/`). The DeepInfra request asks for medium
reasoning and has an output cap of 4,096 tokens. V4-111 and V4-117 had run
out at 1,536 tokens before writing the JSON.

The two providers agree on run B's answers:

| | Result |
|---|---|
| Mean, Groq / DeepInfra | 0.942 / 0.937 |
| Identical scores | 206 of 246 |
| Within 0.25 | 236 of 246 |
| Same pass decision at 0.8 | 232 of 246 |
| Within 0.25 of the second rater's 66 scores, Groq / DeepInfra | 52 / 54 |

Scores from the two providers are not mixed in one comparison.

| Judged by DeepInfra | Run B | Run C |
|---|---:|---:|
| **answer_correctness** | 0.937 | **0.959** |
| 95% CI over clusters | 0.913 – 0.959 | 0.938 – 0.978 |
| Hallucination rate | 0.122 | 0.102 |
| Answers scoring 0.0 | 4 | 4 |
| Critical false passes | 0 | 0 |

Paired over the clusters, run C minus run B is **+0.022**, 95% CI
**[-0.001, +0.045]**. The CI touches zero, so the improvement is likely but
not established. 14 cases moved up by 0.25 or more and 5 moved down.

**Reading of the cases.** Two criteria were fixed before the scores were
read: a regression caused by the fixes, or a serious false statement not
already known. Neither was met.

- The 5 cases that moved down:
  - V4-072 and V4-145 have the same plan as in run B, and both answers give
    what was asked; the score moved with the judge or the composer.
  - V4-049 (service contact sent to RAG) and V4-209 (pronoun follow-up
    answered with a clarification) are planner variance. Planned 6 times
    each, v56 chose the lookup 5/6 and 5/6, against v53's 4/6 and 3/6.
  - V4-175 picked the ungraded pass/fail lookup. The composer then left the
    4,8–5,4 band unanswered while the row was in its evidence. v56 kept the
    two scoring lookups in 4 of 6 plans against v53's 6 of 6, a difference
    too small to read; it is kept as a case to watch.
- Every flagged or unfamiliar answer below 1.0 was read: V4-111, V4-114,
  V4-118, V4-144, V4-147, V4-181, V4-218, V4-236 and V4-035. None states
  something false.
  - V4-114's "đầu tháng 10/2025" deadline for first-year students is in the
    K51 notice.
  - V4-147 contains the GPA that the judge called missing.
  - The rest are the known incomplete answers.

A Groq judgement of run C, for continuity with the run A and run B figures
above, is scheduled after the daily cap resets. It does not change the
comparison above, which uses one provider for both runs.

## Planner v61, then table search (2026-10-04)

Post-fix measurements, judged like Run C (gpt-oss-120b on DeepInfra, packet
`judge-packet-v3-source-clauses`), with the composer on DeepInfra at low reasoning.

| | Run C (rejudged) | v61, v35 | v61, table search |
|---|---:|---:|---:|
| Commit | `1a9ccd3d` | `9111b71f` | `5a7797de` |
| answer_correctness | 0.961 | 0.960 | 0.966 |
| 95% CI over clusters | — | 0.942 – 0.977 | 0.949 – 0.981 |
| Answers scoring 0.0 | 4 | 1 | 0 |
| Critical false passes | 0 | 0 | 0 |

- v61 against Run C: paired 0.000, CI [−0.023, +0.025]; 8 cases fixed, 10
  lower, none with a serious falsehood (read case by case; V4-169, the only 0,
  is a judge error).
- Table search against v61 on the same replayed plans: paired +0.005, CI
  [−0.008, +0.020], no new 0. The pre-registered rule in `SPEC.md` is met.
- Reruns: v61 V4-111 and V4-210 (composer timeout) and V4-234 (judge timeout);
  table search V4-164 (composer timeout). No reranker was skipped.
- Reports: `official_v4_answers_20261004T104406Z`,
  `official_v4_answers_20261004T124930Z`.

## What these results do not establish

- **Run B is not a hold-out.** Its figure describes the deployed system; the
  hold-out claim rests on run A alone. The same holds for run C.
- **Three of the five fixes are unmeasured here.** The unaccented gain is
  attributable to the BM25 fix. The `query_plan` follow-up fix was compared on
  `official_v2`'s 25 follow-ups and changed 6 questions without losing or
  gaining a scope term: it passes its criterion, but no benefit was shown. The
  `scholarship_lookup` and `foreign_language_lookup` fixes have regression
  tests and no measured effect on v4.
- **The judge is not calibrated against the owner.** Every figure here is one
  model's reading. It was compared only with a second model
  (`judge_calibration/`): no false pass among 30 perfect scores, and stricter
  than the correctness criterion on the rest. Its flagging of correct answers
  as unsupported is visible in the 23 cases above.
- **The structured-lookup audit is blind to the five fixed bugs.** Run against
  the code before the fixes it also reports no findings, which is stated in
  `scripts/audit_structured_lookups.py`. It establishes row selection, not
  label matching.
- **The mix is designed, not natural.** Multi-request and boundary questions
  are over-weighted on purpose, so the overall mean is not an estimate of
  accuracy on real student traffic.
- **The questions are synthetic.** They were authored from the handbook, not
  collected from students.
