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
| Composer | DeepSeek flash, thinking off, prompt v3.30 | Gemini 3.1 Flash-Lite; DeepSeek thinking low | Same quality as Gemini with 0 failures against 20/150; thinking low judged the same (correctness 0.991 against 0.988) and 3 s slower |
| Directory selection | Exact name, otherwise DeepSeek picks from the closed catalog; when it finds nothing, the same prompt again with thinking low | Fuzzy-score thresholds; looser prompt wording; thinking on every call | Development cases: 10 wrong units under thresholds, 0 with the selector. The second look: everyday wordings 42 → 47 of 47, 0 wrong, median 0.86 s against 1.5 s for thinking on every call |
| Embedding | `BAAI/bge-m3` over the DeepInfra API | Local `bge-m3`; Qwen3-Embedding-8B | API vectors identical to local; Qwen3-8B ties after reranking, with query p50 6.3 s against 1.3 s |
| Reranker | Qwen3-Reranker-8B on DeepInfra, on all 24 fused children | None; Cohere rerank-v4.0-fast; Qwen3-Reranker 0.6B, 4B | hit@1 0.923 / hit@5 1.000 against Cohere 0.897 / 0.981 and none 0.832 / 0.955 |
| Lexical search | BM25 fused with RRF (k = 60), scored by BM25 only | Dense only; BM25 with a title-match rule | RRF + rerank beats dense + rerank; the title rule cost hit@1 and 3× BM25 time |
| Candidate depth | 24 children for dense, BM25, fusion and rerank | 16, 40 | 24 holds the first gold child for 155/155 questions, 16 for 154/155 |
| Tables | Reviewed JSON tables for lookup; readable tables kept in parents; no table rows embedded | The composer reading tables from retrieved text | The composer picked the wrong row of a range table in every try (sup_05, grade_remaining) |
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

## Operations

| Setting | Value | Why |
|---|---|---|
| Start-up warm-up | Build the pipeline and the retriever, wait up to 180 s for BM25 | On the live Space the first RAG question took 23.3 s and the second 6.9 s, because the retriever and the BM25 index were built on first use; with the retriever warmed, the first took 7.5 s (`ac565c1c`) |
| Planner rate limits | 500 requests a minute, no local token limit; after a 429 wait up to 10 s, then the safe RAG plan | The account allows 500 RPM and 200,000 TPM for `gpt-6-luna`. A plan costs about 9,400 tokens (948 calls), so tokens bind first at about 21 questions a minute, which OpenAI enforces with 429s. The old local cap of 30 a minute (the free Groq limit of the Qwen era) failed the 31st question in a minute, and with a single key one 429 failed every question for 30 s; both now plan normally or fall back to RAG (offline simulation, `e7a19a21`) |
| Queue wait | 30 s (was 15 s) | A queued request waits for an active answer to finish, and answers took about 7 s at p50 and 9–10 s at p90 (`56453c13`) |
| Reranker timeout | 10 s, no retry | Cohere went from 5 s to 8 s when 24 candidates took up to 4.0 s; for Qwen3-Reranker-8B (max 9.3 s) 3 of 30 live calls fell back at 8 s. A retry would only double the wait at an overloaded service |
| Query embedding | 5 s timeout, 1 retry; on failure BM25 serves alone | Retrieval used to return nothing when the embedding call failed; with the API embedder a timeout now costs ranking quality, not the answer |
| Skipped rerank | Logged as a warning and recorded in telemetry | Trial-key limits used to skip reranking silently, dropping hit@1 from 0.897 to 0.832 |
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

## What these measurements do not show

- A comparison with plain RAG (no planner) or with a long-context model given the
  whole handbook; these baselines are planned for the paper.
- The graph and BM25 ablations on the current stack. The runner has the modes
  (`--retrieval-mode no_graph`, `--retrieval-mode vector_only`, fixed in
  `dfcc2dc8` so that `vector_only` really skips BM25), but no run of them has
  been reported; the dense-only numbers above come from the reranker scripts.
- End-to-end answer quality of the final stack on a hold-out; it will be judged
  once on `official_v3`.
- The judge's agreement with a human rater; both datasets were written by one
  author from handbook content, not collected from real students.
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
| Retrieval with and without query expansion | `official_v1_retrieval_20260929T045526Z` (with), `…T052455Z` (without) |
| Slang probe | `measurements_20260928/results/slang_probe/` (`slang_probe.py`) |
| "Where" questions and table-adjacent rules | `table_adjacent_questions_20260929_run1-3` and `regwhere_v53_20260929_run1-3` (v53); `where_v54_20260929_run1-3`, `official_v1_deterministic_20260929T124205Z` and `official_v2_deterministic_20260929T125553Z` (v54); `where_all_v55_20260929_run1-3` (v55); `official_v2_deterministic_20260929T111444Z` (v53, before the fact-lock grounding fix) |
| Directory selector, second look | `directory_matching_20260929T100059Z` / `…T100140Z` (before), `…T100338Z` / `…T100416Z` (looser wording), `…T102008Z` / `…T101754Z` (thinking on every call), `…T103359Z` / `…T103530Z` (second look); existing cases first, everyday set second |
