# Design decisions and the measurements behind them

Every component of the current system was chosen by measuring it against the
alternatives. This document collects those comparisons in one place: what was
compared, on which data, what the numbers were, and why the choice was made.
The dated logs of each experiment are in [archive/](archive/README.md); the raw
reports are listed at the end.

## How to read the numbers

- **Almost every number is a development measurement.** `official_v1` (135
  deterministic, 155 retrieval and 150 answer cases) was used to tune prompts
  and pick models, so its scores are optimistic. `official_v2` is spent in the
  same way. The 21 questions in `data/eval/development/supplementary_questions.yaml`
  are development questions for the new v35 content.
- **The hold-out is `official_v3`.** Its planner suite was run once, on
  2026-09-27 (below). No result from it may be used to change the system; any
  later run of it is a post-fix measurement.
- **Noise.** On the 135-case deterministic suite, a small prompt change flips
  2–3 borderline cases either way, so a difference of 3 or fewer cases is
  treated as a tie. Paired comparisons use McNemar's test on the cases where
  the two arms disagree.
- **Answer quality** comes from an LLM judge (`openai/gpt-oss-120b`) whose
  agreement with a human rater has not been measured.

## Summary

| Component | Chosen | Alternatives measured | Deciding evidence |
|---|---|---|---|
| Planner | OpenAI `gpt-6-luna`, reasoning medium, strict schema, prompt v53 | Qwen3.8 on Groq, Cohere Command A+, DeepSeek flash (none, low, medium) | 133/135 on v1 with p95 5.8 s; DeepSeek low 128/135 with p95 18 s; Qwen lost 28 requests to free-tier limits |
| Composer | DeepSeek flash, thinking off, prompt v3.30 | Gemini 3.1 Flash-Lite; DeepSeek thinking low | Same quality as Gemini with 0 failures against 20/150; thinking low no better with v3.30 and 3 s slower |
| Directory selection | Exact name, otherwise DeepSeek picks from the closed catalog | Fuzzy-score thresholds | Development cases: 10 wrong units under thresholds, 0 with the selector |
| Embedding | `BAAI/bge-m3` over the DeepInfra API | Local `bge-m3`; Qwen3-Embedding-8B | API vectors identical to local; Qwen3-8B ties after reranking, with query p50 6.3 s against 1.3 s |
| Reranker | Qwen3-Reranker-8B on DeepInfra, on all 24 fused children | None; Cohere rerank-v4.0-fast; Qwen3-Reranker 0.6B, 4B | hit@1 0.923 / hit@5 1.000 against Cohere 0.897 / 0.981 and none 0.832 / 0.955 |
| Lexical search | BM25 fused with RRF (k = 60), scored by BM25 only | Dense only; BM25 with a title-match rule | RRF + rerank beats dense + rerank; the title rule cost hit@1 and 3× BM25 time |
| Candidate depth | 24 children for dense, BM25, fusion and rerank | 16, 40 | 24 holds the first gold child for 155/155 questions, 16 for 154/155 |
| Tables | Reviewed JSON tables for lookup; readable tables kept in parents; no table rows embedded | The composer reading tables from retrieved text | The composer picked the wrong row of a range table in every try (sup_05, grade_remaining) |

## Planner

The planner turns one message into typed tasks (structured lookup, RAG or
clarify). All runs below are the 135-case `official_v1` deterministic suite
unless stated.

| Date | Setup | Passed | Latency | Notes |
|---|---|---:|---|---|
| 2026-09-10 | Qwen3.8 low (Groq), prompt v41 | 123/135 | median 1.8 s | Baseline |
| 2026-09-10 | Qwen3.8 low, prompt v42 | 129/135 | | Control codes shown with their meaning; McNemar p = 0.07 against v41 |
| 2026-09-12 | Qwen3.8 low, prompt v43 | 129/135 | p95 5.8 s | Baseline for the DeepSeek comparison; 0 fallbacks |
| 2026-09-11 | Cohere Command A+, thinking budget 2048 | 105/135 | median 5.8 s | 20 cases lost against Qwen, 2 won (p = 0.0001) |
| 2026-09-25 | DeepSeek flash, thinking off, prompt v43 | 123/135 | p50 1.2 s, p95 3.4 s | McNemar p = 0.03 against Qwen; the 6 losses are simple tool-scope choices |
| 2026-09-25 | DeepSeek flash, thinking low | 128/135 | p50 5.1 s, p95 18.1 s | 0 fallbacks |
| 2026-09-25 | DeepSeek flash, thinking medium | 127/135 | p50 4.8 s, p95 19.4 s | 2 fallbacks from overthinking "khoa đó" follow-ups |
| 2026-09-26 | Qwen3.8, full v1 on free keys | 100/135 | | 28 request failures from free-tier limits; not a clean baseline |
| 2026-09-27 | Luna v51, strict schema, medium | 129/135 | p95 6.1 s | 0 request failures, 0 fallbacks |
| 2026-09-27 | Luna v52 | 133/135 | p95 5.8 s | General rules for score formats, levels and unit/office fields |
| 2026-09-27 | Luna v53 (final) | 133/135 | median 5.2 s | Restores four "only if" conditions for merging tasks |

**Hold-out.** Luna v52 on `official_v3` (132 cases, 2026-09-27): **115/132 =
87.1%** (95% CI 80.3–91.8), p95 7.7 s. The main failure: two regulation
questions merged into one RAG task (8 cases). Prompt v53 was written after this
run, so any later v3 run is post-fix; 87.1% stays the clean result. On the 6
`official_v2` two-regulation cases, v53 passed 5/6 against v52's 3/6, and it
did not over-split the 4 cross-cohort comparisons (4/4 both).

**Why Luna.** Luna and DeepSeek low are within noise on accuracy (133 against
128), but Luna's p95 is about 6 s against 18 s, it had no failed requests, and
the strict JSON schema removes the parsing fallback. Qwen on free Groq keys was
accurate (129/135) but not dependable: the same suite lost 28 requests to rate
limits. Cohere was clearly worse. A golden test
(`tests/fixtures/luna_planner_request_v53.json`) proves production sends the
exact request that was measured.

**Failures that persist across models** (093/096: "ở phòng nào" read as the
office field instead of the unit; 033/122: one task or two) point to ambiguous
definitions rather than model quality; the answer still names the right unit.

## Composer

The composer writes the answer from the evidence packet only.

**Gemini 3.1 Flash-Lite against DeepSeek flash** (2026-09-27, prompt v3.25,
150 `official_v1` answer cases, identical Luna plans for both arms):

| | DeepSeek flash (thinking off) | Gemini 3.1 Flash-Lite |
|---|---:|---:|
| Failed calls | 0/150 | 20/150 (free-tier 429, all 8 keys limited) |
| Correctness (130 cases both answered) | 0.997 | 0.997 |
| Faithfulness | 0.988 | 0.984 |
| Unsupported claims | 1 | 6 |
| Cases judged good (paired) | 128 | 124 (McNemar p = 0.29) |
| Composer latency median / p90 / max | 1.47 / 2.4 / 4.5 s | 1.65 / 4.1 / 23.5 s |
| Median answer length | 384 characters | 204 characters |

Quality is the same; DeepSeek made fewer unsupported claims, never failed and
has a far shorter latency tail. Only 111/150 packets had identical sources
(Cohere trial rerank varied between calls); on that subset p = 0.69.

**Thinking off against low.** With prompt v3.29, thinking off read the wrong
row of the conduct-deduction table in every try (sup_05: "2 điểm", the
"khiển trách" row) while low got it right, which argued for low. Prompt v3.30
instead tells the composer to read table rows as labelled lines and to copy
contacts verbatim. Measured on 169 answers (150 `official_v1` + 19 development
questions), same recorded evidence packets:

| Prompt v3.30 | Thinking off | Thinking low |
|---|---:|---:|
| Composer time p50 / p90 | 1.4 / 2.4 s | 4.3 / 11.2 s |
| sup_05 deduction | 3 points (correct, ≥ 9/10 tries) | 3 points (correct) |
| 19 development questions, all facts present | 16/19 | 16/19 (same 3 misses, none from the composer) |
| Notices state their school year | 6/6 | 6/6 |
| Emails, phones and links changed from the source | 0 | 0 |

Thinking off was kept: it is as accurate on every check that needs no judge and
about 3 s faster per answer. The judge scores for this pair were not collected
(the Groq judge ran out of daily quota); the final judge pass is planned for
the hold-out. Earlier, the judge gave thinking low (prompt v3.29, v34 data) 0.990
correctness against 0.998 for thinking off (an earlier prompt, v33 data), so
that pair is confounded; two of low's flagged cases were judge disagreements
on near-identical answers.

## Directory selection: thresholds replaced by an LLM over a closed list

Service, office, faculty and program questions must pick records from a
catalog. Until 2026-09-28 this used fuzzy name scores with fixed thresholds
(confidence 0.62/0.72, margin 0.08) that had no recorded basis. A calibration
harness (commit `7ccf22ed`) showed that tuning the thresholds could not fix
it: lexical scores are inflated by common words, and the ranking itself was
the problem. The replacement picks a record whose name or curated alias
equals the question's entity; otherwise DeepSeek (thinking off, JSON output)
chooses ids from the cohort's catalog, and any malformed reply, unknown id or
API failure asks the student instead of guessing.

Labelled development cases, same cases before and after (commit `516c39b2`):

| Catalog | Thresholds | LLM over the closed list |
|---|---|---|
| Services (57) | 32 correct, 3 wrong units | 56 correct, 1 clarification, 0 wrong |
| Offices (45) | 37 correct, 2 wrong | 45 correct |
| Faculties (44) | 34 correct, 1 wrong | 43 correct, 1 miss |
| Programs (45) | 38 correct, 4 wrong, 1 incomplete | 45 correct |

A wrong unit is the costly error (the student is sent to the wrong office),
and it went from 10 to 0. The selector prompt was revised once on these cases,
so they are optimistic. Selector prompt v2 (commit `91f80319`) accepts a whole
question and several named units: whole `official_v1` questions as input went
from 22/27 to 27/27. Removing guessed keyword aliases and records the
handbooks do not list (commit `c0d1a760`) kept 189/191 development cases with
0 wrong units; `official_v1` deterministic stayed at 134/135.

## Retrieval

All retrieval numbers: 155 `official_v1` questions, top 5 parents, gold =
the parent article that answers the question.

### Embedding

| Arm | Qwen3-Embedding-8B hit@1 / hit@5 / MRR@5 | BGE-M3 hit@1 / hit@5 / MRR@5 |
|---|---|---|
| Dense | 0.839 / 0.968 / 0.887 | 0.800 / 0.968 / 0.867 |
| Dense + BM25 (RRF) | 0.839 / 0.981 / 0.892 | 0.832 / 0.955 / 0.882 |
| Dense + Cohere rerank | 0.865 / 0.974 / 0.908 | 0.884 / 0.968 / 0.920 |
| RRF + Cohere rerank | 0.884 / 0.987 / 0.924 | 0.897 / 0.981 / 0.932 |

The stronger embedding wins alone and ties once a reranker reorders the
candidates. Its query latency on DeepInfra's shared endpoint was p50 6.3 s,
p90 26.6 s, max 51.6 s, against about 1.3–1.4 s for BGE-M3. DeepInfra's
`BAAI/bge-m3` returns vectors identical to the local model (cosine 1.00000 on 8
texts), so moving it to the API changed no ranking; it frees the free-tier
Space's CPU and lets several students be served at once.

### Reranker

The first reranker experiment (2026-09-09, Cohere rerank-v4.0-fast on the top
16 RRF children, 157 retrieval events) raised hit@5 from 0.949 to 0.975 and MRR
from 0.874 to 0.940; answer-level scores moved less (correctness 0.951 to
0.960, hallucination rate 0.067 to 0.053). Cohere was added as a fail-open
stage. On 2026-09-29 the same 24 RRF candidates (BGE-M3, v35 data) were
reranked by each candidate:

| Reranker | hit@1 | hit@3 | hit@5 | MRR@5 | Latency per call |
|---|---:|---:|---:|---:|---|
| None (RRF) | 0.832 | 0.935 | 0.955 | 0.882 | |
| Cohere rerank-v4.0-fast | 0.897 | 0.961 | 0.981 | 0.932 | p50 0.74–0.97 s, max 8.4 s |
| Qwen3-Reranker-0.6B | 0.858 | 0.942 | 0.955 | 0.901 | p50 1.3 s, max 2.7 s |
| Qwen3-Reranker-4B | 0.903 | 0.987 | 0.987 | 0.942 | p50 1.4 s, two calls timed out at 90 s |
| **Qwen3-Reranker-8B** | **0.923** | **0.994** | **1.000** | **0.956** | p50 1.6 s, p90 4.7 s, max 9.3 s |

Against Cohere question by question, the 8B model moves 7 questions into first
place and 3 out; it brings the 3 questions every earlier setup missed (014,
038, 080) into the top 5 and loses none. On the 21 development questions it
drops one from the top 5 (sup_20, where another article also answers). Cohere
was dropped as well because its production use is paid and its trial keys
skipped reranking on most calls of some runs (18/155 applied), silently
lowering hit@1 to the RRF level. The timeout is 10 s: at 8 s, 3 of 30 live
calls fell back to RRF. Any failure keeps the RRF order.

### BM25, fusion and depth

- **Fusion.** Without a reranker, adding BM25 raises hit@1 (0.800 to 0.832) and
  costs one hit@5 case; with the reranker, RRF + rerank beats dense + rerank on
  every measure (0.897 / 0.981 against 0.884 / 0.968 with Cohere). BM25 also
  keeps retrieval alive when the query embedding fails.
- **Title rule removed.** BM25 used to promote children whose title matched the
  query. With a two-word minimum it fired on 32/155 queries (mostly the generic
  titles "Sinh viên" and "Học bổng") and lowered RRF hit@1 to 0.813; with a
  three-word minimum and with no rule, hit@1 was 0.832 either way, and the three
  queries it still fired on ranked the gold parent first after reranking
  anyway. Without the rule BM25 takes 28 ms instead of 93 ms (p50). Removed in
  `1d4705f5`.
- **Depth.** Where the first gold child sits in the RRF list: within 16 for
  154/155 questions, within 24 for 155/155, within 40 for 155/155 (median
  distinct parents 8, 11 and 18). All stages use 24: it is the smallest depth
  that holds every gold child, and a reranker call on 24 short children stays
  within the latency budget.
- **Parent grouping.** Children are grouped by parent and a parent is scored by
  its best child, so several children of one article cannot push other
  articles out of the top 5.

## Corpus and tables

- **Small children, full parents** (2026-09-06, v32 against the reviewed
  parent/child build, 179 cohort units): RRF hit@5 100% in both; required-source
  recall 98.6% in both. Removing table rows from the embedded text lowered the
  ranking of a few table-value questions (8 table/policy questions: MRR@5 0.917
  to 0.729), which is why table questions go to structured lookup instead of
  retrieval, while the parents keep the tables as readable Markdown for the
  composer.
- **Structured lookup instead of the composer reading tables.** Two measured
  failures: the composer reported a failing K51 score of 5.2 as a pass by reading
  the wrong interval (grade_remaining; fixed by resolving the row in code), and
  with prompt v3.29 it read the adjacent row of the conduct-deduction table in
  every try (sup_05). Range tables are resolved in code and handed to the
  composer as a fact lock; `official_v1` deterministic is 134/135 with them.
- **v35 data.** On the 155 `official_v1` questions, retrieval on v35 is identical
  to v34, so the new content (GPA formula, Decree 116 links, the faculty tasks
  page, main-campus scope) added no noise. All 21 development questions about it
  retrieve a correct source (before the reranker change).

## Final system check (2026-09-29)

The complete current stack, on development data:

- **Deterministic `official_v1`:** 131/135 under the older v9 contract; the 3
  cases it disagreed on (096, 114, 119) pass under the v10 contract the
  baseline used, leaving only 003, a case that flips between Luna runs.
- **21 development questions end to end:** route 21/21, retrieved source 20/21,
  facts 19/21 by the automatic criteria; reading the two fact misses, both
  answers are correct and the criteria were too strict.
- **Equivalence of the 2026-09-29 refactor:** the refactored code produces
  identical planner requests, plans, structured results and answers on 23,016
  offline scenarios and 49,760 fuzzed plans (see the refactor commits).

## What these measurements do not show

- A comparison with plain RAG (no planner) or with a long-context model given the
  whole handbook; these baselines are planned for the paper.
- End-to-end answer quality of the final stack on a hold-out; it will be judged
  once on `official_v3`.
- The judge's agreement with a human rater; both datasets were written by one
  author from handbook content, not collected from real students.
- Combinations not run, such as Qwen3-Embedding-8B with Qwen3-Reranker-8B.

## Raw reports

Evaluation reports are git-ignored and stay on the development machine under
`data/eval/reports/`:

| Measurement | Report |
|---|---|
| Composer Gemini against DeepSeek | `official_v1_answers_20260927T124310Z` (DeepSeek), `official_v1_answers_20260927T131333Z` (Gemini) |
| Luna v51 / v52 on v1, v52 on v3 | `official_v1_deterministic_20260927T092317Z`, `…T101327Z`, `official_v3_deterministic_20260927T103000Z` (results also in `data/eval/official_v3/RESULTS.md`) |
| Directory matching | `directory_matching_20260927T…` and `…20260928T…`; `service_matching_calibration_*` for the thresholds |
| Retrieval, reranker, embedding, depth, BM25, thinking | `measurements_20260928/` (its README lists each script, commit and result file) |
| End-to-end development questions | `supplementary_questions_20260928T231521Z` |
