# Báo cáo đánh giá release V7

## 1. Mục đích và phạm vi công bố

Tài liệu này chốt kết quả đánh giá cho phiên bản hệ thống sử dụng Qwen 3.8-27B làm Planner và Gemini 3.1 Flash-Lite làm Composer. Mỗi bộ đo một tầng khác nhau nên không cộng các mẫu hoặc trung bình các metric thành một “điểm tổng hệ thống”.

V7 được chạy đúng một lượt đầy đủ trên runtime commit `1f11f6500bc56de861adaecc876ccd9505d93538`. Sau khi xem kết quả:

- không sửa runtime rồi chạy lại V7 để nâng điểm;
- không sửa câu hỏi, ground truth, source target hoặc threshold;
- bốn hash dataset hiện tại vẫn trùng với provenance của lượt chạy đầu;
- mọi failure và gate không đạt đều được giữ lại trong báo cáo.

Vì vậy V7 được dùng làm **official internal release evaluation** của dự án và có thể hỗ trợ các claim ghi đúng phạm vi trong CV. Đây không phải benchmark bên ngoài được đăng ký trước. Nếu dùng cho bài báo, cần mô tả đúng cách khóa hash sau lượt chạy và nên bổ sung tập prospectively frozen hoặc external benchmark cùng đánh giá độc lập của con người.

## 2. Danh tính hệ thống được đánh giá

| Thành phần | Giá trị |
|---|---|
| Runtime commit | `1f11f6500bc56de861adaecc876ccd9505d93538` |
| Evaluator commit | `c053bfcf8a63cc85a3448b1c3691310798319c11` |
| Dataset | Architecture V7 `7.0.0` |
| Planner | `qwen/qwen3.8-27b` |
| Reasoning effort | `low` |
| Planner output | Native JSON Schema, schema `v1` |
| QueryPlan normalizer | `v17-registry-literal-grounding` |
| Router prompt | `structured-regulation-v38-directory-task-contract` |
| Composer | `gemini-3.1-flash-lite` |
| Answer prompt | `student-handbook-answer-v3.22-answer-scope` |
| Pipeline | `v58-registry-grounded-routing` |
| Judge | `openai/gpt-oss-120b`, rubric riêng của dự án |
| Retrieval mode | `vector_primary_graph_supplement` |
| Reranker | Tắt; không dùng PhoRanker |
| Qdrant | `student_handbook_semantic_v32` |
| MongoDB | `parent_docs_v32` |
| Parent docstore hash | `4d410553cfaddeaef51fc096ffd0025d52e585b4c5dfe7ee0807e73570648143` |

### Hash của bốn bộ case

| Suite | SHA-256 |
|---|---|
| Deterministic | `6daa4f4be0e5a1426e11b9106d5ee64e34f4a37ea8ffabe42ea1adae7d329941` |
| Retrieval | `d9511afa0cce9ca1c8e02c24f2c79803c43e38625ddf1cb5e36d84aded18ccd2` |
| Generate + Judge | `5da5f17eaac5c208eb7ccee5b25d8f17713f1ab081a4124f2588bf1bb6532f15` |
| Production | `ad47bf0c0e7782803750692a8b32e440949c6f26466c850d01514d5cfe457f0f` |

## 3. Deterministic Architecture — 140 case

### Mục tiêu

Bộ này kiểm tra kết quả kiến trúc trước khi dùng Composer để đánh giá chính nó:

- QueryPlan có chọn đúng hướng structured, RAG, clarification hoặc OOD không;
- số task và ý nghĩa từng task có phù hợp không;
- structured lookup có thực thi và trả evidence hợp lệ không;
- planner có fallback không;
- evidence có chảy sai cohort không.

Contract V7 chấp nhận nhiều kế hoạch tương đương về kết quả an toàn. Nó không ép task ID, thứ tự task hoặc cách viết raw slot phải giống tuyệt đối với một đáp án duy nhất.

### Phân bố và kết quả

| Nhóm | Số case | Pass | Tỷ lệ |
|---|---:|---:|---:|
| Single structured | 60 | 58 | 96,67% |
| Capability boundary | 24 | 24 | 100,00% |
| Compound | 28 | 24 | 85,71% |
| Missing/ambiguous | 12 | 11 | 91,67% |
| Unsupported in-domain | 8 | 5 | 62,50% |
| Out-of-domain | 8 | 8 | 100,00% |
| **Tổng** | **140** | **130** | **92,86%** |

Theo độ thực tế:

| Split | Số case | Pass | Tỷ lệ |
|---|---:|---:|---:|
| Realistic | 95 | 92 | 96,84% |
| Stress | 45 | 38 | 84,44% |

### Metric chi tiết

| Metric | Kết quả |
|---|---:|
| Outcome-contract accuracy | 92,86% |
| Structured-selection precision | 98,86% |
| Structured-selection recall | 98,86% |
| False-positive rate | 1,92% |
| Plan-structure accuracy | 96,43% |
| Task-semantics accuracy | 95,71% |
| Structured-execution accuracy | 97,86% |
| Structured-evidence accuracy | 98,86% |
| Planner fallback rate | 2,14% |
| Cross-cohort leak quan sát được | 0/140 |

Gate deterministic đạt. Các assertion không được contract áp dụng cho toàn bộ 140 case được ghi `N/A`, không mặc định thành 100%.

## 4. End-to-End Regulation Retrieval — 160 case

### Mục tiêu

Bộ này chỉ chứa câu cần evidence quy định. Mỗi case chạy qua Planner và pipeline production:

1. dense retrieval bằng BGE-M3;
2. BM25 lexical retrieval;
3. RRF fusion;
4. group child chunk theo parent;
5. giới hạn primary parents;
6. tạo graph-related references cho UI.

Structured-only query không nằm trong bộ Retrieval vì các bảng dùng deterministic catalog path.

### Phân bố

| Dimension | Phân bố |
|---|---|
| Split | 108 realistic, 52 stress |
| Cohort | 46 K48–K49, 55 K50, 47 K51, 12 general |
| Tags tiêu biểu | 30 exact article, 20 graph reference, 20 multi-source, 32 cohort-sensitive, 32 condition/procedure, 10 typo không dấu |

### Metric tổng

| Metric | Kết quả |
|---|---:|
| Hit@1 | 126/160 — 78,75% |
| Hit@3 | 145/160 — 90,63% |
| Hit@5 | 148/160 — 92,50% |
| Primary Hit@5 | 148/160 — 92,50% |
| MRR | 0,8559 |
| nDCG@5 | 0,8248 |
| Required-source recall@5 | 0,8802 |
| Citation binding | 93,75% |
| Content-type match | 94,38% |
| Cohort match | 100,00% |
| Cohort leak quan sát được | 0/160 |
| Empty retrieval | 4/160 — 2,50% |
| Latency p50 | 2,674 giây |
| Latency p95 | 5,163 giây |

### Breakdown quan trọng

| Nhóm | N | Hit@3 | MRR | nDCG@5 nếu có |
|---|---:|---:|---:|---:|
| Realistic | 108 | 93,52% | 0,8834 | 0,8698 |
| Stress | 52 | 84,62% | 0,7987 | 0,7314 |
| Exact article | 30 | 100,00% | 0,9278 | — |
| Graph reference | 20 | 95,00% | 0,9250 | — |
| Multi-source | 20 | 80,00% | 0,7500 | — |
| Cohort-sensitive | 32 | 78,13% | 0,7252 | — |
| Typo không dấu | 10 | 50,00% | 0,3833 | — |

Các gate Hit@3, Hit@5, MRR, nDCG@5 và cohort leak đều đạt. Overall gate fail vì `content_type_match=94,38%` thấp hơn threshold 98%. Không dùng Hit@5 để che failure này.

## 5. Generate — 150 case

### Phân bố

| Loại answer | Số case |
|---|---:|
| Regulation RAG | 90 |
| Structured | 30 |
| Mixed | 10 |
| Clarification | 8 |
| Unanswerable | 6 |
| OOD | 6 |
| **Tổng** | **150** |

Phân bố gồm 102 realistic và 48 stress. Toàn bộ 150 output dùng retrieval production và không dùng PhoRanker.

| Metric Generate | Kết quả |
|---|---:|
| Literal `answered` status | 88,00% |
| Latency mean | 6,250 giây |
| Latency p50 | 5,517 giây |
| Latency p95 | 10,685 giây |
| Max | 84,847 giây |

`answered=88%` không phải accuracy: clarification, OOD và abstention hợp lệ có thể dùng status khác.

## 6. LLM Judge — 150 case

Judge là `openai/gpt-oss-120b` với rubric riêng. Đây không phải RAGAS và không phải human evaluation độc lập.

| Metric | Kết quả |
|---|---:|
| Faithfulness | 92,65% |
| Answer relevancy | 93,91% |
| Answer correctness | 88,30% |
| Citation correctness | 94,25% |
| Context precision | 50,10% |
| Context recall | 79,93% |
| Packet required-fact coverage | 82,67% |
| Exact required-fact hit | 51,33% |
| Numeric accuracy | 81,33% |
| Abstention correct | 97,33% |
| Question handling correct | 98,00% |
| Unsupported-claim flag | 8,67% |
| Critical-false-pass flag | 2/150 |

Gate faithfulness, answer correctness, citation correctness và abstention đạt. Gate numeric accuracy, unsupported-claim rate và critical false pass không đạt.

Exact required-fact hit sử dụng matching hẹp nên có thể không nhận một paraphrase đúng; vì vậy nó được báo riêng, không thay bằng Judge correctness hoặc human audit.

### Trung bình theo answer type

| Loại | N | Faithfulness | Relevancy | Correctness | Citation |
|---|---:|---:|---:|---:|---:|
| Regulation RAG | 90 | 89,21% | 90,32% | 82,76% | 91,41% |
| Structured | 30 | 100,00% | 100,00% | 94,27% | 99,33% |
| Mixed | 10 | 97,30% | 98,80% | 97,90% | 97,00% |
| Clarification | 8 | 88,75% | 98,75% | 98,75% | 96,25% |
| Unanswerable | 6 | 99,17% | 96,67% | 100,00% | 98,33% |
| OOD | 6 | 98,33% | 100,00% | 100,00% | 100,00% |

## 7. Source-grounded audit

Audit gồm:

- 40 case stratified đã xác định trước;
- review toàn bộ 14 case bị Judge gắn cờ;
- đối chiếu query, final answer, authorized evidence, cohort và gold scope.

Đây là AI-assisted source-grounded review trong workflow được chủ dự án phê duyệt, không phải đánh giá mù của chuyên gia độc lập.

| Dimension | Kết quả |
|---|---:|
| Overall | 96,06% |
| Correctness | 93,23% |
| Faithfulness | 98,38% |
| Completeness | 94,63% |
| Citation quality | 97,38% |
| Safe behavior | 99,50% |
| Judge–audit MAE | 0,0333 |
| Agreement trong ±0,15 | 95,00% |

Phân loại 40 case:

| Nhãn | Số case |
|---|---:|
| Pass | 32 |
| Acceptable minor limitation | 4 |
| Evaluation case issue | 3 |
| Confirmed system defect | 1 |

Một confirmed defect là `v7_ans_struct_020`: câu stress về điểm K51 chứa đồng thời tín hiệu “học phần còn lại”, D+ và câu hỏi “đạt hay không đạt”. Planner chọn sai bảng học phần không phân mức; Composer trung thành với evidence sai loại nên trả P/Đạt thay vì D+/Không đạt. Các probe tự nhiên sau đó cho thấy câu threshold thông thường vẫn được phân nhánh có điều kiện đúng. Dự án giữ nguyên failure và không vá prompt/normalizer sau evaluation.

Trong 14 Judge flags, review tìm thấy hai answer có unsupported expansion thực tế, nhưng cả hai đi cùng target/gold ambiguity của evaluation case. Judge cũng tạo nhiều false positive khi một chi tiết có citation hợp lệ nhưng rộng hơn required fact.

## 8. Production — 60 request

### Phân bố và latency

| Scenario | N | Success | p50 | p95 |
|---|---:|---:|---:|---:|
| Cold RAG | 20 | 100% | 5,533 s | 21,015 s |
| Structured | 10 | 100% | 3,648 s | 5,715 s |
| Warm cache | 10 | 100% | 1,980 s | 6,751 s |
| Streaming | 10 | 100% | 5,511 s | 6,745 s |
| Burst | 10 | 100% | 9,382 s | 13,542 s |
| **Tổng** | **60** | **100%** | **5,445 s** | **12,478 s** |

### Contract metrics

| Metric | Kết quả |
|---|---:|
| Transport success | 60/60 |
| Payload success | 60/60 |
| Response status accuracy | 60/60 |
| HTTP 429 | 0/60 |
| Timeout | 0/60 |
| Warm cache hit | 100% |
| Cold cache hit | 0% |
| Streaming TTFT coverage | 100% |
| Streaming TTFT p50 | 4,586 giây |
| Streaming TTFT p95 | 5,811 giây |
| Mean source count | 4,12 |
| Source utilization | 76,67% |

Overall production gate fail vì public endpoint không cung cấp internal debug telemetry (`telemetry_coverage=0%`) và warm-cache p95 vượt target 2 giây. Gate availability, cache protocol, RAG p95 và streaming TTFT đạt. Đây là bounded smoke/load test, không phải capacity, security hoặc traffic benchmark.

## 9. Kết luận chốt release

### Có thể công bố

- Deterministic outcome contract: **130/140 — 92,86%**.
- Structured selection precision/recall: **98,86% / 98,86%**.
- End-to-end retrieval Hit@5: **148/160 — 92,50%**; MRR **0,8559**; không quan sát cross-cohort leak trong 160 case.
- LLM-as-judge: faithfulness **92,65%**, relevancy **93,91%**, correctness **88,30%**, citation correctness **94,25%** trên 150 case.
- AI-assisted source-grounded audit: overall **96,06%** trên 40 case, với 1 confirmed system defect được giữ lại.
- Production contract: transport/payload/status **60/60**, streaming TTFT p95 **5,811 giây**.

### Không nên công bố theo cách sau

- Không gọi 530 phép đo là 530 câu hỏi độc lập hoặc cộng chúng thành một accuracy chung.
- Không gọi Judge là human evaluation hoặc RAGAS.
- Không tuyên bố 0% hallucination; raw Judge flag là 8,67% và review flags tìm thấy hai unsupported expansions trong case mơ hồ.
- Không tuyên bố mọi gate đều pass; Retrieval, Judge và Production còn gate fail đã nêu.
- Không gọi V7 là pre-registered external holdout.

### Đánh giá hoàn thành

Hệ thống đủ điều kiện chốt làm một production-oriented portfolio project: kiến trúc có phân tầng rõ, retrieval và cohort isolation có bằng chứng, structured path hoạt động tốt, API chạy ổn trong bounded test và các limitation được công bố minh bạch. Những failure còn lại nên chuyển thành regression/backlog của phiên bản sau thay vì tiếp tục sửa và chạy lại V7 để tìm 100%.
