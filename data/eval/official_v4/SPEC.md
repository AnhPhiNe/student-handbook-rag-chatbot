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
- **Table-search choice by non-inferiority** (owner, 2026-10-04, before any
  run B score was read): run B repeats the v61 run
  (`official_v4_answers_20261004T104406Z`) with one change, the reviewed
  table-search collections (`configs/retrieval_eval_patient_table_search.yaml`,
  Qdrant `student_handbook_table_search_f3c77e0908bc`, Mongo
  `parent_docs_table_search_f3c77e0908bc`). The v61 QueryPlans are replayed
  from a shared plan cache, so the planner is not a second source of change;
  cases whose v61 plan was a planner fallback are planned again and listed.
  The composer is DeepInfra DeepSeek-V4.1-Flash low in both runs. Compare the
  two runs case by case over the 246 cases, both after their timeout reruns,
  with the same judge and packet. Deploy table search if both hold: the lower
  bound of the 95% cluster interval of the paired `answer_correctness`
  difference (B minus v61) is at least -0.03; and every case scored 0 in B
  but not in v61 is shown, on review against its sources, to be a judge error.
  Otherwise production keeps v35. Table search only has to be no worse: its
  purpose is to find a table when the planner does not call a tool, which v4
  rarely tests. Cases whose reranker was skipped (429 or timeout, read from
  the run log) are rerun before scoring.
- **Clause chunks, corpus scope and composer v3.35** (owner, 2026-10-05, before
  any score of this run was read): run C2 repeats table-search run B
  (`official_v4_answers_20261004T124930Z`) on the published clause-chunk candidate
  (Qdrant `student_handbook_table_search_79c456af1075`, Mongo
  `parent_docs_table_search_79c456af1075`, build `build-99d162d545cd26cae458`)
  with composer v3.35; the v61 QueryPlans are replayed from the shared cache,
  the composer is DeepInfra DeepSeek-V4.1-Flash low in both runs, and the judge
  and packet are unchanged. Composer timeouts and reranker skips are rerun before
  scoring. The owner removed vừa làm vừa học, cao đẳng and staff-only content
  from the assistant's scope, so cases are split before scoring:
  - out of scope (10: V4-014, 015, 017, 081, 157, 177, 179, 197, 198, 211): each
    answer must say the question is outside what the assistant serves and must
    not answer with the chính quy or student rule; read one by one;
  - partly out of scope (8: V4-095, 098, 110, 125, 146, 150, 153, 180): read one
    by one; the in-scope parts must be answered from their sources and the
    out-of-scope parts declined; judge scores are reported, not used, because
    the gold expects the out-of-scope rules;
  - in scope (the other 228): deploy if the lower bound of the 95% cluster
    interval of the paired `answer_correctness` difference (C2 minus B) is at
    least -0.03 and every case scored 0 in C2 but not in B is shown, on review
    against its sources, to be a judge error.
  Any out-of-scope or partly out-of-scope answer that applies the wrong rule
  blocks the deploy until fixed. Clause chunks and the composer change are
  measured together; their retrieval effect alone is the offline comparison in
  `docs/DESIGN_DECISIONS.md`. A first start on build `build-e4a43631790e8977946d`
  was stopped at a quarter of the answers, before any score was read, when 20
  articles were found whose list had been split from its lead-in; its directory
  is marked `_ABORTED_before_scoring` and is not used.
  Outcome (2026-10-05): C2 (`official_v4_answers_20261004T181608Z`) passed the
  in-scope rule (paired difference −0.004, interval [−0.022, +0.014], no new
  zero) but not the out-of-scope one: V4-157, 197 and part of 146 answered the
  vừa làm vừa học rule from the kept articles, and staff-only questions were
  called "not found". Chunking review then found six chunks cut mid-word and 54
  heading-only chunks; C2's build is not deployed.
- **Run C3: one chunk per khoản, composer v3.36** (owner, 2026-10-05, AFTER C2's
  scores were read, so its out-of-scope criterion is a changed criterion, not
  the one C2 was held to): C3 repeats run B on build
  `build-7754cc9c07ae9951cfa5` (Qdrant `student_handbook_table_search_e55308ddae85`,
  Mongo `parent_docs_table_search_e55308ddae85`; one chunk per khoản, never split;
  24 reviewed layout fixes; the same corpus scope, which an offline measurement
  kept: without it 46 of 256 regular-student questions had a vừa làm vừa học or
  staff-only article in the top five, with it none). The composer is v3.36: a
  question that names no group is answered for regular university students, and
  where the sources hold separate rules for forms or levels of study the answer
  says whom a rule covers and never presents one group's rule as another's; it
  does not decline. Everything else is as in C2 (v61 plans replayed, DeepInfra
  DeepSeek-V4.1-Flash low, same judge and packet; composer timeouts, reranker
  skips and judge connection errors rerun before scoring).
  - in scope (the 228 of C2): deploy if the lower bound of the 95% cluster
    interval of the paired `answer_correctness` difference (C3 minus B) is at
    least −0.03 and every case scored 0 in C3 but not in B is shown, on review
    against its sources, to be a judge error;
  - the 18 out-of-scope and partly out-of-scope cases of C2: read one by one; an
    answer passes if it answers from a rule for the group asked about, or gives
    another group's rule while saying whom that rule covers, or says the sources
    hold no rule for that group; it fails if it presents another group's rule as
    applying to the asker, and any such answer blocks the deploy. Judge scores
    are reported, not used.
  Outcome (2026-10-05, `official_v4_answers_20261005T052049Z`, no API error,
  judge failure or reranker skip): in scope C3 0.970 against B 0.965, paired
  difference +0.005, 95% cluster interval [−0.008, +0.018], no new zero; all 18
  out-of-scope cases pass (vừa làm vừa học durations answered from Điều 3 and
  labelled; V4-110 says Điều 12 is for chính quy and no vừa làm vừa học rule was
  found; staff-only questions not found). C3 passes and is the build to deploy.
- **Run N: composer reasoning none** (owner, 2026-10-11, before the run; written in
  the session notes and copied here before the next run): N repeats C3 at commit
  `cda3915b` with the composer's `reasoning_effort` set to none instead of low,
  everything else as in C3 (v61 plans replayed, DeepInfra DeepSeek-V4.1-Flash,
  same judge and packet). Keep none if, in scope, the lower bound of the 95%
  cluster interval of the paired `answer_correctness` difference (N minus C3) is
  at least −0.03, every case scored 0 in N but not in C3 is shown not to be a
  serious false statement, and every answer in N that computes a value is checked
  by hand, a wrong result failing the rule.
  Outcome (2026-10-11, `official_v4_answers_20261011T094233Z`, no API error or
  judge failure): in scope N 0.972 against C3 0.970, paired +0.003, 95% cluster
  interval [−0.008, +0.012], no zero in either run; 8 answers compute a value
  (scholarship score, term average) and all 8 are right. None is kept.
- **Run R: composer v3.37, grounded referrals** (owner, 2026-10-11, before the
  run): R repeats N on the current main plus prompt v3.37, which allows a unit
  to be named as the place to ask only when its evidence says the unit handles
  that matter, keeps a procedure's own mailbox for that procedure, and says so
  when a person's contact is asked for and absent. The normalizer is
  `v34-ask-for-what-is-missing` (N ran v32); the 655 saved plans re-normalized
  offline differ only on the misspelt-name cases those fixes target. Keep v3.37
  if, in scope, the lower bound of the 95% cluster interval of the paired
  `answer_correctness` difference (R minus N) is at least −0.03, every case
  scored 0 in R but not in N is shown not to be a serious false statement, and
  no answer in R gives a contact detail that is not in its unit's evidence or a
  procedure mailbox for another matter.
  Outcome (2026-10-11, `official_v4_answers_20261011T104311Z`, commit `4c5faf97`;
  V4-111 judge timed out three times and is left out): in scope R 0.975 against N
  0.974, paired +0.000, 95% cluster interval [−0.013, +0.014], no zero; every
  email is a directory email except `nghidinh116@`, used only in V4-124 and
  V4-167, which ask about that procedure. The rule is met, but reading the
  answers showed v3.37 too cautious: V4-229 sent a scholarship-list question to
  the adviser although Điều 28 says Phòng CTCT&HSSV runs the award, and V4-142
  dropped the email and phone of the institute it named. v3.37 is not shipped.
- **Run R2: composer v3.38** (owner, 2026-10-11, after R was read): v3.38 names
  the unit the evidence says carries out, receives or handles the matter, falls
  back to the adviser, faculty office or Phòng CTCT&HSSV only when the evidence
  names none, limits the personal-contact rule to individuals, and says these
  rules never remove a grounded unit's contact fields. Same rule as R, against
  N, plus: V4-229 names Phòng CTCT&HSSV, and no answer that gives a unit from a
  directory lookup drops a contact field the question asks for.
  Outcome (2026-10-11, `official_v4_answers_20261011T105647Z`, commit `b56b5620`):
  in scope R2 0.982 against N 0.972, paired +0.010, 95% cluster interval
  [−0.001, +0.022], no zero, no stray email, V4-229 names Phòng CTCT&HSSV; the
  19 answers that compute a value were not re-checked here. The added criterion
  fails: V4-142 and V4-144 ask "liên hệ đơn vị nào và ở đâu" and give the address
  without the email and phone.
- **Run R3: composer v3.39** (owner, 2026-10-11, after R2 was read; the last
  iteration on v4 for this change, whatever its result): the contact rule says a
  question asking which unit to contact or where to contact it needs every
  contact field. Same rule as R2 against N. Its result is reported as it comes.
  R3 was stopped part-way (166 of 246 answers, none judged) at the owner's
  request: v3.37–v3.39 each added a line for cases read on v4, which tunes the
  prompt to this set. Its partial output is not reported.
- **Run F: composer v3.40, contact principles** (owner, 2026-10-11, before the
  run; the final run for this change). The case-specific lines of v3.37–v3.39
  are removed. v3.40 differs from v3.36 by two general rules: when pointing to
  where to ask about a part without evidence, name only a unit the evidence says
  does that work, else the adviser or faculty office (study matters) or Phòng
  CTCT&HSSV (other student matters); and contact details are given only when
  the evidence ties them to that unit and that matter, with every contact field
  the evidence has for a unit named as the place to contact. **v4 is not a
  hold-out for this change**: R and R2 were read before v3.40 was written.
  Keep v3.40 if, in scope, the lower bound of the 95% cluster interval of the
  paired `answer_correctness` difference (F minus N) is at least −0.03, every
  case scored 0 in F but not in N is shown not to be a serious false statement,
  and no answer gives an email outside the directories except a procedure
  mailbox on its own procedure. Because v4 informed the change, the main check
  is 12 contact and referral questions written for it and not drawn from v4
  (`ask_fresh.json` in the session notes), each read against the two rules.
  Whatever the outcome, the prompt is not tuned further on these cases.
  Run F was superseded before it ran (the owner chose a simpler rule, below).
- **Run A: composer v3.42, no referral without evidence** (owner, 2026-10-11,
  before the run; the final run for this change). v3.42 is v3.36 plus one rule,
  in the owner's words: "Khi chưa tìm thấy căn cứ cho một ý, nói rõ điều đó và
  không gợi ý đơn vị hay thông tin liên hệ nào cho ý đó." Composer reasoning
  none, served first by the DeepSeek API (run N used DeepInfra; same weights);
  judge gpt-oss-120b on DeepInfra as in N; normalizer v34 (N ran v32), so the
  paired difference also carries the normalizer change. v4 is not a hold-out
  for referral behaviour (R and R2 were read). Keep v3.42 if, in scope, the
  lower bound of the 95% cluster interval of the paired `answer_correctness`
  difference (A minus N) is at least −0.03, every case scored 0 in A but not in
  N is shown not to be a serious false statement, and no answer gives an email
  outside the directories except a procedure mailbox on its own procedure.
  Before the run, 21 targeted replays (12 new contact questions, the owner's
  live case, 8 v4 cases) gave: personal contacts declined without a referral;
  grounded units with full contacts; one leak (the rector's phone answered with
  Phòng CTCT&HSSV's mailboxes, `nghidinh116@` among them); two over-cautious
  answers. The leak is recorded as a known limit, not tuned.
  Outcome (2026-10-11, `official_v4_answers_20261011T120228Z`, commit `072e4152`,
  no provider error): in scope A 0.968 against N 0.972, paired −0.004, 95%
  cluster interval [−0.019, +0.011], no zero. The email criterion fails: V4-232
  (a department head's phone) gives Phòng CTCT&HSSV with `nghidinh116@`, while N
  had no such leak on v4. The rule did not show a measurable effect on the leak
  it targets, and it removed a grounded referral (V4-229). v3.42 is not kept;
  the composer stays v3.36 with reasoning none.
- **Run K49: the K49 handbook replaces K48-K49** (owner, 2026-10-13; written
  2026-10-18, before the run). Only data change: build
  `build-973ef632fcbca126b306` (cohorts K49, K50, K51), collections
  `student_handbook_table_search_3bbd93e9f05a` / `parent_docs_table_search_3bbd93e9f05a`
  through `configs/retrieval_eval_patient_k49.yaml`; composer v3.36 with
  reasoning none, served first by the DeepSeek API; judge gpt-oss-120b on
  DeepInfra; normalizer v34; 16 answer workers. The 89 cases drawn for
  K48-K49 now target K49 (`gold_adjustments.yaml`, `cohort_migration`); every
  gold was re-checked against the K49 PDF before the run, and 11 entries record
  why a case changed: 8 change required facts (V4-095, 096, 111, 118, 121, 128,
  145, 182), 2 change a school year or an earlier assistant turn (V4-088, 216)
  and 1 keeps a reviewed directory value (V4-144).
  Plans are not replayed: the scoring tool's text now names the courses graded
  pass/fail (Quy chế đào tạo Điều 2: thể chất, quốc phòng – an ninh, tin học cơ
  bản, ngoại ngữ không chuyên; owner, 2026-10-18), and the tool text is part of the
  plan cache key, so all 246 cases are planned live, once, into a new cache file
  that is kept with the run.
  Reported, with no deploy decision attached (the owner decides after review):
  - **K49 (84 cases with K49 as the UI cohort, plus 5 comparisons): a new
    baseline**, with its 95% cluster interval. It is not compared with any
    K48-K49 figure: the handbook, the golds and the plans changed.
  - **K50 and K51 (the cases that name neither K48-K49 nor K49), regression
    check**, paired case by case against run A
    (`official_v4_answers_20261011T120228Z`; its composer prompt is v3.42,
    v3.36 plus one referral sentence, otherwise the same configuration), with
    run C3 (`official_v4_answers_20261005T052049Z`, v3.36, composer low on
    DeepInfra) as a second reference, and run N's 0.972 (in scope; its per-case
    records are lost) cited as context only. Their data changed in two places,
    both decided by the owner before the run: Phòng HTQT's misprinted phone is
    corrected to (028) 38391080 (as in K49), and a QR pointer wrapped over two
    PDF lines no longer cuts the adviser rules' Điều 4 and 7 and Nghị định 116
    Điều 7 and 13; otherwise only the cohort label K49 in shared records. The
    paired difference also carries the new plans and the scoring tool text. The
    check passes if, in scope, the lower
    bound of the 95% cluster interval of the paired `answer_correctness`
    difference (K49 run minus A) is at least −0.03 and every case scored 0 here
    but not in A is shown not to come from the data change.
  - The cases out of scope or partly out of scope keep the C2 lists.
  - Provider errors are rerun whole under the existing rules; gold found wrong
    after the run is not edited and is reported with both figures.
  Outcome (2026-10-18, `official_v4_answers_20261018T073835Z`, commit `ea4fc1bd`,
  no provider error): K49 in scope 0.960 [0.918, 0.992], zeros V4-070 (gold
  narrower than the K49 dormitory procedure) and V4-209 (planner asked instead of
  reading the history); K50 and K51 0.975 against A 0.964, paired +0.011
  [−0.011, +0.033], no new zero: the regression check passes.
- **Run P: composer prompt v3.41 on DeepSeek-V4.1-Flash, DeepInfra only**
  (owner, 2026-10-19). First registered the same day (commit `d4ab548a`) as
  v3.41 together with `deepseek-ai/DeepSeek-V4.1-Flash-1017`; its gates stopped
  that configuration before any v4 answer was produced (outcomes below), and the
  owner then chose V4.1-Flash. This amendment is written after those gate
  results and before run P starts.
  - The change measured is the prompt, v3.36 → v3.41 (commit `35469798`): the
    v3.36 rules stated once each under five principles, and one rule changed by
    the owner's choice: a part without evidence gets "Khi chưa tìm thấy căn cứ
    cho một ý, nói rõ điều đó và không gợi ý đơn vị hay thông tin liên hệ nào
    cho ý đó" (v3.42 added the same sentence to v3.36 and failed run A's email
    criterion; v3.41 is measured on its own terms). v3.41 was drafted on
    official_v1 and development questions; it keeps rules that came from
    earlier v4 cases.
  - Composer: `deepseek-ai/DeepSeek-V4.1-Flash` on DeepInfra only, reasoning
    none, no fallback (the DeepSeek API path is dropped by the owner's choice).
  - **Baseline: run K49** (`official_v4_answers_20261018T073835Z`, commit
    `ea4fc1bd`), not rerun: prompt v3.36, reasoning none, configured DeepSeek
    API first with DeepInfra fallback; its records show 232 of 246 answers
    from `deepseek-ai/DeepSeek-V4.1-Flash` on DeepInfra and 14 from
    `deepseek-flash` on the DeepSeek API (same weights). Run N is not usable:
    its per-case records are lost and its data and golds predate K49.
  - **Same plans as K49**: `data/eval/reports/official_v4_k49_plans.json`,
    sha256 `d6a0731b6dc535867ef053b96ec3d5a78b537e13ccb9bd47a257d7d028a2f7f2`
    (planner v61, normalizer v34). Everything else as in K49: dataset sha256
    `541d78d5…29ed5`, `configs/retrieval_eval_patient_k49.yaml`, collections
    `student_handbook_table_search_3bbd93e9f05a` /
    `parent_docs_table_search_3bbd93e9f05a`, Voyage rerank-3,
    `configs/answer_generation_eval_patient.yaml`, 16 answer workers, judge
    gpt-oss-120b on DeepInfra with packet `judge-packet-v3-source-clauses`
    (judge workers are not fixed). With the plans fixed, P differs from K49
    in retrieval execution, the composer prompt, and for 14 cases the provider
    serving the same weights.
  - **Gate outcomes for the 1017 configuration** (2026-10-19): (1) 20 targeted
    replies (12 ask_fresh questions through the pipeline, V4-229, 142, 144,
    231, 236, 081, 031, 035 from K49's packets): none disables thinking on 1017
    (0 reasoning tokens); the owner's sentence removed ungrounded referrals in
    6 replies; V4-142 gave the institute's address without phone, email and
    website (3 draws per arm: full fields 3/3 with V4.1-Flash under either
    prompt, 1/3 and 2/3 with 1017); the rector's-phone question leaked
    `nghidinh116@` under both prompts (known limit). (2) Development
    required-facts check, 100 questions with identical packets, 106 facts:
    v3.36 + V4.1-Flash 95 (median 704 characters), v3.41 + 1017 93 (538):
    sup_05 stated 2 points for a first exam warning instead of 3 (an adjacent
    row; 1 of 5 redraws with 1017 under v3.36, 0 of 10 with V4.1-Flash), and
    sup_20 says "lâm thời" where the counter looks for "tạm thời". The gate
    failed and the 1017 configuration was not run.
  - **Gates for this configuration**: the same development check gave
    v3.41 + V4.1-Flash 94 of 106 by count (median 573 characters, 19% shorter
    than v3.36); its one difference from v3.36 is the same sup_20 wording
    ("lâm thời"), read and found not to be a missing fact. Recorded as passed
    on that reading. The 20 targeted replies are repeated with V4.1-Flash before
    P and read the same way; a clear error stops there.
  - **Validity**, checked in the run log before any score is read: no 402 or
    authentication error, no dense retrieval falling back to BM25 only, no
    reranker skip. Affected cases are rerun whole before scoring; if that is
    not possible the run is reported incomplete and not scored.
  - **Keep P if all hold**, in scope (the 228 cases; the C2 lists of 10 out of
    scope and 8 partly out of scope): the lower bound of the 95% cluster
    interval of the paired `answer_correctness` difference (P minus K49) is at
    least −0.03; no case scored 0 in P is above 0 in K49 (a new zero fails the
    rule; its review is shown but does not excuse it); and no answer gives an
    email outside the directories, except a procedure mailbox on its own
    procedure. The 18 out-of-scope and partly out-of-scope cases are read one
    by one as in C3; one that presents another group's rule as the asker's
    fails and blocks the deploy. If all hold, the owner has decided to deploy
    v3.41 with this composer.
  - **v4 is not a hold-out for this change**: runs R, R2 and A were read
    before the owner's referral sentence was chosen. Whatever the outcome, the
    prompt is not tuned on v4 after P. The deploy is separate from the planner
    v62 / normalizer v35 work.
  Outcome (2026-10-19, `official_v4_answers_20261018T175106Z`, commit
  `216bbea0`, all 246 composed by V4.1-Flash on DeepInfra; the log shows no
  402, authentication error, BM25-only search or reranker skip): in scope P
  0.960 against K49 0.969, paired −0.009, 95% cluster interval [−0.017,
  −0.003]; no email outside the directories except `nghidinh116@` on its own
  procedure (V4-124, V4-167); the 18 out-of-scope cases pass reading. **One new
  zero, V4-195** (K49 0.2): both runs give the same wrong answer to the
  follow-up "Còn khóa K51 thì sao ạ?" (the liên thông durations, 2 and 4 years,
  instead of chính quy 4 and 6). By the rule a new zero fails P, so v3.41 is
  not kept and not deployed.
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
