# Tổng hợp metric v6 và đánh giá khả năng chốt dự án

Ngày: 31/08/2026. Phạm vi: đối chiếu các output v6 đã có, mã evaluator liên quan và audit đã lưu; không chạy lại model, sửa runtime, sửa gold hay thực hiện security/load audit mới.

## 1. Kết luận điều hành

**Có thể chốt mốc dự án portfolio/beta và bắt đầu đọc source ngay. Không nên tuyên bố toàn bộ evaluation hợp lệ, mọi gate pass, hoặc hệ thống đã sẵn sàng làm nguồn tư vấn chính sách có thẩm quyền.**

- Điểm mạnh có bằng chứng tốt nhất: Retrieval end-to-end **154/160 Hit@5 = 96,25%**, MRR **0,8585**, nDCG@5 **0,8557**, không quan sát cross-cohort leakage trong 160 case.
- Generate/Judge có đủ 150 output và 150 judge hợp lệ. Điểm trung bình cao nhưng vẫn có failure, sai số của judge/matcher và khác biệt đáng kể giữa single-target với mixed query.
- Production đã hoàn tất 60 request: HTTP 60/60, payload 59/60, status 57/60. Đây không phải tỷ lệ nội dung đúng; controlled cold-cache benchmark không hợp lệ.
- **Phải đính chính Deterministic:** 118/140 là kết quả của evaluator legacy, chưa phải full QueryPlan/structured-contract exactness. Không dùng các số 100% value/citation ở báo cáo này để quảng bá.
- “Human audit” trong tên file là AI-assisted evidence review do Codex làm, người dùng duyệt. Chưa có bằng chứng một đợt chấm độc lập của chuyên gia/người thứ hai. Không gọi là independent human evaluation.
- Không có căn cứ để đập lại kiến trúc, bỏ validator, thêm reranker/agent hoặc tiếp tục nối dài prompt. Phần cần chỉnh trước hết là tính đúng của phép đo, rồi các failure family cụ thể nếu chuyển sang production đáng tin cậy hơn.

Mốc hợp lý để kết thúc: **beta/portfolio release with documented limitations**, không phải “zero-defect policy assistant”. Metric được đóng băng là kết quả quan sát của một phiên bản, không phải chứng nhận vĩnh viễn cho mọi bản refactor sau đó.

## 2. Phiên bản và phạm vi mẫu

Manifest khóa runtime `b0560d1b06355737dd576ff8f01c4102c6fe7a8a`:

- Planner: `qwen/qwen3.8-27b`, reasoning `low`, `json_schema`, strict false.
- Planner prompt: `structured-regulation-v36-qwen38-schema`.
- Normalizer: `v13-task-local-fallback`.
- Composer: `gemini-3.1-flash-lite`, prompt `student-handbook-answer-v3.21-runtime-clarification`.
- Pipeline: `v52-runtime-clarification`.
- Retrieval/Generate: `vector_primary_graph_supplement`, không reranker; Qdrant `student_handbook_semantic_v32`, MongoDB `parent_docs_v32`.
- Judge: `openai/gpt-oss-120b`, rubric riêng của dự án; **không phải RAGAS**.
- HEAD local khi tổng hợp: `ea61818b`; `git diff b0560d1b..HEAD` trên runtime/config/frontend/artifact directories không có thay đổi. Các commit evaluator không được đồng nhất với runtime commit.

| Bộ | Số lượng | Phân bố |
| --- | ---: | --- |
| Deterministic | 140 | 60 single structured; 28 compound; 24 capability boundary; 12 missing/ambiguous; 8 unsupported in-domain; 8 OOD |
| Retrieval | 160 | 96 semantic; 24 exact article; 24 graph-linked; 16 multi-source |
| Generate + Judge | 150 | 72 RAG; 30 structured; 18 mixed; 10 clarification; 10 unanswerable; 10 OOD |
| Audit chọn trước | 40 trong 150 | 16 RAG; 8 structured; 6 mixed; 4 clarification; 3 unanswerable; 3 OOD |
| Audit mở rộng | 60 trong 150 | 40 chọn trước + 20 automatic failures ngoài tập 40 |
| Production | 60 request / 50 query | 20 cold RAG; 10 structured; 10 warm repeats; 10 streaming; 10 burst |

Không cộng thành 510 câu hỏi độc lập. Đối chiếu query sau lowercase/collapse whitespace cho thấy **312 chuỗi query duy nhất** giữa bốn suite chính; 138/150 query Generate xuất hiện trong Deterministic/Retrieval, Production là các query liên kết đã có. Đây là thiết kế đo nhiều tầng trên các câu liên quan, hữu ích để chẩn đoán nhưng không làm tăng số mẫu độc lập.

Phân bố cohort không đều: Deterministic 111 K51 / 18 K50 / 11 K48–K49; Generate 92 K51 / 31 K50 / 19 K48–K49 / 8 general. Không coi average này là tỷ lệ thành công theo traffic thật hoặc chất lượng bằng nhau giữa ba khóa.

## 3. Deterministic 140 — số liệu diagnostic, chưa đủ contract chính thức

### 3.1. Số liệu raw

| Metric | Raw |
| --- | ---: |
| Pass | 118/140 — 84,29% |
| Structured-vs-rest precision | 92,96% |
| Structured-vs-rest recall | 88,00% |
| F1 | 90,41% |
| False positive rate / false negative rate | 7,69% / 12,00% |
| Intent / strategy accuracy | 84,29% / 85,00% |
| Fallback correctness | 92,31% |
| LLM-call expectation accuracy | 89,29% |
| Router API success / cache hits / validation errors được ghi nhận | 140/140 / 0/140 / 0/140 |
| Latency p50 / p95 / max | 1,78 / 4,06 / 22,02 giây |

API/schema thành công không có nghĩa decision semantic đúng. Precision/recall ở đây là structured-vs-rest, không phải macro F1 của toàn bộ mode/intent.

| Nhóm | Raw pass |
| --- | ---: |
| Single structured | 52/60 — 86,67% |
| Compound | 25/28 — 89,29% |
| Capability boundary | 22/24 — 91,67% |
| Missing/ambiguous | 9/12 — 75,00% |
| Unsupported in-domain | 2/8 — 25,00% |
| OOD | 8/8 — 100% |
| Realistic / stress | 107/125 — 85,60% / 11/15 — 73,33% |

Review cũ phân loại 22 raw failure thành 14 system defects và 8 minor limitations; trong 8 minor có bốn trường hợp từ chối an toàn nhưng khác route kỳ vọng. Chúng vẫn là observation hữu ích, không chứng nhận bộ kiểm tra đầy đủ.

### 3.2. Phát hiện mới: evaluator không đọc đầy đủ contract v6

Đối chiếu **mã đúng tại harness commit `0499d63d`**:

1. CLI chọn `evaluate_deterministic_v2` chỉ khi `deterministic_contract.startswith("query-plan-")`.
2. Manifest không có trường đó; provenance raw ghi `deterministic_contract=null`. Vì vậy lượt chạy vào `evaluate_deterministic` legacy.
3. Case v6 khai báo `expected_plan` ở 140/140 case và `expected_tasks` ở 132/140 case. Evaluator legacy không kiểm tra hai contract này; nó chấm các group/strategy và các field assertion cũ.
4. Trong 140 case, số case có `expected_contains_any`, `expected_numeric_value`, `expected_item_count`, `expected_citation_content_type`, `expected_citation_cohort` đều bằng **0**.
5. Với field cũ bị thiếu, các check value/item-count/citation có thể mặc định pass. Vì vậy raw **100% structured_value_exactness**, **100% structured_item_count_accuracy**, **100% citation metadata/content type** và **0 deterministic cross-cohort leak** không chứng minh các khả năng tương ứng đã được test đầy đủ.
6. Provenance Deterministic còn ghi Qdrant/MongoDB **v31**, khác manifest và các lượt sau **v32**. Không tự sửa nhãn thành v32; cần log thực tế để phân biệt metadata stale với storage thật.

**Đính chính nhận định trước:** không gọi 118/140 là full architecture exactness đã được xác nhận. Giữ raw và failure review làm diagnostic/partial-contract evaluation; không tăng điểm hoặc xóa các failure. Đây là lỗi phép đo, không phải bằng chứng runtime vừa bị sửa hỏng.

Nếu muốn có metric architecture chính thức: sửa dispatch/contract và test evaluator để đọc đúng schema v6, kiểm tra assertion coverage, khóa v32. Tận dụng trace đã lưu nếu đủ; nếu thiếu phải xin chạy bổ sung có công bố rõ invalid prior run/harness correction. Không giả lập task trace còn thiếu, không thay gold theo output, không âm thầm gọi đó là lượt holdout đầu tiên. Hiện báo cáo này **không sửa hoặc chạy lại** phần đó.

## 4. Retrieval 160 — mạnh về tìm trúng, yếu hơn về đủ mọi nguồn

| Metric | Kết quả |
| --- | ---: |
| Hit@1 | 123/160 — 76,88% |
| Hit@3 | 151/160 — 94,38% |
| Hit@5 | 154/160 — 96,25% |
| Primary Hit@5 | 154/160 — 96,25% |
| MRR | 0,8585 |
| nDCG@5 | 0,8557 |
| Required-source recall@5 (macro) | 92,81% |
| Parent section match / citation binding | 96,25% / 96,25% |
| Content-type match | 156/160 — 97,50% |
| Empty retrieval / synthetic-leak flag | 4/160 / 4/160 |
| Cross-cohort leakage được quan sát | 0/160 |
| Latency p50 / p95 / max | 2,39 / 4,38 / 22,46 giây |

Đây là **end-to-end retrieval**, có ảnh hưởng của Planner, không phải chất lượng vector retriever thuần. Cờ synthetic/content-type bao gồm các case bị route sang structured/no RAG; không tự diễn giải là database bị nhiễm dữ liệu.

| Loại câu | Hit@5 | Required-source recall@5 trung bình |
| --- | ---: | ---: |
| Semantic | 93/96 — 96,88% | 96,88% |
| Exact article | 23/24 — 95,83% | 95,83% |
| Graph-linked | 24/24 — 100% | 91,67% |
| Multi-source | 14/16 — 87,50% | **65,63%** |

Theo cohort: general 8/8; K51 42/46; K50 52/53; K48–K49 52/53. Theo split: realistic 116/120; stress 38/40.

Sáu miss: hai ranking miss, bốn Planner/mode/task/scope miss theo failure taxonomy. Do đó thêm reranker chưa chắc sửa được nguyên nhân chính. Không cần rebuild dữ liệu chỉ vì metric chưa 100%.

**Lưu ý quan trọng:** tìm được một nguồn đúng không có nghĩa tìm đủ mọi nguồn. Required-source recall ở đây giới hạn top 5, chưa đồng nghĩa toàn bộ packet sau graph thiếu cùng tỷ lệ. Nhóm graph-linked 24/24 cũng không chứng minh graph đem lại improvement nhân quả; không có ablation trong lượt này.

Gate raw **fail** do content-type match 97,50% dưới ngưỡng 98%; các ngưỡng Hit/MRR/nDCG/cohort đều đạt. Vẫn có thể công bố metric thành phần trung thực, không gọi overall gate pass. Không quan sát leakage trong 160 case không phải bảo đảm 0% ngoài production.

## 5. Generate + Judge 150

### 5.1. Trạng thái output, không phải accuracy

- `answered`: 122/150 — 81,33%.
- `needs_clarification`: 10/150.
- `out_of_domain`: 15/150.
- `low_confidence` kèm lỗi retrieval: 3/150.
- Tổng trạng thái được evaluator coi là thành công: 147/150 — 98%.
- Generation latency p50/p95/max: 5,56 / 12,61 / 21,69 giây, đo local pipeline của lượt này, không trộn với client latency Production.

`success_rate=81,33%` trong file Generate chỉ đếm `answered`; `answer_success=98%` trong Judge còn chấp nhận clarification/OOD. Hai số khác định nghĩa, không chứng minh chất lượng tăng sau judge. Một câu answered vẫn có thể sai; một câu clarify/OOD vẫn có thể là hành vi đúng.

### 5.2. Rubric LLM Judge riêng

| Chiều chấm | Trung bình trên 150 |
| --- | ---: |
| Faithfulness | 0,9220 — 92,20% thang điểm |
| Answer relevancy | 0,9522 — 95,22% |
| Answer correctness | 0,9277 — 92,77% |
| Citation correctness | 0,9299 — 92,99% |
| Context precision | 0,4103 — 41,03% |
| Context recall | 0,7046 — 70,46% |
| Judge unsupported-claim flag | 8/150 — 5,33% |
| Judge critical-false-pass flag | 2/150 |

Đây là **điểm trung bình**, không phải 139/150 câu đúng hay xác suất đúng. Faithfulness đo bám evidence, không thay thế correctness với ground truth. Context scores trộn RAG, structured và guardrail không cần context; ví dụ OOD có context recall trung bình 0. Không kết luận từ 41,03% rằng 58,97% toàn bộ evidence runtime là sai.

| Nhóm | n | Faithfulness | Correctness | Citation |
| --- | ---: | ---: | ---: | ---: |
| RAG | 72 | 94,97% | 93,99% | 94,21% |
| Structured | 30 | 89,67% | 93,17% | 90,00% |
| Mixed | 18 | 92,06% | **83,78%** | 88,67% |
| Clarification | 10 | 98,00% | 85,00% | 91,00% |
| Unanswerable | 10 | 85,50% | 99,50% | 96,00% |
| OOD | 10 | 81,00% | 100,00% | 100,00% |

Đây là breakdown sau chạy để giải thích, không một benchmark mới. Correctness realistic 94,66% (n=117), stress 86,06% (n=33). Không cherry-pick nhóm dễ để thay headline đã định trước.

### 5.3. Các check tự động khác

| Check | Raw | Hạn chế |
| --- | ---: | --- |
| Required-fact hit | 99/150 — 66,00% | Tất cả fact phải match; paraphrase/gold dư chi tiết gây false negative |
| Numeric accuracy | 136/150 — 90,67% | Kiểm tra chuỗi số từ required facts xuất hiện trong answer; case không có số mặc định pass; không phải numeric reasoning accuracy |
| Abstention correct | 140/150 — 93,33% | Kết hợp status và phrase matching, có false negatives đã audit |
| Question handling correct | 140/150 — 93,33% | Composite heuristic, không thay thế review nội dung |
| Packet required-fact coverage | 69,67% | Matching proxy, không phải tỷ lệ fact đúng đã xác nhận |

Gate Judge raw **fail**: numeric dưới 95%, unsupported flag 5,33% vượt 5%, critical flags 2 vượt 1. Ngoài ra raw còn `human_audit_pending` vì được viết trước audit. Audit mới không tự làm các gate fail trở thành pass; cần kết quả tổng hợp riêng thay vì overwrite raw.

## 6. Audit 40 + automatic failures

Thang mỗi chiều: 0 / 0,5 / 1. Điểm tổng là trung bình correctness, completeness, faithfulness, citation, cohort. Phương pháp: **AI-assisted source-grounded review, owner-approved workflow**, không phải independent expert audit. Các file hiện vẫn ghi `completed_pending_user_approval`; không dùng tên cột `human_*` để suy ra đã có người chấm độc lập.

| Metric | 40 chọn trước | 60 mở rộng |
| --- | ---: | ---: |
| Điểm tổng | 96,25% | 91,50% |
| Correctness | 95,00% | 87,50% |
| Completeness | 92,50% | 83,33% |
| Faithfulness | 98,75% | 98,33% |
| Citation correctness | 95,00% | 88,33% |
| Cohort correctness | 100,00% | 100,00% |
| Pass sạch | 32/40 | 32/60 |
| Minor limitation | 2/40 | 5/60 |
| Evaluation/evaluator issue | 3/40 | 14/60 |
| Confirmed defect theo audit lưu | 3/40 | 9/60 |
| Critical false pass theo audit lưu | 1/40 | 2/60 |

60 là **failure-enriched sample**, không phải mẫu ngẫu nhiên. Không dùng 9/60 làm defect rate của traffic, không suy 9/150 là tất cả lỗi trong 150 vì 90 câu chưa được đối chiếu ở mức này. Cũng không dùng 96,25% composite score thành “96,25% câu trả lời hoàn toàn đúng”.

### Đính chính cách mô tả hai case severity high

`v6_ans_rag_009` và `v6_ans_mixed_011` hỏi quyền được thông báo thay đổi học vụ/học phí. Đọc output gốc cho thấy model nói **“nguồn hiện có chưa trực tiếp xác lập”**, không khẳng định chắc chắn sinh viên không có quyền.

Lỗi được chứng minh: đúng Điều 8 không vào packet, câu hỏi có đáp án bị trả thành chưa đủ căn cứ, rồi thêm các quy định gần chủ đề nhưng không trả target. Trong mixed case, phần TCF vẫn đúng. Vì vậy mô tả trước “phủ định sai quyền” quá mạnh; nên ghi **retrieval miss → false abstention / answer incompleteness và lệch trọng tâm**. Giữ severity/cờ raw để trace lịch sử, nhưng cần người hiểu nguồn xác nhận trước khi gọi là critical policy hallucination trong paper.

Các nhóm lỗi thật được audit hỗ trợ: thiếu nguồn/exact target/nguồn bổ trợ; structured directory routing/resolution miss; clarification/compound handling. Nhiều cờ automatic khác là lỗi matcher, gold quá chi tiết hoặc judge false positive. Không sửa runtime cho một false-positive evaluator.

## 7. Production 60

| Metric | Kết quả |
| --- | ---: |
| HTTP success | 60/60 |
| Payload không lỗi | 59/60 — 98,33% |
| Status khớp gold | 57/60 — 95,00% |
| HTTP 429 / client timeout | 0/60 / 0/60 |
| Client latency p50 / p95 / max | 6,64 / 16,27 / 47,28 giây |
| Streaming TTFT p95 | 13,32 giây, n=10 |
| Warm cache hit flag | 10/10 |
| Warm client latency p95 | 12,43 giây |
| Cold requests thực tế hit cache | 8/20 — cold protocol không hợp lệ |
| API telemetry coverage | 0/50 non-stream requests |

Scenario success: cold 20/20; structured 9/10; warm 10/10; streaming 10/10; burst 10/10. Realistic 47/48; stress 12/12, nhưng stress có case status sai nên không gọi 12/12 là content pass.

Hai failure nội dung/handling trùng nhóm đã biết: mượn micro và cohort conflict. Một mismatch status còn lại là từ chối danh sách cá nhân, chấp nhận về an toàn nhưng khác frozen status gold.

Lượt đầu 45/60 HTTP 429 do harness thiếu client identity đã giữ làm invalid diagnostic. Lượt sửa harness không còn 429, nhưng tám case thành công ở lượt đầu làm nóng cache trong lượt sau. Không công bố cold speedup từ lượt sau.

Gate Production **fail**, trong đó có ba vấn đề đo lường: cold contamination, API không trả debug telemetry, gate tìm scenario `deterministic` trong khi dataset dùng `structured`. Hai latency gate cũng chưa đạt (warm client p95, streaming TTFT p95).

Warm responses báo `llm_called=false`, server timer khoảng 0,23–1,11 giây nhưng client đo 1,81–18,36 giây. Chưa đủ log để quy chênh lệch cho mạng, proxy, queue hay phần ngoài timer backend. Không thay client latency bằng server latency để nâng điểm. Không có telemetry API không chứng minh LangSmith tắt; số default retry/context bằng 0 không phải đo được thật.

60 request không đo được uptime dài hạn, năng lực phục vụ tải lớn, privacy/security, failover đầy đủ hay an toàn chính sách. Không dùng 98,33% payload success thành 98,33% answer accuracy/availability SLO.

## 8. Có over-engineering hoặc overfitting không?

### Nhận định về kiến trúc

Luồng Planner → normalize/validate → thực thi structured/RAG → evidence packet → Composer → citation/stream có trách nhiệm riêng phù hợp với yêu cầu multi-intent, nhiều cohort và dữ liệu bảng. Không có bằng chứng trong v6 buộc phải bỏ các tầng này.

Các invariant nên giữ:

- Schema/validator bảo vệ task/slot/cohort hợp lệ; schema không kiểm tra được semantic applicability.
- Structured resolver trả giá trị xác định; Composer không tự đổi kết quả.
- Canonical citation identity bảo vệ link đúng document/cohort/article.
- Applicability guard và graph resolver không đoán đích khi mơ hồ.
- Budget/dedupe ngăn packet không kiểm soát; không mặc định rank 1 là authority.
- Giới hạn retry/capacity/health có ích cho dịch vụ.

Không nên kết luận “không over-engineering” chỉ vì test pass, hoặc “bị overfit” chỉ vì holdout fail. Kiến trúc hợp lý vẫn có model/routing/data-coverage failures. Không có phép so sánh kiểm soát để quy chất lượng tốt/xấu cho riêng việc đổi Qwen 3.8; không cần mở lại A/B chỉ để hoàn thành CV.

### Nơi đang có complexity đáng giảm

Bằng chứng rõ nhất là **evaluation plumbing**: hai nhánh deterministic contract, tên field/gate lệch dataset, snapshot audit pending, nhiều metric có cùng tên “success” nhưng khác ý nghĩa. Nên chuẩn hóa một contract đang dùng, tên metric và báo cáo applicability/N/A; không xây framework mới hay thêm một tầng judge nữa.

Với runtime, chưa thực hiện full-code/dead-code/security audit trong lượt này; không kết luận mọi helper hiện tại đều cần thiết hoặc mọi dòng đều sạch. Refactor nên theo call path thực tế và characterization tests, không xóa một guard chỉ vì model mới tuân schema tốt hơn.

### Khi nào sửa là tổng quát, không vá case?

Một thay đổi chấp nhận được phải: có trace xác định tầng lỗi; sửa một invariant đã có; dùng metadata/schema thay vì tên case/từ khóa; có test dương/âm và domain khác; giữ fail-closed khi thiếu căn cứ; có giới hạn scope/diff. Failure v6 trở thành regression/dev sau khi dùng để thiết kế fix.

Không nên làm: keyword `micro → phòng X`, `Điều 8 → luôn thêm nguồn`, thêm ví dụ từng case vào prompt, ép mọi câu ngoại ngữ vào một route, tăng toàn bộ top-k/budget, thêm LLM verification loop chỉ để điểm tăng. “Chỉ thêm hai câu prompt” vẫn có thể overfit nếu hai câu đó mã hóa benchmark.

## 9. Ưu tiên sửa tối thiểu

| Việc | Trước CV/beta | Trước dịch vụ chính sách đáng tin cậy hơn | Hướng tối thiểu |
| --- | --- | --- | --- |
| Sửa nhãn/giới hạn metric và đính chính Deterministic | Bắt buộc | Bắt buộc | Báo cáo đúng phép đo; không sửa raw |
| Đo đủ contract Deterministic | Chỉ cần nếu muốn công bố metric này | Nên hoàn tất | Dispatch đúng schema; assertion coverage; storage identity; test harness |
| False abstention khi có nguồn đúng | Ghi known limitation được | Ưu tiên cao | Trace query/target → candidates → packet; sửa đúng tầng gây bỏ nguồn, không prompt thay retrieval |
| Cohort conflict bị tự chọn | Không quảng bá hỗ trợ case này hoàn hảo | Ưu tiên cao | Xung đột đã nhận diện phải clarify, không tự chọn một scope; không thêm năm/khóa đặc biệt |
| Structured service/directory misses | Có thể backlog | Ưu tiên vừa | Xác minh capability mapping/slot canonicalization/execution, không hard-code câu |
| Multi-source completeness / graph support | Có thể backlog | Ưu tiên cao cho câu nhiều ý | Phân biệt missing candidate, missing packet và Composer bỏ ý trước khi sửa |
| Warm latency / streaming TTFT | Công bố số đo thật | Cần đo theo SLO sản phẩm | So timing client/server; không tăng model/budget theo cảm giác |
| Over-clarify, OOD-vs-abstain wording, thiếu chi tiết phụ | Backlog | Theo impact | Không đổi kiến trúc chỉ vì nhãn evaluator khác |
| Thêm reranker, model A/B, agent, RAGAS, framework eval mới | Không cần | Chưa có bằng chứng cần | Không mở rộng scope |

Sửa một bug thật rồi kiểm tra bằng v6-regression là hợp lý; không được gọi điểm sau sửa trên cùng các câu đã phân tích là clean holdout accuracy. Một lượt trước sai harness được phép có bản sửa công khai, nhưng không xóa lịch sử hoặc trộn các lượt thành one-shot đẹp hơn.

## 10. Có thể chốt gì ngay?

| Mục tiêu | Kết luận |
| --- | --- |
| Portfolio/CV, demo beta | **Có.** Kiến trúc và triển khai có giá trị; dùng Retrieval metric có phạm vi rõ, tự khai limitation |
| Chốt mọi metric là official/no caveats | **Chưa.** Deterministic sai contract; audit chưa độc lập; Production cold/telemetry hạn chế |
| Bắt đầu đọc source | **Ngay bây giờ.** Không cần đợi sửa hoàn hảo |
| Refactor cho dễ đọc | **Có, trên nhánh/commit riêng**, giữ hành vi và tests; không vừa sửa semantic vừa gọi refactor thuần |
| Chuẩn bị paper | **Có thể viết system/methodology/error analysis.** Chưa đủ kết luận phương pháp tốt hơn baseline hay model tốt hơn; audit cần mô tả đúng vai trò AI/người |
| Production pilot hỗ trợ tra cứu, có link nguồn | **Có điều kiện:** phạm vi rõ, hạn chế case chưa đáng tin, người dùng kiểm chứng nguồn và kênh phản hồi |
| Production làm nguồn quyết định chính sách chính thức | **Chưa nên tuyên bố đạt.** Cần xử lý/giới hạn failure ảnh hưởng scope và evidence completeness, cùng kiểm tra vận hành/an toàn riêng |

Không cần ép dự án đạt 100% để có giá trị CV. Nhưng hoàn thành portfolio không tự động bằng production sign-off hay scientific validation.

### Metric nên/không nên đưa CV lúc này

Nên dùng: “Achieved **96.25% Hit@5 (154/160)** on a frozen end-to-end retrieval evaluation, with **no observed cross-cohort leakage in that set**.” Có thể thêm MRR 0,859 nếu còn chỗ.

Nếu đưa judge, ghi “custom LLM-as-judge evaluation on 150 queries; mean faithfulness **0.922/1**”, không “92.2% verified correct answers”. CV ngắn không bắt buộc nhồi mọi metric.

Tạm không dùng: 118/140 như full architecture exactness; 100% structured value/citation; “human-evaluated faithfulness 98.75%” không giải thích AI-assisted; 98.33% như accuracy; cold latency/speedup; RAGAS scores đã bỏ; số cũ v4/v5 gắn sang Qwen 3.8.

## 11. Kế hoạch kết thúc hữu hạn

1. Dùng báo cáo này làm snapshot v6 có caveat, giữ raw/history. Chọn metric có căn cứ để cập nhật README/CV trong một thay đổi tài liệu riêng.
2. Chốt mốc beta/portfolio; không mở vòng “fix đến 100%”. Bắt đầu đọc source trước khi refactor.
3. Nếu cần headline architecture: chỉ sửa evaluator/contract trước, không sửa runtime cùng lượt; công bố đúng trạng thái invalid prior run và dữ liệu đã được xem.
4. Refactor từng khu vực: API → Planner/normalizer → executor → retrieval/structured → packet/Composer → citations/stream. Dùng fixture/characterization tests và regression cũ; lưu version runtime đã đo để metric không trôi theo code mới.
5. Trước mở rộng production, xử lý một danh sách hữu hạn gồm scope conflict, missing evidence của câu answerable/multi-source và latency theo trace. Nếu fix tối giản không đủ, chọn giới hạn hỗ trợ/abstain thay vì mặc định thêm subsystem.
6. Paper là giai đoạn riêng: câu hỏi nghiên cứu, baseline phù hợp, protocol đo chính xác và đánh giá con người minh bạch. Không cần làm ngay để hoàn thành CV; không claim gain từ graph/model khi chưa đo đối chứng.

Trong lần tổng hợp này chỉ thêm báo cáo, **không sửa prompt, Planner, retrieval, graph, database, UI, evaluator hoặc dataset; không commit/push/deploy hay chạy lại bất kỳ suite nào**.

## 12. Bằng chứng gốc

- [Manifest v6](</C:/Users/A Fee/Desktop/Workspace/student_handbook_rag/data/eval/architecture_v6_holdout/manifest.json>)
- [Deterministic raw](</C:/Users/A Fee/Desktop/Workspace/student_handbook_rag/work/v6_official_0499d63d_run01/deterministic_full.json>) và [review cũ](</C:/Users/A Fee/Desktop/Workspace/student_handbook_rag/work/v6_official_0499d63d_run01/deterministic_failure_review.md>) — giới hạn evaluator được đính chính tại mục 3 của báo cáo này.
- [Retrieval raw](</C:/Users/A Fee/Desktop/Workspace/student_handbook_rag/work/v6_retrieval_official_a013cdc8_run01/retrieval_end_to_end_qdrant_vector_primary_graph_supplement_full.json>) và [failure taxonomy](</C:/Users/A Fee/Desktop/Workspace/student_handbook_rag/work/v6_retrieval_official_a013cdc8_run01/retrieval_failure_taxonomy.md>)
- [Generate raw](</C:/Users/A Fee/Desktop/Workspace/student_handbook_rag/work/v6_answer_official_a013cdc8_run01/answer_generation_full.json>) và [Judge raw](</C:/Users/A Fee/Desktop/Workspace/student_handbook_rag/work/v6_answer_official_a013cdc8_run01/generated_answer_judge_full.json>)
- [Audit 60](</C:/Users/A Fee/Desktop/Workspace/student_handbook_rag/work/v6_answer_official_a013cdc8_run01/human_audit_60_report.md>) và [audit 40 đã chọn trước](</C:/Users/A Fee/Desktop/Workspace/student_handbook_rag/work/v6_answer_official_a013cdc8_run01/human_audit_40_official.json>)
- [Production audit](</C:/Users/A Fee/Desktop/Workspace/student_handbook_rag/work/v6_production_official_845b481d_run01/PRODUCTION_AUDIT_VI.md>)
- Evaluator: [suites.py](</C:/Users/A Fee/Desktop/Workspace/student_handbook_rag/src/evaluation/suites.py>), [evaluate_system.py](</C:/Users/A Fee/Desktop/Workspace/student_handbook_rag/scripts/evaluate_system.py>); phần dispatch đã được đối chiếu thêm bằng `git show 0499d63d:scripts/evaluate_system.py`.
