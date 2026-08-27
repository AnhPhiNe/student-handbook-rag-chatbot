from __future__ import annotations

import json
from typing import Any

from src.common.legal_reference import article_label_from_heading, normalize_article_label

from .amendment_precedence import (
    ApplicableAmendment,
    collect_applicable_amendments,
    strip_misattached_amendment_notes,
)
from .context_allocation import ContextAllocationConfig


DEFAULT_MAX_CONTEXT_CHARS = 160000
ANSWER_PROMPT_VERSION = "student-handbook-answer-v3.4-direct-predicate-grounding"


def build_answer_prompt(
    query: str,
    retrieval_result: dict[str, Any],
    selected_citations: list[dict[str, Any]] | None = None,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    cohort: str | None = None,
    context_allocation: ContextAllocationConfig | dict[str, Any] | None = None,
) -> str:
    """Build a compact, task-bound answer prompt."""
    del context_allocation  # Kept in the public signature for compatibility.
    packet = build_authorized_evidence_packet(
        query=query,
        retrieval_result=retrieval_result,
        selected_citations=selected_citations,
        fallback_cohort=cohort,
        max_context_chars=max_context_chars,
    )
    required_units = [
        {
            "task_id": unit["task_id"],
            "question": unit["question"],
            "cohort": unit["cohort"],
            "coverage": unit["coverage"],
            "clarification_question": unit.get("clarification_question"),
            "allowed_source_refs": unit["allowed_source_refs"],
        }
        for unit in packet["units"]
    ]

    return f"""Bạn là chatbot tra cứu Sổ tay sinh viên. Trả lời bằng tiếng Việt tự nhiên, rõ ràng, đủ ý và chính xác; không tự ý rút gọn đến mức gây hiểu lầm.

QUY TẮC BẮT BUỘC
1. Trả lời đủ từng đơn vị yêu cầu và mọi ý độc lập trong câu hỏi của đơn vị đó.
2. Mỗi đơn vị chỉ được dùng evidence và source_ref đã cấp cho đúng task/cohort; không mượn nguồn của đơn vị khác.
3. Chỉ kết luận điều mà nguồn trực tiếp xác lập cho đúng đối tượng, hành vi hoặc điều kiện được hỏi. Không dùng điều kiện của một hậu quả, thủ tục hoặc khái niệm gần nghĩa để trả lời cho điều khác.
4. Nếu nguồn phân biệt nhiều hình thức đào tạo, đối tượng hoặc trường hợp mà câu hỏi chưa chỉ rõ, trình bày riêng mọi nhánh có evidence trực tiếp; không âm thầm chọn một nhánh đại diện.
5. Giữ đầy đủ điều kiện và ngoại lệ. Không lấy điều kiện của một nhánh để phủ định hoặc khẳng định tuyệt đối cho các nhánh còn lại.
6. Không suy ra một điều kiện đã hoặc chưa được đáp ứng chỉ từ nhãn chung như năm học, khóa hay hình thức đào tạo. Khi nguồn yêu cầu một mốc hoặc trạng thái cụ thể mà câu hỏi chưa xác lập, hãy nêu kết luận theo điều kiện hoặc yêu cầu làm rõ.
7. Khi primary evidence có article_label, nêu đúng article_label tại phần kết luận mà nguồn đó trực tiếp hỗ trợ. Không tự tạo Điều/khoản/điểm và không liệt kê các nguồn không được dùng để trả lời.
8. Với câu hỏi có/không về một hành vi hoặc vật cụ thể: nếu nguồn chỉ nêu tiêu chí định tính chung mà không trực tiếp gọi tên hoặc định nghĩa trường hợp được hỏi, chỉ nêu tiêu chí và nói rõ Sổ tay không kết luận trực tiếp cho trường hợp đó; không tự biến việc diễn giải tiêu chí thành lệnh cấm hoặc cho phép.
9. Nếu evidence chỉ gần chủ đề hoặc không đủ cho một phần, hãy nói rõ phần đó chưa tìm thấy căn cứ; trả lời partial hoặc abstain, không đổi câu hỏi sang khái niệm gần nghĩa.

QUY CÁCH
- Không dùng kiến thức ngoài AUTHORIZED_EVIDENCE_BY_UNIT.
- Không chèn mã nguồn như [S1] vào câu trả lời; giao diện hiển thị nguồn riêng.
- Dùng Markdown có chọn lọc: in đậm kết luận chính, số liệu, thời hạn và điều kiện quan trọng; dùng danh sách khi có nhiều bước, điều kiện hoặc trường hợp. Không in đậm cả đoạn.
- Với coverage=needs_clarification, chỉ nêu clarification_question của đơn vị đó.
- Với coverage=uncovered hoặc không có source_ref được phép, nói chưa tìm thấy căn cứ cho đúng ý đó.
- Nếu có applicable_amendments, áp dụng nội dung mới nhất trong đúng phạm vi nhưng không nhắc nhãn kỹ thuật amendment.
- Không hiển thị quá trình suy luận, metadata kỹ thuật hoặc tự tạo mục nguồn.

AUTHORIZED_EVIDENCE_BY_UNIT
{_to_pretty_json(packet)}

FINAL_INSTRUCTIONS
Câu hỏi gốc: {query}

Các đơn vị bắt buộc phải xử lý theo đúng thứ tự:
{_to_pretty_json(required_units)}

Chỉ xuất câu trả lời cuối cùng cho sinh viên."""


def build_authorized_evidence_packet(
    *,
    query: str,
    retrieval_result: dict[str, Any],
    selected_citations: list[dict[str, Any]] | None,
    fallback_cohort: str | None,
    max_context_chars: int,
) -> dict[str, Any]:
    """Group already-authorized primary evidence by logical task and cohort."""
    citations = _resolve_primary_citations(retrieval_result, selected_citations)
    sources = [_normalize_source(citation, index) for index, citation in enumerate(citations, 1)]
    sources = [source for source in sources if source["content"]]
    units = _composition_units(
        retrieval_result,
        fallback_cohort=fallback_cohort,
        fallback_question=query,
    )
    per_source_chars = _source_content_budget(
        max_context_chars=max_context_chars,
        source_count=max(1, len(sources)),
    )

    packet_units: list[dict[str, Any]] = []
    for unit in units:
        authorized_sources = [
            _source_for_unit(source, unit, per_source_chars)
            for source in sources
            if _source_supports_unit(source, unit)
        ]
        amendments = collect_applicable_amendments(
            retrieval_result,
            query=unit["question"],
            cohort=None if unit["cohort"] == "default" else unit["cohort"],
        )
        packet_units.append(
            {
                **unit,
                "allowed_source_refs": [source["source_ref"] for source in authorized_sources],
                "primary_evidence": authorized_sources,
                "applicable_amendments": [
                    _amendment_evidence(amendment)
                    for amendment in amendments
                ],
            }
        )

    return {"answer_prompt_version": ANSWER_PROMPT_VERSION, "units": packet_units}


def _amendment_evidence(amendment: ApplicableAmendment) -> dict[str, Any]:
    amendment_source = amendment.source_document_id
    if amendment.source_locator:
        locator_contains_document = bool(
            amendment_source
            and amendment.source_document_id.casefold()
            in amendment.source_locator.casefold()
        )
        if locator_contains_document or not amendment_source:
            amendment_source = amendment.source_locator
        else:
            amendment_source = f"{amendment_source} — {amendment.source_locator}"
    citation_source = (
        amendment.source_handbook_title
        or amendment.source_handbook_id
        or amendment.source_title
    )
    return {
        "amendment_source": amendment_source,
        "citation_source": citation_source,
        "citation_pages": list(amendment.source_pages),
        "effective_rule": amendment.effective_rule,
        "replacement_text": amendment.replacement_text,
    }


def build_prompt(
    query: str,
    retrieval_result: dict[str, Any],
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    cohort: str | None = None,
    context_allocation: ContextAllocationConfig | dict[str, Any] | None = None,
) -> str:
    return build_answer_prompt(
        query=query,
        retrieval_result=retrieval_result,
        selected_citations=retrieval_result.get("citations"),
        max_context_chars=max_context_chars,
        cohort=cohort,
        context_allocation=context_allocation,
    )


def limit_context(context: str, max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS) -> str:
    context = (context or "").strip()
    if len(context) <= max_context_chars:
        return context
    return context[:max_context_chars].rstrip() + "\n\n[Evidence đã được rút gọn.]"


def _resolve_primary_citations(
    retrieval_result: dict[str, Any],
    selected_citations: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if selected_citations is not None:
        return [dict(citation) for citation in selected_citations]

    citations = retrieval_result.get("citations") or []
    if citations and any(citation.get("content") or citation.get("document") for citation in citations):
        return [dict(citation) for citation in citations]

    # Compatibility for legacy call sites/tests that only provide retrieved items.
    result: list[dict[str, Any]] = []
    for item in retrieval_result.get("retrieved_items") or []:
        metadata = dict(item.get("metadata") or {})
        result.append(
            {
                **metadata,
                "chunk_id": item.get("chunk_id") or item.get("_id"),
                "content": item.get("content") or item.get("document"),
                "supports_task_ids": item.get("supports_task_ids")
                or metadata.get("supports_task_ids")
                or [],
            }
        )

    if result:
        return result

    structured_result = retrieval_result.get("structured_result")
    if structured_result:
        return [
            {
                "chunk_id": "structured-result",
                "title": structured_result.get("table_name") or "Dữ liệu tra cứu có cấu trúc",
                "cohort": structured_result.get("cohort"),
                "content": _to_pretty_json(structured_result),
            }
        ]
    return []


def _composition_units(
    retrieval_result: dict[str, Any],
    *,
    fallback_cohort: str | None,
    fallback_question: str,
) -> list[dict[str, Any]]:
    plan = retrieval_result.get("query_plan") or {}
    tasks = plan.get("tasks") or []
    task_results = {
        str(result.get("task_id")): result
        for result in retrieval_result.get("task_results") or []
        if result.get("task_id")
    }
    coverage_by_task = retrieval_result.get("coverage_by_task") or {}
    units: list[dict[str, Any]] = []

    for index, task in enumerate(tasks, 1):
        task_id = str(task.get("id") or f"t{index}")
        result = task_results.get(task_id) or {}
        cohorts = task.get("cohorts") or result.get("cohorts") or [fallback_cohort or "default"]
        coverage_by_cohort = result.get("coverage_by_cohort") or {}
        for task_cohort in cohorts:
            cohort_key = str(task_cohort or "default")
            coverage = str(
                coverage_by_cohort.get(cohort_key)
                or result.get("coverage")
                or coverage_by_task.get(task_id)
                or "uncovered"
            )
            units.append(
                {
                    "task_id": task_id,
                    "question": str(task.get("question") or result.get("question") or "").strip(),
                    "mode": str(task.get("mode") or result.get("mode") or "rag"),
                    "cohort": cohort_key,
                    "coverage": coverage,
                    "clarification_question": task.get("clarification_question")
                    or result.get("clarification_question"),
                }
            )

    if units:
        return units

    return [
        {
            "task_id": "legacy",
            "question": str(
                retrieval_result.get("effective_query")
                or retrieval_result.get("query")
                or fallback_question
            ).strip(),
            "mode": "rag",
            "cohort": str(fallback_cohort or retrieval_result.get("selected_cohort") or "default"),
            "coverage": "covered" if _has_primary_evidence(retrieval_result) else "uncovered",
            "clarification_question": retrieval_result.get("clarification_question"),
        }
    ]


def _normalize_source(citation: dict[str, Any], index: int) -> dict[str, Any]:
    metadata = citation.get("metadata") or {}
    supports_task_ids = citation.get("supports_task_ids") or metadata.get("supports_task_ids") or []
    applicable_cohorts = citation.get("applicable_cohorts") or metadata.get("applicable_cohorts") or []
    if isinstance(applicable_cohorts, str):
        applicable_cohorts = [applicable_cohorts]
    source_id = str(
        citation.get("source_parent_id")
        or citation.get("parent_section_id")
        or citation.get("chunk_id")
        or citation.get("document_id")
        or f"source-{index}"
    )
    content = str(citation.get("content") or citation.get("document") or "").strip()
    parent_content = str(citation.get("parent_content") or "").strip()
    article_label = normalize_article_label(
        citation.get("article_label"),
        citation.get("parent_article"),
        metadata.get("article"),
        citation.get("source_section"),
        citation.get("title"),
        article_label_from_heading(parent_content.splitlines()[0])
        if parent_content
        else None,
        article_label_from_heading(content.splitlines()[0]) if content else None,
    )
    return {
        "source_ref": f"S{index}",
        "source_id": source_id,
        "title": citation.get("title") or metadata.get("title"),
        "article_label": article_label,
        "source_cohort": citation.get("cohort") or metadata.get("cohort"),
        "applicable_cohorts": [str(value) for value in applicable_cohorts],
        "applicability": citation.get("applicability") or metadata.get("applicability"),
        "source_pages": citation.get("source_pages") or metadata.get("source_pages") or [],
        "supports_task_ids": [str(task_id) for task_id in supports_task_ids],
        "content": strip_misattached_amendment_notes(
            content,
            source_parent_id=source_id,
        ),
        "parent_content": strip_misattached_amendment_notes(
            parent_content,
            source_parent_id=source_id,
        ),
    }


def _source_supports_unit(source: dict[str, Any], unit: dict[str, Any]) -> bool:
    task_id = unit["task_id"]
    supports_task_ids = source["supports_task_ids"]
    if task_id != "legacy" and task_id not in supports_task_ids:
        return False

    # Task binding is authoritative. Cohort filtering becomes strict only when
    # runtime exposes explicit applicability metadata; a K50-authored policy
    # may legitimately apply to K51.
    applicable_cohorts = source["applicable_cohorts"]
    return not applicable_cohorts or unit["cohort"] in applicable_cohorts


def _source_for_unit(
    source: dict[str, Any],
    unit: dict[str, Any],
    max_chars: int,
) -> dict[str, Any]:
    """Select the evidence representation appropriate for this task mode.

    A canonical source may support both a structured lookup and a regulation
    task. Evidence fusion keeps one citation identity, so RAG units must use
    the full parent regulation text while structured units keep the curated
    JSON/table representation.
    """

    content = source["content"]
    if unit.get("mode") == "rag" and source.get("parent_content"):
        content = source["parent_content"]
    return {
        key: value
        for key, value in {
            **source,
            "content": limit_context(content, max_chars),
        }.items()
        if key != "parent_content"
    }


def _source_content_budget(*, max_context_chars: int, source_count: int) -> int:
    usable = max(1000, int(max_context_chars) * 3 // 4)
    return max(1000, usable // max(1, source_count))


def _has_primary_evidence(retrieval_result: dict[str, Any]) -> bool:
    return bool(
        retrieval_result.get("citations")
        or retrieval_result.get("retrieved_items")
        or retrieval_result.get("structured_result")
    )


def _to_pretty_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str)
