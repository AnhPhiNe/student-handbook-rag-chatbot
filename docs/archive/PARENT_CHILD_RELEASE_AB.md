# Parent/child corpus A/B — 2026-09-06

## Scope and identity

This is a targeted corpus ablation, not a new holdout score or an end-to-end
Planner evaluation. It compares local snapshots of the old v32 corpus with the
new reviewed parent/child build. No live collection or deployment was changed.

- Baseline build: `build-02a2eed8dae5b4307427`; candidate:
  `build-934f1caf384f99ad96e9`.
- Runtime checkout: `9098f655`, with uncommitted build/test/documentation changes.
  Exact harness/runtime/config/corpus hashes are in `ab_identity_answers.json`.
- Local exact-cosine Qdrant plus production RRF/grouping/graph, no reranker.
  Exact-content vectors reused from the previously verified local cache.
- Composer: `gemini-3.1-flash-lite`, temperature 0; response cache disabled.
- Twelve pre-existing diagnostic questions, each generated once per arm: 24
  successful answers, no API errors or cached answers. Arm order alternated.
- Planner is replaced with fixed RAG task plans. The compound case uses two RAG
  tasks, **not** a structured-plus-RAG plan. This tests table misrouting tolerance,
  not the normal structured resolver or Planner task selection.
- Model calls were explicitly authorized by the user. No private chat history
  was included. No additional model judge or repeat generation was run.

## Retrieval results

The broader set has 155 questions expanded to 179 cohort execution units. Queries
are supplied directly to retrieval; these metrics do not include Planner or the
answer pipeline's query expansion.

| Metric | Old | New |
|---|---:|---:|
| Dense source Hit@5 | 164/179 (91.62%) | 164/179 (91.62%) |
| RRF source Hit@5 | 179/179 (100%) | 179/179 (100%) |
| RRF macro required-source recall@5 | 98.60% | 98.60% |
| RRF MRR@5 | 0.9555 | 0.9555 |
| RRF binary nDCG@5 | 0.9553 | 0.9553 |
| Invalid source-cohort matches | 0 | 0 |

This binary nDCG uses grade >= 2 relevance and is not the official graded nDCG.
Local exact search also does not establish hosted approximate-search latency.

Targeted diagnostics expose a tradeoff that the broader aggregate does not:

| Diagnostic group | Old RRF Hit@5 | New RRF Hit@5 | Old/new MRR@5 |
|---|---:|---:|---:|
| Eight table/policy/compound questions | 8/8 | 7/8 | 0.9167 / 0.7292 |
| Four source-layout/amendment questions | 4/4 | 4/4 | 1.0000 / 0.6875 |

Dense hits in these groups are respectively 8/8 versus 8/8 and 4/4 versus 3/4.
Removing table rows can lower ranking for table-value questions. The lost direct
RRF hit is the K50 82-point conduct classification question; it remains reported.

## Final-answer audit

Codex reviewed all 24 answers against the prepared authorized evidence packets,
approved JSON and article text. This is **agent review**, not independent human
review or a blinded external judge. The rubric was recorded after generation:
correct requested values, applicable cohort/amendment, all requested alternatives,
material eligibility exceptions, and supporting article references. Thus these
counts are diagnostic observations, not publication-ready benchmark metrics.

| Question ID | Old | New | Finding |
|---|---|---|---|
| `duration_bridge` | Pass | Pass | K48–49 college bridging: 1.5 / 3 years |
| `duration_part_time` | Pass | Pass | K50 first-degree part-time: 5 / 9 years |
| `academic_classification` | Pass | Pass | GPA 3.3: Giỏi |
| `conduct_classification` | Pass | Pass | 82 points: Tốt, supported in packet |
| `grade_remaining` | Fail | Pass | Old says C/pass; correct K51 result is D+/not pass |
| `scholarship_policy` | Pass | Incomplete | New omits exclusion of bridging students |
| `retake_policy` | Pass | Pass | Highest achieved score becomes official score |
| `compound_det105_regression` | Pass | Pass | Both requested topics answered |
| `review_duration_k51_regular` | Pass | Pass | Amended 4 / 6 years |
| `review_duration_k51_parttime` | Pass | Pass | Amended maximum 7.5 years, not historical 9 |
| `review_foreign_two_columns` | Pass | Pass | All eight TOEIC component ranges correct |
| `review_scholarship_merged_rows` | Incomplete | Pass | New includes both Giỏi combinations |

Under this rubric: old **10/12**, new **11/12**; two improvements, one regression,
nine unchanged passes. `status=answered` alone was not treated as a quality pass.
Small samples and one stochastic generation per arm cannot establish a reliable
improvement or prove that corpus changes caused every output difference.

### The scholarship omission is not missing corpus evidence

Both packets contain Article 26(1)(b): bridging students are not eligible for the
encouragement scholarship. The new answer lists the principal Article 27 criteria
but omits this exclusion; the old answer includes it. The fact was not removed by
table separation. This is an observed Composer completeness failure with available
evidence. No prompt patch or rerun was used to conceal it.

### Why the 82-point answer still works

The direct retrieval diagnostic uses the original query. The answer pipeline
expands it with “đánh giá và phân loại kết quả rèn luyện”; both answer preparations
then include Article 9 as primary evidence and the full readable table. Therefore
both final answers correctly say Tốt. These are different query paths, not a
contradiction or proof that the original retrieval loss disappeared.

**Excluding table rows from embeddings does not exclude them from Composer.**
The unchanged production pipeline can authorize full parent article evidence,
including its table, after narrative retrieval. Structured JSON remains the
deterministic lookup source. No new table fallback was added for this experiment.

All 24 prepared packets passed source-cohort/applicability checks; a shared source
with validated applicability is not counted as leakage just because its source
document was published for another cohort. The harness output's top-level cohort
is `default`; this audit uses explicit task/packet cohorts, not that transport
field. No unsupported cross-cohort answer claim was observed in this sample.

## Decision

The corpus separation/build is technically viable: the broad retrieval aggregate
is unchanged and the targeted final answers are mostly preserved, with two useful
improvements. It is **not** a zero-regression result: there is one eligibility
omission and reduced ranking resilience on table queries.

Do not automatically promote based on the net 10/12 → 11/12 count. Report these
tradeoffs to the user and obtain a release decision. No runtime optimization,
new evaluation suite, or repeated generation is required to report this result.
If the limitation is accepted, use new versioned collections and the existing
preflight/verification/smoke workflow, retaining v32 for rollback.

## Evidence files

Outputs are isolated in `work/parent_child_release_ab/`:

- `answers.jsonl`: all 24 final results; SHA-256
  `54a2814a2a7602c454f7f42c9ea7cca8e8e73b270ea40777e3c5e2293b5aa965`.
- `answer_packets.jsonl`: separately prepared evidence/prompts; SHA-256
  `caf5ea918041dce7298a4fefea03a1541665f9e128a61486a30fbd4c10ba2057`.
- `agent_answer_audit.json`: per-case judgments and rubric.
- `ab_identity_answers.json`: generation/corpus provenance; SHA-256
  `ebf0c88b72b7338712a90558db332c9fb7318135210e969ff0f81c697a712fdb`.
- `hybrid_*.json`, `ab_retrieval_summary.json`: saved retrieval and metrics.

Prepared packets are not provider-captured request logs. The same unchanged
preparation code and inputs were used for generation; answers are preserved
without reruns. Earlier reports remain historical and are not silently replaced.

### Subsequent prompt clarification (not part of this A/B)

After reviewing these results, the user authorized clarifying the Composer's
existing scope rule. Version `student-handbook-answer-v3.23-material-exceptions`
explicitly includes material exclusions from other authorized articles while
excluding unrelated exceptions. It adds no scholarship-specific example, routing
rule, or extra model call. The 24 answers above used v3.22 and were not rerun;
their scores do not measure compliance with the new prompt. Synthetic contract
tests cover the instruction and evidence retention, not live model behavior.
