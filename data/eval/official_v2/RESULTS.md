# official_v2 results

One run per suite on 2026-09-12, on the frozen bundle. The runtime was commit
`d09e970` (pipeline v76, planner Qwen3 prompt v43 on Groq, normalizer v28, composer
Gemini 3.1 Flash-Lite, judge `openai/gpt-oss-120b`); router and response caches off.
These numbers describe that commit, and they are the only hold-out measurement of
official_v2: the runtime has since changed (case 003 below exposed a real defect, fixed in
`536169fc`), so later runs of this bundle are post-fix regression measurements on a seen
set. See the bundle [README](README.md) for the protocol that now applies.

Reports live under `data/eval/reports/` (not in git):

- `official_v2_deterministic_20260912T043159Z`
- `official_v2_retrieval_20260912T044413Z`
- `official_v2_answers_20260912T045237Z`

## Headline

| Suite | Metric | Result |
|---|---|---|
| Deterministic | pass rate | 142/154 = 92.2% (CI 86.9–95.5) |
| Retrieval | Hit@1 / Hit@5 / MRR / nDCG@5 | 77.4 / 94.6 / 84.8 / 85.3 |
| Retrieval | required-source recall@5 | 91.9 |
| Judge | answer correctness / faithfulness / relevancy | 96.3 / 96.0 / 98.8 |
| Judge | citation correctness / context recall / context precision | 96.6 / 84.5 / 60.8 |
| Judge | hallucination rate / critical false passes | 6.5 / 3 |

Per-slice tables with 95% intervals:

```bash
python -m scripts.report_official_slices data/eval/reports/official_v2_deterministic_20260912T043159Z/deterministic.json --bundle official_v2
python -m scripts.report_official_slices data/eval/reports/official_v2_answers_20260912T045237Z/generated_answer_judge.json --bundle official_v2
python -m scripts.report_official_slices data/eval/reports/official_v2_retrieval_20260912T044413Z/retrieval.json --bundle official_v2
```

## The 12 deterministic failures

| Case | Slice | Question | Judge answer correctness |
|---|---|---|---:|
| 003 | single.scoring | Học phần chuyên ngành em được 5,2 vậy có bị rớt môn không? | 0 |
| 008 | single.scoring | Môn giáo dục thể chất chỉ xét đạt hay không đạt, em được đúng 5,0 vậy  | 100 |
| 024 | single.scholarship_classification | Học bổng loại khá thì số tiền nhận được tính kiểu gì? | 100 |
| 042 | single.student_service | Có khiếu nại về chuyện đào tạo thì gửi đơn cho đơn vị nào? | 0 |
| 070 | boundary.clarify | Học kỳ này em xếp loại học lực gì ạ? | 90 |
| 090 | multi_intent.struct_struct | GPA 3,65 xếp loại gì, và muốn học bổng xuất sắc thì rèn luyện phải loạ | 100 |
| 096 | multi_intent.struct_struct | TOEFL ITP bao nhiêu thì tương đương bậc 3, nộp chứng chỉ để xét miễn n | 40 |
| 102 | multi_intent.regu_regu | Điểm rèn luyện toàn khóa tính thế nào, thấy sai thì khiếu nại ở đâu? | 50 |
| 121 | multi_cohort.structured | Học bổng giỏi của K50 và K51 xét điều kiện khác nhau thế nào? | 100 |
| 122 | multi_cohort.structured | Hệ chính quy K50 và K51 được học tối đa bao nhiêu năm? | 100 |
| 130 | memory.cohort_switch | Thế còn K50 thì sao? | 75 |
| 147 | memory.pronoun | Số điện thoại phòng đó là gì? | 0 |

Half of them (6 of 12) still produced an answer the judge scored at or above 80: the plan
or the evidence scope did not match the contract, but the student would have read a correct
answer. The other six are real answer failures worth reading case by case.

## Answers the judge scored below 80

| Case | Score |
|---|---:|
| 003 | 0.0 |
| 042 | 0.0 |
| 147 | 0.0 |
| 096 | 40.0 |
| 111 | 40.0 |
| 102 | 50.0 |
| 130 | 75.0 |

## Regression check on official_v1

Same runtime, deterministic suite: 129/135, the same six failing cases as the run before
the G1-2 and G2-1 refactors.

## What these numbers do not cover

- No production suite in this scope, so no live-API latency or release-gate result.
- One author wrote the questions and the gold; no second reviewer.
- The judge is an LLM; its agreement with a human rater has not been measured.
- One run per suite, so run-to-run variance is unknown.
