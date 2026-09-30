# official_v4: an independently authored hold-out

official_v4 measures the whole system, from the student's message to the final
answer, on questions the system was never tuned on and that neither the system's
author nor its models wrote.

## Why a new set

- `official_v3` is no longer a clean hold-out: prompt v53 was written after its
  run. Its 87.1% (2026-09-27) stays the pre-fix planner result.
- `official_v1`, `official_v2` and `official_v3` were all written by Claude, and
  the planner prompt was tuned on v1 and v2. A new set from the same author would
  share their phrasing, so v4 is written by a model from another vendor.
- v3 has only a planner suite; v4 has answer gold from the start.

## Rules

1. **No result from v4 may change the system.** Prompts, catalogs and code are
   tuned on v1, v2 and the development sets only. Any later v4 run after a fix
   is a post-fix measurement and is labelled so.
2. **The draw is frozen before any question exists.** `scripts/draw_v4_tickets.py`
   (seed 20260930) writes `tickets.json`; it refuses to overwrite it without
   `--force`, which is allowed only before authoring starts.
3. **The author does not see the system.** It gets `GEMINI_PROMPT.md`, one batch
   of tickets and the public handbook excerpts in that batch. Never the code,
   prompts, catalog internals, design notes or known failures.
4. **Questions are not edited after authoring.** A case is dropped only for a
   stated reason (a false fact in the draft gold, a ticket marked
   `khong_phu_hop`, a near-duplicate of v1–v3), logged before any run.
5. **Run once**, end to end, on the frozen final system.

## Allocation (246 tickets)

| Family | Cells | Tickets |
|---|---|---:|
| A. Single request | 9 table or directory lookups × 6 (grade scales, foreign language, study duration, scholarship, formulas, offices, faculties, programmes, student services); regulations: policy 10, procedure 10, consequence or exception 10, open 6 | 90 |
| B. Several requests | table + regulation 18, regulation + regulation 18, table + table 18, three requests 6, four or five requests 6 | 66 |
| C. Comparison | two cohorts on a table 9, two cohorts on a regulation 9, two rows of one table 6 | 24 |
| D. Relation | programme → faculty contact 6, service → unit contact 6 | 12 |
| E. Conversation (two turns, the second is scored) | cohort switch, entity switch, pronoun, topic switch, 6 each | 24 |
| F. Boundary | missing information 6, partly answerable 6, in domain but not in the handbook 8, out of domain 6, mixed 4 | 30 |

- **Size.** 246 cases give an overall 95% interval of about ±4 points at 90%
  (v3: ±6 with 132); clustering widens it a little. Families of 24 or more are reported on their own (about
  ±12 points); cells of 6 are descriptive only.
- **Cohorts.** Tickets rotate K48-K49, K50 and K51 within each cell. The six
  foreign-language table tickets are all K50, because only the K50 handbook has
  the certificate equivalence table; a ticket always takes its source's cohort.
- **Styles** over the base tickets, assigned at random: natural 50%, informal
  20%, no diacritics or typos 15%, long context 15%.
- **Repeated content.** The three cohorts' handbooks share many articles and the
  two formulas, so some tickets ask the same thing. Cases whose required facts
  overlap by 80% or more (word 3-grams) are scored as one cluster, decided from the
  authored gold before any run. This only widens the intervals.
- **Over-limit tickets** (four or five requests) accept either answering them or
  asking the student to choose at most three.
- **Missing-information tickets** (`F.clarify`) accept either asking for the
  missing detail or answering every case with its condition (e.g. both study
  forms' maximum durations). The owner judges an answer by whether it answers the
  question, and extra information is fine; decided 2026-09-30, before any run.

## What the draw samples

- **Tables:** a random row of a reviewed table (grade scales, classifications,
  scholarship, study duration, the language table) or a formula; the excerpt is
  the handbook article that prints the table.
- **Directories:** a random office, faculty, programme or student-service record,
  with its contact lines only.
- **Regulations:** a random handbook article, excluding articles that print a
  lookup table, articles under 300 characters, and administrative articles no
  student asks about (scope, entry into force, duties of ministries or units,
  budgeting), matched on the article title. Procedure tickets draw only from
  articles that mention a file, a procedure or a submission; consequence tickets
  only from articles that mention a sanction, a prohibition or an exception.
  When an article still cannot carry the ticket's question kind, the author asks
  something else the article states and records the kind in `ghi_chu`.
- **Main campus only:** records and articles naming the branch campus
  (Phân hiệu Long An) are left out. The filter matched "phân hiệu" and "Long An" only, so K51
  faculty records of both branches whose text says neither (emails such as
  `longan.khcb@`, addresses in Tây Ninh or Gia Lai) could be drawn: V4-104, V4-142
  and V4-200. They are kept (AUTHORING_LOG.md). The draw read the extraction files; the
  system's runtime directories already leave both branches out.
- **Free tickets:** out-of-domain and not-in-handbook tickets (F) have no source;
  the author invents them.

## Workflow and status

| Step | Who | Status |
|---|---|---|
| Draw tickets and batches | `scripts/draw_v4_tickets.py` | done (246 tickets, 13 batches) |
| Pilot 1 (15 tickets) | Gemini 3.8 Flash | done, questions discarded (below) |
| Batch 00 (pilot 2, 15 tickets) | Gemini 3.8 Flash | done: 15 of 15 written, all facts found in their excerpts, 1 reclassified (AUTHORING_LOG.md) |
| Check each batch | `scripts/check_v4_authored.py N` | done for 00–12 |
| Batch 01 (30 tickets) | Gemini 3.8 Flash | done: 30 of 30 written, all facts found in their excerpts; 3 consequence tickets asked another kind, as allowed |
| Batch 02 (25 tickets) | Gemini 3.8 Flash | done: 25 of 25 written, all facts found in their excerpts; 5 of 10 procedure tickets asked another kind |
| Batch 03 (28 tickets) | Gemini 3.8 Flash | done: 28 of 28 written; facts in their excerpts, and the three computed scholarship scores recomputed correct |
| Batch 04 (8 tickets) | Gemini 3.8 Flash | done: 8 of 8 written; the computed scores (3,40, 3,60) recomputed correct; the 6- and 8-year maximum durations are the K51 and K50 handbooks' own values |
| Batch 05 (14 tickets) | Gemini 3.8 Flash | done: 14 of 14 written; all facts in their excerpts |
| Batch 06 (14 tickets) | Gemini 3.8 Flash | done: 14 of 14 written; facts in their excerpts, the computed score (3,40) recomputed correct |
| Batch 07 (22 tickets) | Gemini 3.8 Flash | done: 22 of 22 written; facts in their excerpts, the computed scores (3,56, 3,70, 3,52) recomputed correct |
| Batch 08 (11 tickets) | Gemini 3.8 Flash | done: 11 of 11 written; facts in their excerpts, the computed average (3,50) recomputed correct |
| Batch 09 (16 tickets) | Gemini 3.8 Flash | done: 16 of 16 written; facts in their excerpts, including the cohort differences (7,5 and 9 years; 6 and 8 years) |
| Batch 10 (27 tickets) | Gemini 3.8 Flash | done: 27 of 27 written; facts in their excerpts; V4-175 follows the amended K51 table (D+ fails in the remaining courses) |
| Batch 11 (14 tickets) | Gemini 3.8 Flash | done: 14 of 14 written; facts in their excerpts, including the assistant turns of the conversations |
| Batch 12 (22 tickets) | Gemini 3.8 Flash | done: 22 of 22 written; facts in their excerpts (the JLPT levels N4 and N3 checked by hand) |
| All batches | | done: 246 of 246 tickets written, none refused; 36 asked another question kind, as allowed |
| Fact check against the data; overlap check with v1–v3; clusters | scripts | done: every number and worded fact in its excerpts (computed values rechecked by hand); no question reaches 0.5 word-3-gram overlap with the 725 questions of v1–v3; 229 clusters, 11 of them with more than one case |
| Gold review of all 246 cases against their excerpts and the handbook | system author with Claude (an AI assistant), at the owner's request instead of the 30-case owner sample | done 2026-09-30: 5 cases' gold adjusted and one scoring rule added for the 8 refusal cases (`gold_adjustments.yaml`, AUTHORING_LOG.md); not an independent human review |
| Convert and freeze | `scripts/build_v4_cases.py` | done 2026-09-30: `generated_answer_cases.json` (246 cases, 229 clusters) applies `gold_adjustments.yaml`; frozen at the commit that adds it, and each run snapshot records the file's `dataset_sha256`. `tests/test_official_v4.py` fails if the file drifts from its sources |
| Run once, end to end | `scripts/run_official_answers.py --suite answers --bundle official_v4` | pending owner approval (paid) |

## Metrics (decided 2026-09-30, before the run)

- **Headline:** mean `answer_correctness` over the 246 cases, with a 95% interval
  from a bootstrap over the 229 clusters.
- **Secondary:** mean `answer_correctness` per family with 24 or more cases
  (A, B, C, E, F); the hallucination rate (`unsupported_claim`); the count of
  critical false passes.
- **Descriptive only:** results per cell (6 cases) and per writing style, and
  D (12 cases). The 14 refusal cases give a refusal figure too small for a
  strong claim.
- The overall mean is over the designed mix (multi-request and boundary
  questions are over-weighted on purpose), not an estimate of accuracy on real
  traffic; results are reported per family as well.
- **Reranker timeouts** (added 2026-09-30 during the run, before any score was
  read): cases whose answer records a reranker fallback for a timeout or
  request error are rerun whole (generation and judge). The list comes from
  telemetry only, before the judge output is opened. The rerun result is kept
  whether better or worse; a case that times out again is retried up to three
  times, then kept as its last attempt and counted as "reranker unavailable".
  The headline uses the rerun results (the system as designed); the first-run
  figure and the timeout rate are reported too.
- **4B reranker ablation** (added 2026-09-30, before any score was read):
  DeepInfra's Qwen3-Reranker-8B endpoint was overloaded during the first run
  (27-46 s per tiny call against 1.4 s for the 4B model), and the first run was
  paused at 75 cases. v4 is also run in full with Qwen3-Reranker-4B
  (`configs/retrieval_reranker_4b.yaml`, otherwise identical). The headline
  stays the 8B run, the deployed configuration, resumed when the endpoint
  recovers; the 4B run is reported as an ablation whatever its result. The
  reranker-timeout rule applies to both runs. A later switch of the deployed
  reranker to 4B would be a choice made on this test set, and its v4 figure
  would be reported as such.
- **Reranker choice by non-inferiority** (owner, 2026-09-30; SUPERSEDED the same
  day by the Voyage decision below, before any v4 score was read; replaced "the headline stays the 8B run" above): compare
  the 4B and 8B runs case by case over the 246 cases, both after their
  timeout reruns. Deploy 4B, and make its run the headline, if all three hold:
  mean `answer_correctness` of 4B is no more than 0.02 below 8B; 4B has no
  more critical false passes than 8B; the 4B hallucination rate is no more
  than 0.02 above 8B. Otherwise keep 8B as the headline and 4B stays an
  ablation. The reason is availability (the 8B endpoint stalled for over an
  hour; 4B answered in 1.4 s), not a higher score; the paper states the rule
  and reports both runs. The 0.02 margin is about the run-to-run spread seen
  on official_v1 (0.970 against 0.990). A retrieval-only comparison on
  official_v1 (`--suite retrieval --scope pure`, both rerankers) is reported
  as supporting evidence and is not part of the rule.
- **Deployed reranker: Voyage rerank-3** (owner, 2026-09-30, before any v4 score
  was read; supersedes the 4B/8B non-inferiority rule above). Measured on the
  155 `official_v1` retrieval questions with one shared set of 24 RRF
  candidates built by the frozen code, one call per question
  (`scripts/compare_rerankers.py`, `data/eval/reports/reranker_compare_v1/`):

  | Reranker | gold parent in top 5 | gold parent first | p50 | p90 | max |
  |---|---|---|---|---|---|
  | none (RRF order) | 148/155 | 0.826 | - | - | - |
  | Qwen3-Reranker-4B (DeepInfra) | 153/155 | 0.903 | 1.40 s | 1.76 s | 9.16 s |
  | Qwen3-Reranker-8B (DeepInfra, 2026-09-29) | 155/155 | 0.923 | 1.6 s | 4.7 s | 9.3 s |
  | **Voyage rerank-3 (MongoDB)** | **155/155** | **0.942** | **0.76 s** | **0.85 s** | **1.35 s** |
  | Voyage rerank-3-lite | 154/155 | 0.929 | 0.75 s | 0.84 s | 1.66 s |

  The choice rests on availability and latency with ranking quality at least
  equal to 8B: the DeepInfra 8B endpoint stalled for over four hours on
  2026-09-30 (30-60 s per call), which cost 105 of 246 cases their reranker in
  the 8B run. rerank-3 against 8B is 0.942 against 0.923, about three
  questions, which this set cannot separate. Measured once per reranker, on a
  development set, at one point in time; the 8B row is the 2026-09-29
  measurement because its endpoint was unusable.

- **Two runs are reported.** Run A (headline, hold-out) is the frozen system
  with Voyage rerank-3 and no other change. Run B (not a hold-out) adds the
  five general fixes written after run 4B's failures were read
  (`docs/DESIGN_DECISIONS.md`); its figure is reported as "after fixes" and
  never as the hold-out result, because the fixes were chosen with knowledge of
  v4. The 4B and 8B runs become ablations.
- The timeout list is read from the run log (the reranker warning is printed
  while its case is running): the answer records do not keep the reranker
  telemetry.
- **Dense-retrieval timeouts** (added 2026-09-30, AFTER run A's scores were
  read): run A's log shows 108 of 246 cases with at least one search that fell
  back to BM25 only, because the embedding call exceeded its 5 s limit on a
  slow network. The reranker-timeout rule is extended to them unchanged: the
  list comes from the log alone, each case is rerun whole, the rerun result is
  kept whether better or worse. Reruns, and run B, use
  `configs/retrieval_eval_patient.yaml` (30 s waits for the embedding and the
  reranker, otherwise identical), which changes how long a call may take and
  not what it returns. Because the rule was extended after scores were seen,
  the first-run figure (0.927, n = 245) is reported beside the rerun figure.
- A run that fails part-way is completed by rerunning only the failed cases.
  Gold found wrong after the run is not edited; it is reported with both
  figures.

## Pilot 1 (2026-09-30)

The first draw was tried on 15 tickets. The output is kept in
`pilot/batch_00_gemini_flash.yaml`; its questions are not part of v4, and the
tickets were redrawn with the same seed after the fixes below. No system was run.

- 10 of 15 tickets were written; the author marked 5 as not writable, each with
  a correct reason. 4 asked for a question kind the drawn article could not
  carry (a procedure from an article on using conduct results, a consequence
  from an article on advisers' rights); 1 drew a programme whose record has no
  faculty. Fixes: procedure and consequence tickets draw from matching
  articles, the author may change the question kind and record it, and
  programmes without a faculty are left out.
- The author invented nothing: missing content was reported, not filled in.
- The informal style was followed in 4 of 4 tickets. One table question copied
  the row's whole range ("từ 5,5 đến 6,2"); table tickets now ask for one value
  inside a range.

## Limitations to report

- Scope: the system is not deployed yet, so the questions are synthetic, written
  by an independent language model (with no knowledge of the system) from
  randomly drawn tickets in several writing styles. Evaluating on real student
  questions is the next step after the deploy.
- The ticket draw is made by the system's maintainer, at random with a fixed
  seed.
- v4 measures the final answer, not the planner on its own: planner labels
  were dropped to keep the set small (2026-09-30). Failed cases are traced to
  the planner, retrieval or the composer after the run. The planner's own
  hold-out figure remains v3's 87.1% before the fix.
- Robustness to rewording is seen only through the mix of writing styles; the
  36 paired variants in the first design were dropped with the planner labels.
  The `variant_style` field in `tickets.json` is left from the draw and unused.
- Some drawn articles give questions few students would ask (staff conduct, a
  unit's internal duties, the legal basis of a notice); they stay in the set,
  and the gold review did not remove them.
- Procedure and consequence tickets often fell back to another question kind
  when the article had none; results are reported by the kind actually asked.
- The judge (`openai/gpt-oss-120b`) has not been compared with a human rater.
- The gold was checked by the system's author with an AI assistant, not by an
  independent human rater. The paper says "checked by the system author with
  AI support".
