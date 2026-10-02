# Design decisions and the measurements behind them

The measured component choices and later candidate changes are recorded below.
Not every later change has a full end-to-end comparison; candidate-only checks
are labelled explicitly. This document collects the comparisons: what was
compared, on which data, what the numbers were, and why the choice was made.
The dated logs of each experiment are in [archive/](archive/README.md); the raw
reports are listed at the end.

## How to read the numbers

- **Almost every number is a development measurement.** `official_v1` (135
  deterministic, 155 retrieval and 150 answer cases) was used to tune prompts
  and pick models, so its scores are optimistic. `official_v2` is spent in the
  same way. The 21 questions in `data/eval/development/supplementary_questions.yaml`
  are development questions for the new v35 content.
- **Historical hold-outs.** `official_v3` retains its first planner result of
  2026-09-27, but was used after that run and is now spent. `official_v4` run A
  is the historical end-to-end hold-out; B/C are post-fix measurements. No new
  hold-out or production result is claimed for subsequent offline hardening.
- **Noise.** On the 135-case deterministic suite, a small prompt change flips
  2–3 borderline cases either way, so a difference of 3 or fewer cases is
  treated as a tie. Paired comparisons use McNemar's test on the cases where
  the two arms disagree.
- **Answer quality** comes from an LLM judge (`openai/gpt-oss-120b`) whose
  agreement with a human rater has not been measured.

## Summary

| Component | Chosen | Alternatives measured | Deciding evidence |
|---|---|---|---|
| Planner | OpenAI `gpt-6-luna`, reasoning medium, strict schema; candidate prompt v57 | Qwen3.8 on Groq, Cohere Command A+, DeepSeek flash (none, low, medium) | Latest recorded full v1 belongs to v56: 133/135, p95 7.68 s (2026-10-01). It is not a full v57 measurement; see the 2026-10-02 candidate section |
| Composer | DeepSeek flash, thinking off; candidate prompt v3.34 | Gemini 3.1 Flash-Lite; DeepSeek thinking low | Originally chosen for equivalent quality without Gemini's failed calls; v4 Run C measures v3.33, not the later candidate or a new isolated model comparison |
| Directory selection | Exact name, otherwise DeepSeek picks from the closed catalog; when it finds nothing, the same prompt again with thinking low | Fuzzy-score thresholds; looser prompt wording; thinking on every call | Development cases: 10 wrong units under thresholds, 0 with the selector. The second look: everyday wordings 42 → 47 of 47, 0 wrong, median 0.86 s against 1.5 s for thinking on every call |
| Embedding | `BAAI/bge-m3` over the DeepInfra API | Local `bge-m3`; Qwen3-Embedding-8B | API vectors identical to local; Qwen3-8B ties after reranking, with query p50 6.3 s against 1.3 s |
| Reranker | Voyage `rerank-3`, on all 24 fused children (2026-09-30) | Qwen3-Reranker-8B, 4B, 0.6B on DeepInfra; Cohere rerank-v4.0-fast; none | first 0.942 / top-5 155/155 at p90 0.85 s, against 8B 0.923 / 155 at p90 4.7 s, 4B 0.903 / 153, Cohere 0.897, none 0.832 / 148. Chosen for availability: the DeepInfra 8B endpoint stalled for over four hours on 2026-09-30 |
| Lexical search | BM25 fused with RRF (k = 60), scored by BM25 only | Dense only; BM25 with a title-match rule | RRF + rerank beats dense + rerank; the title rule cost hit@1 and 3× BM25 time |
| Candidate depth | 24 children for dense, BM25, fusion and rerank | 16, 40 | 24 holds the first gold child for 155/155 questions, 16 for 154/155 |
| Tables | Reviewed JSON for lookup; tables kept in full parents; candidate adds 35 source-reviewed search descriptions, not numeric rows | The composer reading tables from retrieved text | Range-reading failures justify deterministic fact locks. Search descriptions only locate the original table; candidate coverage and limits are recorded below |
| Planner input | The student's own words | 156 slang rules rewriting the question first | 133/135 without the rewrite against 132/135 with it; the 12 rewritten questions pass either way |
| Retrieval query | Slang rewritten to handbook wording | The student's own words | On 61 slang-reworded questions hit@5 61/61 with the rewrite against 58/61 without |

## Planner

The planner turns one message into typed tasks (structured lookup, RAG or
clarify). All runs below are the 135-case `official_v1` deterministic suite
unless stated.

| Date | Setup | Passed | Latency | Notes |
|---|---|---:|---|---|
| 2026-09-10 | Qwen3.8 low (Groq), prompt v41 | 123/135 | median 1.8 s | Baseline |
| 2026-09-10 | Qwen3.8 low, prompt v42 | 129/135 | | Control codes shown with their meaning; McNemar p = 0.07 against v41 |
| 2026-09-12 | Qwen3.8 low, prompt v43 | 129/135 | p95 5.8 s | Unused `CATALOG_HINT` line removed, identical to v42 case by case; baseline for the DeepSeek comparison |
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

**Planner input and keyword rules (2026-09-29).** The question used to reach
the planner after 156 slang rules rewrote it (63 of 681 `official_v1`/`v2`
questions changed), a remnant of the Qwen era. On `official_v1` deterministic
(v10 contract, Luna v53, same code otherwise) the planner scored 132/135 with
the rewrite and 133/135 without it; the 12 questions the rewrite changes pass
in both arms, and the 3 discordant cases (003, 113, 122) are ones it does not
touch, so they are run-to-run variance (McNemar p = 1.00). The planner now
reads the student's own words. Two keyword rules were removed the same day
because neither fired on the 706 `official_v1`, `official_v2` and development
questions: a second planner call when the task count differed from the
numbered requests ("thứ nhất", "thứ hai"; the count is still stated in the
prompt), and a list of 16 handbook phrases that overrode the planner's
out-of-domain decision.

**Failures that persist across models** (093/096: "ở phòng nào" read as the
office field instead of the unit; 033/122: one task or two) point to ambiguous
definitions rather than model quality; the answer still names the right unit.

### "Where do I go" questions: two catalog wordings tried, neither kept (2026-09-29)

`official_v2` (rerun on the current stack) showed two routing patterns. The
first was a rule question next to a lookup table sent to the table (case 059).
The second was "nộp ... ở đâu" sent to the handbook text instead of the service
catalog (041, 042, 096), which loses the office's contacts. Three development
sets were written and committed before any change and answered 3 times each:
`table_adjacent_questions.yaml` (26 rule questions, 14 service "where"
questions), `where_and_mixed_questions.yaml` (15 more service "where"
questions, 8 planner-only probes needing a table and a rule) and
`regulated_where_questions.yaml` (13 "where" questions whose office, approver
or deadline a regulation sets).

- **Rule questions next to a table: no change needed.** 78/78 went to the
  text, retrieved the gold parent and stated the facts; the 059 slip did not
  recur. Probes needing both a table and a rule included a RAG task 22/24.
- **"Where" questions.** The catalog descriptions of `student_service` and
  `office` say that procedures ("thủ tục") use RAG. Two rewordings were tried:

| Wording | Service "where" (29 questions × 3) | Regulated "where" (13 × 3) | Rule questions (26 × 3) | `official_v1` / `v2` |
|---|---|---|---|---|
| v53, kept: "thủ tục … dùng RAG" | 57/87 planned to the catalog; of the 14 first questions answered, 22/42 gave the contacts, the rest named the unit without them or, 4 times in 20, said nothing was found | 39/39 right office or person | 78/78 | 133/135, 143/154 |
| v54: asking where to do something uses the catalog, even for a procedure | 87/87 with contacts | `official_v2` 085 became a clarification (2 of 2) and 102 "nothing found" (1 of 2); both were answered from the regulation under v53 | 78/78 | 134/135, 144/154 (041, 042, 096 gained; 085, 102 lost) |
| v55: v54, except cases where a regulation sets the office, approver or deadline (e.g. complaints, exam absence, leave) use RAG | 53/77 (69%, 10 rate-limit fallbacks excluded) | 39/39 | 78/78 | stopped once v55 failed |

The rule was fixed before v55 ran. v55 would be kept only if service questions
reached at least 95%, regulated ones named no wrong office and did no worse
than v53, rule questions stayed at 78/78 and `official_v1`/`v2` did not drop,
and there would be no third attempt. v55 failed the service criterion: the
planner read "học vụ, công tác sinh viên" as covering certificate exemptions,
fee waivers and double-degree admission. So the registry is back at v53.

The boundary is hard to put into words. "Nộp … ở đâu" is a service question
when the catalog answers it, and a regulated case when a regulation names a
different office or a deadline. For example, a conduct-score complaint goes to
Phòng CTCT&HSSV within 7 days, while the catalog lists Phòng Thanh tra Đào
tạo for complaints. A description can push the planner to one side but does
not draw that line reliably.

Under v53 the failure is the safe one: no run named a wrong office; a service
question sometimes lacks the contacts or says nothing was found. Reading both
the catalog and the regulations for every "where" question would remove the
choice, at the cost of an extra retrieval and a composer rule for conflicting
sources. It has not been built.

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

Judged on the 150 `official_v1` answers of the same replay (judge
`openai/gpt-oss-120b` on Groq, both arms on the dataset version the recorded
run used):

| Prompt v3.30 | Thinking off | Thinking low |
|---|---:|---:|
| Answer correctness (95% CI) | 0.988 (0.971–0.999) | 0.991 (0.976–1.000) |
| Faithfulness | 0.989 | 0.980 |
| Citation correctness | 0.985 | 0.973 |
| Hallucination rate | 0.033 | 0.047 |
| Answers with an unsupported claim | 5 (4 only in this arm) | 7 (6 only in this arm), McNemar p = 0.75 |
| Correctness below 0.8 | 1 (006) | 0 |
| Critical false passes | 0 | 0 |

The one correctness gap, case 006, is a judge inconsistency: both arms name
the same office and duty in nearly the same words, and the judge scored them
0.4 and 1.0. Thinking off was kept: it is as accurate by the judge and by
every rule check, and about 3 s faster per answer (composer p50 1.4 s against
4.3 s). These answers come from evidence packets recorded on the v34 data
with Cohere reranking, so they compare the composer setting only. Earlier,
the judge gave thinking low (prompt v3.29, v34 data) 0.990 correctness
against 0.998 for thinking off (an earlier prompt, v33 data); that pair is
confounded and is superseded by the table above.

### Identifiers are checked against the evidence (2026-09-29)

An audit of 768 saved answers checked every identifier (email, phone,
link, document code, room number) and every number against the evidence
packet the composer saw. Of 200 identifiers, 1 was wrong
("khotienganh@hcmue.edu.vn" for "khoatienganh@hcmue.edu.vn"), with exactly
one near match in the evidence. Of 2,535 numbers, 43 were not found
verbatim and none was wrong: list numbering, clause numbers read from
numbered paragraphs, and rewrites such as "01 tuần" as "7 ngày". So the
answer now passes through a corrector for identifiers only: one missing
from the evidence is replaced by its unique near match (up to 2 edits for
emails and links, 1 for phones, codes and rooms; swapping two neighbouring
characters counts as one edit) and logged otherwise. The limits are not wider
because real identifiers sit close together: across the handbook data, 4 pairs
of document codes (such as 11/2020/NĐ-CP and 110/2020/NĐ-CP), 2 pairs of phone
numbers and 294 pairs of room numbers are one edit apart.
Numbers are left to the fact lock and the judge. In a streamed answer the text is
released only at whitespace (a run without whitespace is held up to twice the
256-character buffer), so an identifier is never split between two releases
and is corrected before the student sees it.

### Composer prompt history

| Version | Date | Change | Evidence |
|---|---|---|---|
| v3.23 | 2026-09-06 | Material exceptions in the evidence | Six-case smoke (Gemini): 5/6 main criteria met; the scholarship answer omitted the exclusion of bridging students ([archive](archive/COMPOSER_V323_RELEASE_SMOKE.md)) |
| v3.24 | 2026-09-06 | Table reading and cohort context grounded in the prompt | Not measured separately |
| v3.25 | 2026-09 | | Used for the Gemini/DeepSeek A/B above. A review of 146 real packets found every source marked `candidate`, so the rule "answer candidate-only units cautiously" applied to every answer and matched DeepSeek hedging before correct answers |
| v3.26 | 2026-09-27 | An input section defines the packet; `candidate` is the default and answers normally when it directly answers | From the v3.25 review |
| v3.27 | 2026-09-27 | Rules regrouped by task (scope, conclusions, missing evidence, tables, presentation) | 68 of 71 clauses verbatim; not measured on its own |
| v3.28 | 2026-09-27 | Student wording; the admission-year definition returns to scope matching | Replays on identical evidence: v3.27 added the admission year to 8 answers against 2; DeepSeek echoed input terms (cohort, evidence) in 2–6 answers per run; 17–29 answers opened with a bare "Có."/"Không." |
| v3.29 | 2026-09-28 | Yes/no conclusions stated as a full sentence, never a bare "Có." | A bare "Có." had affirmed the opposite of the answer (military leave and the study period) |
| v3.30 | 2026-09-28 | Table rows read as labelled lines; contacts copied verbatim; sources without an article named by document title; notices state their school year | The thinking comparison above; sup_05 fixed with thinking off |

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

### A second look with thinking when nothing is found (2026-09-29)

"tui cần in bảng điểm và làm thủ tục chuyển trường thì đến đâu" was answered
without Phòng Khảo thí và Đảm bảo chất lượng, whose K51 service is "Cấp các
loại giấy chứng nhận điểm cho sinh viên". The selector (thinking off) answered
"none" for "in bảng điểm". Until the same day the planner saw the question
after the slang table had rewritten it ("in bảng điểm" → "cấp bảng điểm"),
which hid the gap; removing that rewrite (*Planner input* under Planner)
exposed it. Adding a slang rule per wording is the patch this avoids, so three
general changes were measured instead.

The cases: a new set, `data/eval/development/service_everyday_cases.yaml`
(47 K51 cases: 20 everyday wordings of a listed service, 15 near another
unit's service, 12 needs no K51 service lists), written and committed
(`112089ba`) before any changed prompt ran, with the decision rule fixed in
its header; and the 189 existing development cases. Each arm ran once; the
cases whose outcome changed were then repeated (5 times for the two prompts,
3 for thinking).

| Arm | Existing (189) | New (47) | Wrong units | Service lookups via the LLM (101): median / p90 / max |
|---|---|---|---|---|
| Thinking off (before) | 187 | 42 | 0 | 0.78 / 1.0 / 2.5 s |
| Looser prompt wording, thinking off | 185 | 44 | 0 | not timed separately |
| Thinking low on every call | 188 | 45 (2 failed calls) | 0 | 1.5 / 5.6 / 12.4 s |
| **Thinking off, then thinking low only when it finds nothing** | **188** | **47** | **0** | **0.86 / 2.3 / 14.9 s** |

- **Looser wording** told the model that students say "in", "xin", "lấy" for
  "cấp" and to pick the service that meets the need. It found "in bảng điểm"
  and "nhận lại bài thi đã nộp để xem điểm", but lost "trang web của trường
  bị lỗi" (to none) and "xin tài liệu để làm khóa luận" (to a clarification),
  5 times out of 5 each. That is a trade, not a gain, so it was dropped.
- **Thinking on every call** found those needs without losing the other two,
  and the 12 absent needs still got no unit. It costs latency, and 3 of 102
  calls failed. Two used the whole 3,000-token output budget on thinking,
  which DeepSeek counts against `max_tokens`, and returned an empty answer.
  One reply began with the requested format, `{"type": "json_object"}`, before
  the answer. Thinking length for one prompt ranged from 128 to about 3,200
  tokens (1–13 s).
- **Chosen: the second look.** The fast call runs first; only when it answers
  "none" is the same prompt asked with thinking low. A found record never waits
  for thinking, and the fast call has chosen no wrong unit on these cases, so
  nothing it finds changes. Only "none" answers pay a second call: 25 of 101
  lookups here, 20 of them needs chosen to be absent, so fewer in real
  questions. It also fixed the one faculty miss (fac_18). Settings: output
  budget 4,096 tokens, timeout 30 s. The reply parser takes the first JSON
  object that carries a decision. A failed second look keeps the "none" and is
  logged as `directory_selector_thinking_failed`. The prompt text is unchanged
  (v2).

Limits: single runs, and thinking replies vary between runs (in a probe,
"đăng ký chương trình trao đổi sinh viên với trường nước ngoài" was matched 2
times of 3 and answered none once), so 47/47 is not a stable figure. The 47
cases were written by the AI assistant, not reviewed independently, and are
now development data too. The slowest lookup, about 15 s, was a long think on
a need the catalog does not list.

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
  within the latency budget. Before 2026-09-28 (`f8e87a55`) 24 children were
  fused but Cohere reranked only the first 16 and dropped the other 8.
- **Query expansion (2026-09-29).** Before retrieval the slang dictionary
  rewrites and expands the query (43 of the 155 questions change). With and
  without it, on the same code: hit@1 0.929 / 0.923, hit@3 0.987 / 0.994,
  hit@5 1.000 / 1.000, MRR 0.959 / 0.956. It moves one question into first
  place (101) and one out of the top 3 (080): a tie (McNemar p = 1.00) on
  development questions written in handbook-like wording. Those questions
  exercise only 14 of the 106 slang phrases, so a slang probe followed: 61
  gold-labelled `official_v1`/`v2` questions reworded with 30 testable slang
  phrases (canonical phrase replaced by the slang, sources unchanged). With
  the rewrite hit@5 was 61/61, without it 58/61; hit@1 46 against 43, MRR
  0.857 against 0.816. The three lost sources were "miễn giảm tiền học",
  "miễn giảm tiền trường" and "bị warning", which dense search did not map to
  học phí and cảnh báo học tập. Not significant at this size (p = 0.25 for
  hit@5), but only the arm without the rewrite loses sources, so the retrieval
  rewrite stays. BM25 also expands the 50 listed acronyms and 39 generated
  program acronyms itself, independently of this rewrite.
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

### Table-search candidate and task-local evidence (2026-10-02)

The candidate adds 35 frozen, source-reviewed Vietnamese descriptions to 3,800
narrative chunks. Metadata/cohort/provenance and raw tables stay canonical; the
descriptions locate sources and are not facts for generation. All 3,835 records
were re-embedded into separate Qdrant/MongoDB candidate collections. v35 is kept
unchanged. Publication, hashes and staged verification are in
[ROUTING_EVIDENCE_RELEASE.md](ROUTING_EVIDENCE_RELEASE.md).

Measured on 15 known development queries: BM25 parent Hit@5 is 12/15 without
handles and 15/15 with them; metadata-v1 and reviewed-v2 descriptions both score
15/15, so natural wording has no demonstrated gain over metadata v1. Live candidate
retrieval found the expected parent and table family for 15/15, with retrieval
p95 2.82 seconds. Family coverage is not exact table/scope correctness or answer
accuracy. One real TOEIC SSE question retrieved the appendix and copied all four
score components correctly, but added an unrelated student-affairs warning and
used recognition wording that could imply TOEIC is compulsory. It took 19.06
seconds. These are development observations, not a new hold-out or production claim.

The later offline audit found two evidence-contract defects: same-parent merge
discarded a later task's hydrated table; amendment selection could use the other
task's primary parents. Hydrated representations now stay task-local (ordinary
source fusion and final public citation dedup remain), and amendment targets must
belong to the current unit's authorized parents before ranking/limits. These are
general runtime fixes; no query-specific routing, answer_groups or DAG is added.
Planner v57 and composer v3.34 prompt text is unchanged by the evidence fix.
The candidate is not yet promoted into the deploy/build contract or activated on
HF, and the live TOEIC answer-quality limitations remain pending verification.

## Operations

| Setting | Value | Why |
|---|---|---|
| Start-up warm-up | Build the pipeline and the retriever, wait up to 180 s for BM25 | On the live Space the first RAG question took 23.3 s and the second 6.9 s, because the retriever and the BM25 index were built on first use; with the retriever warmed, the first took 7.5 s (`ac565c1c`) |
| Planner rate limits | 500 requests a minute, no local token limit; after a 429 wait up to 10 s, then the safe RAG plan | The account allows 500 RPM and 200,000 TPM for `gpt-6-luna`. A plan costs about 9,400 tokens (948 calls), so tokens bind first at about 21 questions a minute, which OpenAI enforces with 429s. The old local cap of 30 a minute (the free Groq limit of the Qwen era) failed the 31st question in a minute, and with a single key one 429 failed every question for 30 s; both now plan normally or fall back to RAG (offline simulation, `e7a19a21`) |
| Queue wait | 30 s (was 15 s) | A queued request waits for an active answer to finish, and answers took about 7 s at p50 and 9–10 s at p90 (`56453c13`) |
| Reranker timeout | 10 s, no retry | Cohere went from 5 s to 8 s when 24 candidates took up to 4.0 s; for Qwen3-Reranker-8B (max 9.3 s) 3 of 30 live calls fell back at 8 s; Voyage rerank-3 peaked at 1.35 s, so the 10 s budget is now slack. A retry would only double the wait at an overloaded service |
| Query embedding | 5 s timeout, 1 retry; on failure BM25 serves alone | Retrieval used to return nothing when the embedding call failed; with the API embedder a timeout now costs ranking quality, not the answer |
| Skipped rerank | Logged as a warning and recorded in telemetry | Trial-key limits used to skip reranking silently, dropping hit@1 from 0.897 to 0.832 |
| No answer cache, no Redis (2026-09-30) | Every question runs the planner, retrieval and composer. The public visit counter is one MongoDB document (`app_metrics`, `$inc` with upsert, 3 s timeouts); `STUDENT_RAG_VISIT_COUNTER=false` keeps a developer machine from counting | The answer cache was keyed by the exact question plus the evidence, and only 4 of 78 real requests hit it, most of them tests; a hit also made "Tạo lại" return the same answer. A semantic cache was rejected: a near-duplicate question can need a different cohort or article, and a wrong cached answer costs more than a composer call. Without the cache, Redis held only the visit counter, and MongoDB already serves the parent articles, so one service was dropped. On 2026-09-29 the Redis client had also had no timeouts, and the visit endpoint had blocked the event loop (fixed in `dbd23e29` before the removal) |
| LangSmith tracing (2026-09-29) | One root run per question. One LLM child run per call: planner, each directory-selector call (the thinking second look marked) and composer. Each child has the model, the provider, token usage in `usage_metadata` (cached input and reasoning tokens counted separately), the key's short hash and the timing. The root holds the planner's plan, the history turns the planner saw (last four, 300 characters each), per-task fact locks and directory decisions, and counts of corrected identifiers. Composer prompts are traced only with `STUDENT_RAG_TRACE_PROMPTS=1` | Before this, every call showed 0 tokens and no cost: usage was sent as `usage`, a field LangSmith 0.8.8 does not read. The OpenAI planner was labelled Groq, a leftover default from the Qwen era. Key hashes, directory-selector calls and the history were missing, and clarifications and cache hits lost the planner's run. A follow-up can be replayed from the traced history; evidence text can be rebuilt from the cited source ids, so it is not copied. Two verification traces: a full answer with a thinking second look cost 31,602 tokens, $0.0040 as priced by LangSmith, and the thinking call was its most expensive step; a clarification cost $0.0004. Each retrieval is a retriever child run too. It holds the time of each stage (embedding, Qdrant, BM25, rerank, graph), whether reranking was skipped and why, and the top 10 candidates with their rank in the dense, BM25 and fused lists (ids, no text). The rerank call is an LLM child run with the tokens and price DeepInfra reports, about $0.0002 a question. A warm request traced from Vietnam took 26.5 s: planner 11.1 s, retrieval 8.1 s (embedding 3.6 s), composer 2.8 s. One cold request showed BM25 not yet built, which the trace now makes visible |

## Defects found in the 2026-09-29 review

Each of these reached, or would have reached, a student. They were found by
reading traces, by new tests, or by checking an assumption, and each fix was
checked against the saved plans and answers.

| Defect | How it was found | Fix and why this one | Check |
|---|---|---|---|
| **A unit vanished from the evidence.** "email khoa toán, sdt khoa cntt" (K51) answered that the handbook gives no phone for Khoa CNTT, 4 times out of 4 | A student-style question in LangSmith; the planner and lookups were right, the evidence packet was not | A directory lookup cites its whole catalog (`student_faculty_profiles`), and the task merge keyed citations by that id, so two units of one catalog in two tasks collapsed into the first. The merge key now includes the record ids of directory evidence. Keying on the record, not on the catalog, keeps each task's evidence its own while the same record cited twice is still one source | Regression test; 3 of 2,488 saved plans change, all "email Khoa Tiếng Anh và Khoa Tiếng Pháp", which had lost Khoa Tiếng Pháp |
| **A miscopied email** ("khotienganh@hcmue.edu.vn" for "khoatienganh@hcmue.edu.vn") | Seen in a LangSmith trace; the saved official_v1 run of 2026-09-28 had the same slip (case 127). The data is right, so the composer dropped a letter despite the verbatim rule | An audit of 768 saved answers first measured the problem: 1 of 200 identifiers wrong, and 0 of the 43 numbers not found verbatim. So only identifiers are corrected, from the evidence, when exactly one near match exists; see *Identifiers are checked against the evidence* under Composer for the rule, the limits and why they are not wider | On the 768 saved answers exactly case 127 changes; unit tests for sync, stream and cache |
| **"in bảng điểm" not sent to Phòng Khảo thí** ("tui cần in bảng điểm và làm thủ tục chuyển trường thì đến đâu") | A LangSmith trace | The selector answered "none" because the catalog says "cấp giấy chứng nhận điểm"; the planner's slang rewrite had hidden this until it was removed. Looser prompt wording traded two found services for two others; a second look with thinking on, only when nothing is found, gained without losing. See *A second look with thinking* under Directory selection | New frozen set of 47 everyday wordings: 42 → 47 correct; existing development cases 187 → 188; 0 wrong units in every arm |
| **A table row not locked in multi-part questions** ("Rèn luyện 82 điểm được loại gì, học bổng giỏi cần rèn luyện bao nhiêu điểm?") | Rerunning `official_v2` deterministic on the current stack (case 091 and 116 failed on `resolved_result` although the plan was right) | The planner's contract says a slot span is quoted from the student's question or history, and the plan normaliser checks it there. The executor checked it again against the task's question, which the planner writes itself; "82 điểm" is not in "Điểm rèn luyện 82 được xếp loại gì?", so the row was not locked and the composer got only the whole table. The executor now grounds on the same text as the normaliser: the question, plus the referenced turns for a follow-up. The task question is the planner's paraphrase, so it could never show that a value came from the student | 2 of 2,488 saved plans and 2 of 154 `official_v2` plans gain a lock, all correct (82 → Tốt, 66 → Khá; 4,8 → Chưa đạt; chính quy → 8 years); none lose one |
| **Glued words in streamed answers** ("sinh viênnộp") | A new unit test for the stream cleaner | The held-back tail was flushed through `clean_answer`, which strips it; its leading space is now kept once text has been shown. `PIPELINE_VERSION` moved so cached glued answers are not served | 24 of the 150 saved answers, replayed as streams, would have glued two words |
| **Repeated words in the slang rewrite** ("xếp loại tốt nghiệp tốt nghiệp", "phòng khảo thí và đảm bảo chất lượng và đảm bảo chất lượng") | Reading the rewritten development questions | A replacement ending with the words the student wrote next drops those words. Only an overlap of two or more words counts: one shared word is often a coincidence ("đăng ký môn phần mềm" must keep "phần mềm") | Exactly 5 rewrites change on 681 questions, all of them repetitions |
| **Planner capped at 30 questions a minute** and failing on a busy key | Checking the key pool settings against the account's limits | See Planner rate limits under Operations | Offline simulation |
| **The image would not start: networkx undeclared** | Regenerating the dependency constraints | `graph_traverser.py` imports networkx, which only torch had pulled in; dropping torch with the API embeddings would have left the next Docker build without it. It is now in `requirements.txt` | Import audit of `src/` against `requirements.txt` |
| **Stale dependency constraints** | The same audit | The constraints are regenerated with uv for the Docker target (CPython 3.11, Linux x86_64): 26 pins nothing installs removed, 5 unpinned packages pinned, no version changed. pip cannot do this from Windows: it evaluates platform markers for the host | All 66 pins resolve to prebuilt Linux wheels, which `python:3.11-slim` needs |

## Earlier held-out results (official_v2, stack of 2026-09-12)

These measure the previous stack (Qwen3 planner on Groq, Gemini composer,
local `bge-m3`, Cohere reranking, v33 data), not the current one; the full
tables are in the [README](../README.md#results).

| Suite | Result |
|---|---|
| Deterministic (hold-out run) | 142/154 = 92.2%, 95% CI 86.9–95.5 |
| Retrieval | hit@5 94.6%, MRR 84.8 |
| Generate + judge | answer correctness 96.3, hallucination rate 6.5% |
| Production (60 requests on the live Space) | 7 of 12 release gates pass; success rate 96.7% |

The run exposed one real defect (K51 foundation/remaining grading, a failing
5.2 reported as a pass), fixed in `536169fc`; later `official_v2` runs are
post-fix.

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

## End-to-end check before the deploy (2026-09-30)

`official_v1` answers (150 cases) on the stack after the 2026-09-29 changes
(v35 data, BGE-M3 over the API, Qwen3-Reranker-8B, composer v3.30, identifier
correction, the selector's second look, fact-lock grounding), against the last
run on 2026-09-28. One run each, so single cases move with planner variance.

| Metric | 2026-09-28 | 2026-09-30 |
|---|---:|---:|
| Answer correctness | 0.990 | 0.970 |
| Faithfulness | 0.985 | 0.972 |
| Hallucination rate | 2.7% | 3.3% |
| Citation correctness | 0.976 | 0.967 |
| Abstention correct | 0.980 | 0.953 |
| Context precision / recall | 0.591 / 0.916 | 0.608 / 0.902 |
| Critical false passes | 0 | 1 |
| Latency p50 / p95 | 11.1 s / 21.5 s | 10.1 s / 21.4 s |

The four cases that dropped all come from a different plan, not from the
composer. Each was planned again five times on the same code:

| Case | 2026-09-30 run | Five new plans |
|---|---|---|
| 029 "đăng nhầm kết quả tốt nghiệp thì báo ai" | student_service, so the wrong office (the critical false pass) | RAG 5/5, correct |
| 110 "số điện thoại thư viện" | student_service, then a needless clarification | office 5/5, correct |
| 092 "TOEIC bốn kỹ năng bậc 3 từng phần" | RAG, "the sources do not say" | table 3/5, RAG 2/5 |
| 045 "có nằm trong quy định này không" | clarification | RAG 3/5, clarification 2/5; asking is defensible for "quy định này" |

So 029 and 110 were rare flips, and 092 is a real instability at the boundary
between a table value and a policy, the kind `official_v3` found in 003, 007
and 085. No prompt change follows: v54 and v55 tried this boundary and each
broke other cases, the failure costs a "not found" answer rather than a wrong
fact, and how often students ask this way is unknown.

This run is the first with the judge fix `d7ffaefb`. The judge used to see only
a source's title, so a correct answer naming the article and document (which
composer v3.30 does) read as an unsupported claim: on a 10-case `official_v2`
smoke the fix moved hallucination from 2/10 to 0/10 on the same answers. The
2026-09-28 run was judged before the fix, when the composer did not yet name
documents.

## Held-out end-to-end result (official_v4, 2026-09-30)

`official_v4` is 246 authored questions over 229 clusters, written against the
handbook and frozen before any of them was run (`data/eval/official_v4/SPEC.md`
fixes the metrics, the cluster bootstrap and the rerun rules). Full figures and
caveats are in `data/eval/official_v4/RESULTS.md`.

| | Run A, hold-out | Run B, after the fixes |
|---|---:|---:|
| Commit | `d3db167e` | `c23e027a` |
| **answer_correctness** | **0.926** | **0.942** |
| 95% CI over clusters | 0.899 – 0.950 | 0.920 – 0.962 |
| Hallucination rate | 0.093 | 0.130 |
| Critical false passes | 0 | 0 |
| Answers scoring 0.0 | 5 | 2 |

Run A is the hold-out: its code predates any sight of a v4 answer. Run B adds
the five fixes below, which were written after the 4B ablation was read, so it
describes the deployed system and is never quoted as a hold-out figure.

Run C (`1a9ccd3d`, 2026-10-01) adds the fixes of the sections below. Because
the Groq keys hit their daily cap, both run B and run C were judged by the same
model on DeepInfra. On run B's answers the two providers agree: 0.942 against
0.937, and 206 of 246 scores are identical. Run C scores **0.959** (CI 0.938 –
0.978) against run B's 0.937. The paired difference is +0.022, CI [-0.001,
+0.045], so the improvement is likely but not established. The criteria for
further fixes, set before reading, were a regression caused by the fixes or a
serious false statement not already known; neither was met. Details are in
`data/eval/official_v4/RESULTS.md`.

Paired over clusters, B − A is +0.016 with a 95% CI of [−0.008, +0.041]: over
the whole set the improvement is not established. It is established where it
was expected — unaccented and mistyped questions gained +0.124 (CI +0.034 to
+0.233, 0.834 → 0.958), which is what the BM25 fix targets — and absent
everywhere else (−0.013, CI −0.036 to +0.007).

The rising hallucination rate is the judge objecting to detail beyond the
sources on answers it also scores correct: 23 of run B's 32 flagged cases score
1.0. Wrong answers fell from 5 to 2, and both of run B's wrong answers came
from planner and composer variance rather than from a fix (in one the query
plan and the resolved table row are identical in both runs).

### The five fixes, found by reading the 4B ablation

| Fix | What was wrong |
|---|---|
| `bm25_retriever` indexes and queries both spellings | an unaccented question could not match accented handbook text |
| `catalog_relationship` accepts several service rows of one unit | a service question could not join to its office |
| `scholarship_lookup` matches a label as a whole word | "khác" was read as "Khá" |
| `foreign_language_lookup` matches a code as a whole word, and answers a named level from that column whenever the table fills it | "N30" was read as "N3"; a level column holding a score range was never matched |
| `query_plan` gives a single-task follow-up the standalone query | the scope named earlier in the conversation was dropped |

Only the BM25 fix has a measured end-to-end benefit. The `query_plan` fix was
compared on `official_v2`'s 25 follow-ups against the pre-patch normalizer with
one planner call feeding both: it changed 6 questions and lost no scope term,
which passes its criterion without showing a gain. The two whole-word fixes
carry regression tests and no measured v4 effect.

### Availability during the runs

Both runs were made from one home network on a day when every provider was
slow; a request that runs no model took 1.5–2.4 s. Run A's first pass lost
dense retrieval to the 5 s embedding timeout in 108 of 246 cases (those cases
scored 0.932 against 0.924 for the intact ones, so the BM25 fallback held), and
the rule for rerunning them was added after those scores were read, which
`RESULTS.md` states. Reruns and run B used
`configs/retrieval_eval_patient.yaml`, which raises the embedding and reranker
waits to 30 s and changes nothing else; deployment keeps `configs/retrieval.yaml`.
Whether the deployed timeouts should rise has to be decided on latency measured
from the deployment, not from this network.

## Fixes after reading the official_v4 answers (2026-10-01)

Every run B answer below 1.0 and every answer the judge flagged (43 cases) was
read against its required facts and the source data. Six answers stated
something false; the rest were incomplete or correct with extra detail. Three
causes were in what a description told a model, not in the data:

| Gap | Evidence | Fix |
|---|---|---|
| The scholarship table holds `scholarship_score_range`, but only the formula tool advertised "điểm học bổng" | V4-148 computed 3.20–3.60 where the table says 3.672; V4-150 sent the student to compute it | The classification aspect names the score range and the K51 columns; the formula tool hands range questions back |
| Directory lookups return `internal_numbers`, the composer dropped them | 9 cases asked for an extension, the payload held it 9 times, the answer printed it 4 times | `requested_field=phone` includes the extension; the composer gives every contact field the evidence has |
| The GPA rounding rule sat only in `raw_excerpt`, which the lookup never passed on | V4-025, V4-030 | A `rounding` field on the rule, carried in the lookup result |

`scripts/audit_tool_descriptions.py` now checks that every answerable field in
the data is named in its tool's registry text, and `tests/test_tool_description_audit.py`
fails on a new gap. Four known gaps remain: the scholarship tool reads the
eligibility and score-formula tables, but no value of `aspect` selects them, so
they are unreachable rather than unadvertised; reaching them needs code.

Not fixed, with the reason:

- **V4-070, dormitory application.** The service directory comes from the
  handbook's directory table, which lists no dormitory application for the
  student affairs office; that duty is in the office's numbered responsibilities
  in the regulations, a second source. Merging it changes every unit's services.
- **V4-107, graduate office routed to RAG.** The service directory holds the
  exact answer; the planner chose RAG for "liên hệ ở đâu để tìm hiểu quy chế".
  This is the "where" boundary that prompts v54 and v55 failed to fix.
- **Needless clarification (V4-100, V4-145, V4-092).** The prompt already forbids
  it; the planner did not follow the rule.
- **V4-003, V4-204.** Composer and planner variance: V4-003 had the same plan and
  the same resolved row as the run that answered correctly.

The registry text is part of the planner prompt, so `official_v1` was planned
again (`official_v1_deterministic_20260930T174119Z`, graded with the v10
contract the baseline used): **130/135**, against 133/135 before. Four cases
newly failed and one newly passed. Each newly failing case was planned again
under the old and the new prompt:

| Case | Old prompt | New prompt | Reading |
|---|---:|---:|---|
| 003 "Môn đại cương 8,8 được A chưa?", keeps `course_scope=foundation` | 10/20 | 5/20 | unstable under both prompts; the baseline pass was a coin flip |
| 032 TOPIK II, keeps "bậc 3"/"bậc 4" | 19/20 | 18/20 | no difference |
| 038 TOEFL iBT, keeps "bậc 3"/"bậc 4" | 5/5 | 5/5 | the failed run was a rare draw |
| 122 certificate office, plans `student_service` | 4/5 | 4/5 | no difference |

No case shows an effect of the change that its variance does not explain, so
the 130 against 133 is read as planner variance. Case 003 is a standing
instability of the scoring boundary, not a new one.

## Structured data of the three cohorts, checked against the handbook (2026-10-01)

Prompted by an owner's question the system could not answer ("học cntt ra trường
làm gì"), the structured layer of K48-K49, K50 and K51 was checked whole:
coverage per cohort, fields left empty though the source holds a value, text
leaking between records, and the K51 amendments.

What held:

- Every table type and directory exists for all three cohorts.
- Decision 4743/QĐ-ĐHSP amends seven points of the training regulation from the
  2025 intake (K51). Two are tables, and both are applied: study duration
  (chính quy 04/06 years, vừa làm vừa học 05/7,5) and the split grade scale (D and
  D+ pass for foundation courses, fail for the rest). The other five are rules,
  read by RAG with `amendments.json`.
- The foreign-language table exists only in the K50 handbook (Decision 3215);
  its own Điều 1 covers intakes from 2022, so it serves all three cohorts.

Three defects, fixed:

| Defect | Scope | Fix |
|---|---|---|
| Career sections unreachable | all 129 program records; the planner judged the question out of domain or sent it to RAG, where no chunk holds a career section | the program tool names careers and offers `requested_field=career` |
| Addresses under "Phòng làm việc" not read | 4 units (Trung tâm Ngoại ngữ, Trung tâm Tin học, Trung tâm Hỗ trợ sinh viên và Phát triển khởi nghiệp, Đoàn Thanh niên – Hội Sinh viên) in K48-K49 and K50: 26 service rows and their profiles without an address | the extractor reads every address label, including Trung tâm Tin học's "Văn phòng ghi danh" |
| A faculty given its programs' careers as duties | 31 of the 34 faculties the keyword guess matched | faculties get no text-derived duties |

`scripts/audit_extraction.py` now checks every table cell, formula and directory
contact value against its source text, and every labelled contact value in the
source against its field. Run on the catalogs before the fix it reports the 26
rows; after it, only the scholarship eligibility table, a faithful short
restatement of Điều 27 that no `aspect` selects yet.

Measured after the fixes, at `a1b82a6b`:

- **Career questions.** Nine questions over different programs and wordings
  (abbreviated, unaccented, colloquial), planned three times each: 27 of 27 go
  to the program tool for careers, against 0 of 9 before; a tenth, asking where
  the IT faculty's office is, stays with the faculty tool 3 of 3. Asked end to
  end, the answers quote the handbook's career sections.
- **official_v1 planner: 134/135** (v10 contract). Runs of this prompt family
  have scored 133, 130 and 134; the one failure, 093, plans the same way under
  the old and the new prompt (9 of 10 plans correct under each).
- **Composer v3.31**, replayed on run B's 246 evidence packets and judged:
  answer correctness 0.942 → **0.958**, paired over clusters **+0.015**, 95% CI
  [+0.002, +0.030]. The four answers that had dropped an extension now give it;
  unsupported-claim flags fell from 32 to 22. One critical false pass appeared,
  V4-148: the packet (planned by run B) holds only the scholarship formula, and
  both prompt versions derived a wrong range from it; with the new tool
  descriptions the planner sends that question to the scholarship table in 10
  of 10 plans. This is v4 data, so it is not a hold-out result.

Not covered: no cell was compared character by character with the PDF, only
with the extracted handbook text; each program's faculty is checked by count
and presence, not record by record against the handbook; K52 is not in the
data.

## The RAG branch, checked against the handbooks (2026-10-01)

What the index holds, and how retrieval and section text compare with the PDFs:

- **Index complete and in sync**: 541 sections (MongoDB holds 541) and 3,800
  chunks (Qdrant holds 3,800); every section has at least one chunk, none empty.
- **Retrieval on official_v4** (run B): 160 of 162 cases got every section their
  current question needs (98.8%). For a follow-up only the current turn's
  section is required; v4's expected list also names the previous turn's. The
  two misses retrieved nothing by design: V4-070 was planned to the directory,
  V4-100 asked back.
- **Coverage against each handbook's table of contents**: every regulation,
  policy and notice is indexed. Out of scope and left out: the college-level
  preschool regulation (Quyết định 3533, a branch-campus programme) and the
  branch-campus sections. Not indexed: the school overview (all three cohorts),
  the museum and historic-site lists (K48-K49, K50), K51's dormitory flowchart
  page (the procedure itself is indexed) and K48-K49's research-report appendix.
- **Section text**: 96–97% of the regulation sentences in the PDFs are in a
  section; the rest are preambles, signatures, forms, table rows stored as
  tables, and out-of-scope text. No section swallows another article's heading,
  carries a page header, holds a broken table or duplicates another of its
  cohort. Two sections are cut (K50 and K51 advising regulation, Điều 4), losing
  a cross-reference. Recorded page numbers: 451 sections right, 2 wrong.
- **Amendments**: all 7 of K51's amendments attach to the right sections; of the
  7 v4 cases that received one, 6 scored 1.0.
- A claim made during the audit and withdrawn: the handbook's "Một số công việc
  của các phòng và trung tâm" table is not missing information. Its seven
  matters are in the service directory in the units' own words, and the
  production selector picked the right unit for 23 of 24 student phrasings.

## Answers follow the student's own handbook (owner decision, 2026-10-01)

Reading the handbooks' own clauses showed that a cohort's handbook can be out of
date for rules that bind every intake:

| K48-K49 handbook | Since replaced or reissued |
|---|---|
| Student affairs regulation, Quyết định 989 (2022) | Quyết định 1999 (2024), "thay thế cho Quyết định số 989"; consolidated as Quyết định 2535 (2025, K51), "áp dụng cho tất cả các khoá tuyển sinh" |
| Conduct assessment regulation, Quyết định 2650 (2022) | Quyết định 2000 (2024), "thay thế Quyết định số 2650" |
| Academic advising regulation, Quyết định 134 (2014) | Quyết định 2001 (2024), printed in K50 and K51 |
| Fee and support notices of 2022–2023 | each handbook prints its own year's; K51 prints 2025–2026 |

K50's student affairs regulation is likewise superseded by K51's consolidated
text. The difference matters: K51 states the scholarship rule by classification
pairs, K48-K49 and K50 by score ranges.

The owner chose to keep answers faithful to the student's own handbook, because
a K49 student who checks an answer against the K49 handbook must find it there.
So the composer names the handbook of the sources it uses ("Theo Sổ tay sinh
viên khóa K50 (năm học 2024 – 2025)"), and when a source belongs to a document
listed in `configs/handbook_currency.yaml` it adds that document's note, which
says what is newer and where it is printed. Every note quotes its basis and
claims a replacement only where a "thay thế" clause says so. Newer content is
never substituted, and the three documents printed only in later handbooks
(off-campus residence, conduct code of 2023, talented-learner policy) are not
offered to the earlier cohorts.

Measured at `ecda6cda`, composer v3.32 replayed on run B's 246 packets: the
handbook is named in 233 answers and a note appears in 71; answer correctness
0.959 against v3.31's 0.958 (paired +0.002, 95% CI [-0.012, +0.015]). The judge
first read the notes as unsupported (flags 22 → 36) because its context omitted
them; with the fix it sees them (29 flags).

For the thesis, the evaluation's correct answer is therefore "faithful to the
student's own handbook", and the table above is a limitation of that choice.

Found while measuring, and fixed afterwards (next section):

- **V4-020**: asked about academic "Khá" with conduct "Tốt" under K51's
  classification table, the composer often reads "Khá trở lên" as excluding
  "Tốt" and denies the scholarship: wrong in about 6 of 8 draws under v3.31 and
  fewer under v3.32.
- **"IELTS 5.0 có đạt chuẩn đầu ra bậc 3 không?"** and similar questions go to
  RAG. The equivalence table is printed as an appendix inside the article
  "Điều 8. Tổ chức thực hiện", so RAG reaches it only when that article is
  retrieved; otherwise the answer says nothing was found.

## Minimum levels and "does my value meet the condition" (2026-10-01)

**Minimum levels (V4-020).** Each "<level> trở lên" cell of a
classification table keeps the handbook's wording. Its row gains
`<column>_admitted_levels`, for example "Tốt; Xuất sắc"
(`src/retrieval/core/ordinal_labels.py`). Composer v3.33 also states the order
of the academic and conduct scales. Live pipeline, K51:

| Academic + conduct | Answer |
|---|---|
| Giỏi + Xuất sắc | Giỏi |
| Khá + Xuất sắc | Khá |
| Khá + Tốt | Khá |
| Xuất sắc + Tốt | Giỏi |

All four are right.

**A value checked against a condition (planner v56).** v56 adds one general
rule to v53: "Hỏi giá trị cụ thể có đạt điều kiện không → structured tra giá
trị + RAG đọc điều kiện". It names no tool or topic. Planner probes (K51,
counts of a lookup task, with RAG beside it for the two "đạt chuẩn đầu ra"
questions):

| Question | v53 | v56 |
|---|---:|---:|
| IELTS 5.0 có đạt chuẩn đầu ra bậc 3 không | 0/3 | 4/4 |
| TOEFL iBT 45 có đủ chuẩn đầu ra không | 1/3 | 4/4 |
| TOEIC 4 kỹ năng muốn bậc 4 thì từng kỹ năng cần bao nhiêu (v1 036) | 8/8 | 8/8 |

On another topic, "Điểm rèn luyện 60 có đủ điều kiện xét học bổng không"
became a conduct lookup plus RAG 3/3. That question was not planned under v53.

**A first attempt that regressed.** The first version had two problems:

- It split each minimum-level cell into one row per admitted level, which
  replaced the handbook's cells.
- It rewrote the foreign-language tool description around the "chuẩn đầu ra"
  question.

official_v1 fell from 134 to 131/135:

- 057 and 060: the rows no longer matched the handbook.
- 036: the planner went to RAG in 3 of 8 draws. With the general rule and the
  original description it is back to 8/8, so the tailored description was the
  harmful part and was dropped.

The final version (`1a9ccd3d`) scores **133/135** on official_v1, against
134/135 before. Both failures are known unstable cases:

- 032: the planner writes the levels as "3"/"4" instead of "bậc 3"/"bậc 4"
  in 2 of 6 draws.
- 096: the planner asks `requested_field=office` instead of `unit` in 2 of 6
  draws.

093, which failed before, passed.

**Not fixed.** "TOEIC bao nhiêu điểm thì đạt chuẩn đầu ra bậc 3?" gives no
value to check and still goes to RAG (1 of 3 draws under v56 reached the table). A
wider rule ("hoặc cần giá trị nào để đạt") did not change it and was not kept.
Splitting the appendix out of Điều 8 in the index would fix the RAG side. That
means rebuilding and re-uploading the index, so it is left for a later data
build.

## The judge against a second rater (2026-10-01)

The judge (gpt-oss-120b on Groq) was compared with a second rater, Claude
(Opus 5.5), on official_v4 run B (`official_v4_answers_20260930T152637Z`). This
is a model-to-model check, not a human calibration.

**Sample.** Every answer the judge scored below 1.0 (36) and 30 of the 210 it
scored 1.0, drawn with seed 20261001 (`data/eval/official_v4/judge_calibration/sample.json`).

**Rubric.** Fixed before reading. Each answer was scored against the question,
the gold answer and the required facts, and checked in the handbook data where
a claim was in doubt:

- 1: everything asked is answered correctly;
- 0.75: the core is right but one asked detail is missing;
- 0.5: one part of a multi-part question is right;
- 0.25: mostly wrong;
- 0: wrong, or a "not found" for an answerable question.

Each answer also got a label:

- C: the student gets a correct answer to what was asked;
- I: incomplete;
- W: states something false.

Gold facts that the question did not ask for, such as an email when only the
address was asked, were not required. A missing internal extension counted
only when the question asked for the phone number.

**Blindness.** The scores were written to `my_scores.tsv` before the judge's
scores were opened. The 30 answers the judge scored 1.0 had not been read
before. The 36 lower ones had, during the audit above, together with the
judge's flags. Their scores are therefore not independent of the judge.

`python -m scripts.judge_calibration` gives (`result.json`):

| Stratum | n | Judge mean | Rater mean | Within ±0.25 |
|---|---:|---:|---:|---:|
| Judge 1.0 (random 30 of 210) | 30 | 1.000 | 1.000 | 30/30 |
| Judge below 1.0 (all) | 36 | 0.606 | 0.812 | 22/36 |
| Whole run, rater reweighted by stratum | 246 | 0.942 | 0.973 | |

- **No false pass at 1.0 in the sample.** Every answer the judge scored 1.0
  was correct to the rater. With 0 of 30, the rate of false passes among the
  210 is below about 10% at 95% (rule of three).
- **The judge is stricter than the correctness criterion.** 19 of the 36
  answers it scored below 1.0 are correct to the rater. Most of its deductions
  are for gold facts the question did not ask for:
  - phone or email when only the unit or address was asked: V4-143, V4-131, V4-145;
  - the standard duration when only the maximum was asked: V4-197;
  - the rounding rule: V4-025.

  In one case it named facts as missing that the answer contains: V4-117, the
  GPA condition and the 2025 re-entry clause. So the reported 0.942 is a
  conservative figure; the rater's estimate is 0.973.
- **One soft false pass.** The judge gave V4-148 0.85, but the answer stated
  the scholarship score range as 3.20 to below 3.60; the handbook gives
  3.20–3.67. At a pass line of 0.8, the judge passes 2 answers the rater does
  not (V4-111 incomplete, V4-148 wrong) and fails 7 the rater finds correct.
- **Real failures in the sample.**
  - 2 answers state something false: V4-003 (3.75 classed Giỏi) and V4-148.
  - 4 fail a whole part of the question:
    - V4-100, V4-092: needless clarification;
    - V4-107: the "where" boundary;
    - V4-204: "not found" for the support centre's services.
  - 11 more miss a detail that was asked.

  These are the cases already listed as fixed or as known limitations above.

**Use.** The judge's scores rank runs and find failures, since every run is
scored by the same judge. They are not an absolute measure of how often
students get a correct answer, which is probably higher than the score.

**Limits.**
- The second rater is a model, not the owner or a student.
- The low stratum was not read blind.
- Ten disagreements are left for the owner to re-score: V4-117, V4-148,
  V4-070, V4-225, V4-143, V4-186, V4-197, V4-145, V4-138 and V4-111.

## What these measurements do not show

- A comparison with plain RAG (no planner) or with a long-context model given the
  whole handbook; these baselines are planned for the paper.
- The graph and BM25 ablations on the current stack. The runner has the modes
  (`--retrieval-mode no_graph`, `--retrieval-mode vector_only`, fixed in
  `dfcc2dc8` so that `vector_only` really skips BM25), but no run of them has
  been reported; the dense-only numbers above come from the reranker scripts.
- End-to-end answer quality of later fixes on a new hold-out. `official_v4`
  run A is the historical hold-out; B/C and subsequent fixes are post-fix.
  `official_v3` has only a planner suite and was used after its first run.
- How often the planner sends a question about a table value to RAG. It is
  about 1–2% of the development cases (v1 092, v3 003, 007, 085), and the student
  gets a "not found" answer. Real questions after the deploy will show whether
  it matters.
- The judge's agreement with a human rater. It was compared only with a second
  model (see "The judge against a second rater"). Both datasets were written by
  one author from handbook content, not collected from real students.
- Combinations not run, such as Qwen3-Embedding-8B with Qwen3-Reranker-8B.
- Whether the composer sends students to units the evidence does not name. When
  the handbook does not say where to go, the composer sometimes suggests an
  office from general knowledge. For "tui cần in bảng điểm và làm thủ tục
  chuyển trường thì đến đâu" (K51, whose handbook gives no office for
  transfers), 2 of 3 runs added "liên hệ Phòng CTCT&HSSV" or "Phòng Đào tạo
  hoặc Phòng CTCT&HSSV". Both runs first said the source names no office.
  Across the 768 saved answers, the 6 distinct sentences sending the student
  to a unit all named a unit in the evidence, with its contacts. The prompt is
  left as it is: the observed suggestions are plausible and marked as not from
  the handbook, and forbidding them risks a more rigid composer for a failure
  not yet seen. The audit found suggestions by phrases such as "nên/có thể
  liên hệ" and "để được hướng dẫn", so other wordings could be missed, and the
  saved answers hold few questions the handbook cannot answer. Revisit if a
  trace shows a suggestion naming the wrong unit.
- Whether answers should leave out the branch campus (Phân hiệu Long An). The
  chatbot serves the main campus. Branch contacts cannot reach an answer: none
  of the 494 records in the service, office, faculty and program catalogs
  names the branch, and every contact in an answer comes from those catalogs.
  Branch text can still arrive through retrieved handbook text. Across the 768
  saved answers, 10 questions (none asking about the branch) had answers
  mentioning it:
  - 8 quote regulation wording that applies to every student ("xác nhận của
    Trưởng khoa hoặc Giám đốc phân hiệu");
  - 1 lists the forms page's links under a separate "Tại phân hiệu" heading.

  The transfer question above also listed the rule for the branch's college
  programme in early-childhood education, marked as such. The composer does
  this because it is told to present every case it cannot rule out, and it is
  never told the student studies at the main campus. It is left as it is: the
  text is faithful and labelled, and forbidding branch content would drop real
  conditions from the regulations. If shorter answers are wanted, telling the
  composer the student's campus is the change to try, measured with the judge.

## Raw reports

Evaluation reports are git-ignored and stay on the development machine under
`data/eval/reports/`:

| Measurement | Report |
|---|---|
| Composer Gemini against DeepSeek | `official_v1_answers_20260927T124310Z` (DeepSeek), `official_v1_answers_20260927T131333Z` (Gemini) |
| Luna v51 / v52 on v1, v52 on v3 | `official_v1_deterministic_20260927T092317Z`, `…T101327Z`, `official_v3_deterministic_20260927T103000Z` (results also in `data/eval/official_v3/RESULTS.md`) |
| Directory matching | `directory_matching_20260927T…` and `…20260928T…`; `service_matching_calibration_*` for the thresholds |
| Retrieval, reranker, embedding, depth, BM25, thinking | `measurements_20260928/` (its README lists each script, commit and result file) |
| Thinking off against low, judged | `measurements_20260928/results/v330/` (`off_judge.json`, `low_judge.json`) |
| End-to-end development questions | `supplementary_questions_20260928T231521Z` |
| Planner input with and without the slang rewrite | `official_v1_deterministic_20260929T045740Z` (with), `…T051501Z` (without) |
| official_v4 run A (hold-out) and run B (after the fixes) | `official_v4_answers_20260930T112153Z` (run A, in the `student_handbook_rag_voyage` worktree) and `official_v4_answers_20260930T152637Z` (run B), each with its `v4_report.json`; ablations `…T060046Z` (8B, 105 cases without a reranker) and `…T063041Z` (4B) |
| Reranker comparison on v1 with shared candidates | `reranker_compare_v1/` and `reranker_compare_v1_patched/` |
| query_plan normalizer, patched against frozen | `plan_normalizer_compare/` |
| Structured lookup audit over every table and cohort | `structured_lookup_audit/` |
| Retrieval with and without query expansion | `official_v1_retrieval_20260929T045526Z` (with), `…T052455Z` (without) |
| Slang probe | `measurements_20260928/results/slang_probe/` (`slang_probe.py`) |
| "Where" questions and table-adjacent rules | `table_adjacent_questions_20260929_run1-3` and `regwhere_v53_20260929_run1-3` (v53); `where_v54_20260929_run1-3`, `official_v1_deterministic_20260929T124205Z` and `official_v2_deterministic_20260929T125553Z` (v54); `where_all_v55_20260929_run1-3` (v55); `official_v2_deterministic_20260929T111444Z` (v53, before the fact-lock grounding fix) |
| Directory selector, second look | `directory_matching_20260929T100059Z` / `…T100140Z` (before), `…T100338Z` / `…T100416Z` (looser wording), `…T102008Z` / `…T101754Z` (thinking on every call), `…T103359Z` / `…T103530Z` (second look); existing cases first, everyday set second |
| End-to-end check before the deploy | `official_v1_answers_20260930T023654Z` (against `…20260928T062050Z`); the five replans in its `replans_029_045_092_110_x5.json`; judge fix: `official_v2_answers_smoke10_20260930T011049Z` and `…_rejudge` |
