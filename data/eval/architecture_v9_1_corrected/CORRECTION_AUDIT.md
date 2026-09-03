# V9.1 evaluation correction audit

V9.1 changes only evaluation eligibility and evaluator semantics. Runtime and frozen outputs are unchanged.

## Retrieval exclusions

| ID | Reason |
|---|---|
| `v8_ret_047` | Tiêu đề Điều 1 dùng chung; query không xác định văn bản K51. |
| `v8_ret_051` | Tiêu đề Điều 1 dùng chung; query không xác định văn bản K50. |
| `v8_ret_118` | Tiêu đề Điều 1 dùng chung; query không xác định Nghị định/văn bản. |
| `v8_ret_141` | Query nói hai việc nhưng liệt kê ba target; gold không bao phủ target thứ ba. |
| `v8_ret_151` | Hai tiêu đề chung không xác định hai văn bản mà gold ngầm chọn. |

## Answer exclusions

| ID | Reason |
|---|---|
| `v8_ans_rag_005` | Query không xác định văn bản K51 nhưng gold chọn riêng một Điều 1. |
| `v8_ans_rag_009` | Query không xác định văn bản K50 nhưng gold chọn riêng một Điều 1. |
| `v8_ans_rag_057` | Tên mục chung không xác định văn bản cố vấn học tập. |
| `v8_ans_rag_069` | Query CVHT/BCS không xác định văn bản ngoại trú mà gold ngầm chọn. |
| `v8_ans_rag_085` | Gold ghép nội dung khen thưởng NCKH ngoài phạm vi query học bổng. |
| `v8_ans_rag_086` | Gold ghép hiệu lực văn bản ngoài phạm vi query về đơn vị. |
| `v8_ans_rag_088` | Gold ghép nghỉ học tạm thời ngoài phạm vi query tổ chức quản lý. |
| `v8_ans_rag_089` | Gold ghép thời gian làm việc ngoài phạm vi mục ứng xử được hỏi. |
| `v8_ans_rag_090` | Gold ghép trách nhiệm quản lý ngoài phạm vi mục ứng xử được hỏi. |

## Evaluator corrections

- Metrics with no applicable assertion are reported as `N/A` and excluded from their denominator.
- Numeric accuracy uses only explicit `numeric_assertions`; numbers embedded in prose gold are not silently treated as assertions.
- Citation exact match is `N/A` when a case declares no expected citation IDs.
- Safe missing-data language counts as abstention even when transport status remains `answered`.
