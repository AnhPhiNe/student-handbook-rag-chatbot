from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from src.common.cohort import is_validated_source_applicable
from src.common.legal_reference import article_label_from_heading, normalize_article_label

from .amendment_precedence import (
    ApplicableAmendment,
    collect_applicable_amendments,
    strip_misattached_amendment_notes,
)
DEFAULT_MAX_CONTEXT_CHARS = 160000
ANSWER_PROMPT_VERSION = "student-handbook-answer-v3.22-answer-scope"


def build_answer_prompt(
    query: str,
    retrieval_result: dict[str, Any],
    selected_citations: list[dict[str, Any]] | None = None,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    cohort: str | None = None,
) -> str:
    """Build a compact, task-bound answer prompt."""
    prompt, _ = build_answer_prompt_bundle(
        query=query,
        retrieval_result=retrieval_result,
        selected_citations=selected_citations,
        max_context_chars=max_context_chars,
        cohort=cohort,
    )
    return prompt


def build_answer_prompt_bundle(
    query: str,
    retrieval_result: dict[str, Any],
    selected_citations: list[dict[str, Any]] | None = None,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    cohort: str | None = None,
) -> tuple[str, str]:
    """Build the Composer prompt and return its exact evidence JSON.

    ``context_used`` in API/debug/evaluation output must describe what the
    Composer actually received, rather than a second legacy rendering of the
    same retrieval result.
    """
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
    evidence_context = _to_pretty_json(packet)

    prompt = f"""Bạn là chatbot tra cứu Sổ tay sinh viên. Trả lời bằng tiếng Việt tự nhiên, rõ ràng, đủ ý và chính xác; không tự ý rút gọn đến mức gây hiểu lầm.

QUY TẮC BẮT BUỘC
1. Trả lời đúng và đầy đủ các ý thực sự được hỏi trong từng đơn vị. Không tóm tắt toàn bộ Điều hoặc mở rộng sang chính sách khác khi câu hỏi chỉ yêu cầu một khía cạnh. Chỉ kết luận dứt khoát khi evidence trực tiếp xác lập kết luận và câu hỏi đã cung cấp đủ điều kiện cần thiết.
2. Mỗi đơn vị chỉ được dùng evidence và source_ref đã cấp cho đúng task/cohort; không mượn nguồn của đơn vị khác.
3. Giữ đúng phạm vi ngữ nghĩa mà nguồn trực tiếp xác lập: đối tượng, hành vi, kết quả, điều kiện và hệ quả. Không chuyển thông tin giữa các khái niệm gần nghĩa hoặc coi chúng là tương đương/tên gọi thay thế, kể cả khi đặt trong ngoặc, trừ khi nguồn trực tiếp định nghĩa như vậy; nếu có nhiều cơ chế, trình bày riêng từng phần và giữ đúng điều kiện, ngoại lệ tương ứng.
4. Nếu kết quả phụ thuộc thông tin câu hỏi chưa cung cấp, hãy trình bày rõ từng trường hợp có căn cứ và nêu thông tin còn thiếu để xác định trường hợp của người dùng; không tự đoán hoặc trả lời có/không tuyệt đối.
5. Khi evidence có article_label, nêu đúng article_label tại phần kết luận mà nguồn đó trực tiếp hỗ trợ. Không tự tạo Điều/khoản/điểm và không liệt kê các nguồn không được dùng để trả lời.
6. Với câu hỏi có/không, chỉ được trả lời có/không khi evidence trực tiếp cho phép hoặc cấm đúng hành vi/kết quả được hỏi. Lịch, thời hạn, điều kiện, quy trình, yêu cầu phê duyệt và việc nguồn không nói "được phép" đều không đủ để suy ra lệnh cấm. Nếu thiếu căn cứ trực tiếp, nói "Nguồn hiện có chưa trực tiếp xác lập..."; không thay câu trả lời bằng một chính sách khác chỉ vì cùng chủ đề.
7. Nếu evidence không đủ cho một ý thực sự được hỏi, nói chưa tìm thấy căn cứ cho đúng ý đó; không đổi target và không suy "Sổ tay không quy định" chỉ vì packet không chứa thông tin ngoài target.
8. Nếu nguồn chỉ dẫn chiếu sang văn bản khác mà không trực tiếp liệt kê đối tượng, điều kiện hoặc giá trị được hỏi, phải nói rõ nguồn hiện có không liệt kê nội dung đó và nêu văn bản được dẫn chiếu; không trình bày câu dẫn chiếu như thể đã trả lời danh sách.
9. Khi evidence có role=target, ưu tiên target để trả lời đúng khía cạnh được hỏi; chỉ bổ sung khoản/ý khác khi cần giải thích điều kiện hoặc ngoại lệ của chính kết luận đó. Nếu chỉ có role=candidate, trả lời thận trọng trong phạm vi evidence và không biến mục gần nghĩa thành target mới.

QUY CÁCH
- Không dùng kiến thức ngoài AUTHORIZED_EVIDENCE_BY_UNIT.
- Không chèn mã nguồn như [S1] vào câu trả lời; giao diện hiển thị nguồn riêng.
- Với đơn vị mode=structured, chỉ nêu kết quả trực tiếp và giải thích cần thiết; không sao chép toàn bộ bảng, danh mục hoặc structured JSON vào Markdown vì giao diện đã hiển thị dữ liệu đó riêng.
- Nếu structured evidence có resolved_result, phải sao chép chính xác kết quả đó; không tự chọn lại hàng hoặc tính lại từ bảng đầy đủ.
- Mọi số liệu phải lấy nguyên từ evidence đã được cấp cho đơn vị; không tính lại, nội suy hoặc mượn số liệu từ đơn vị khác.
- Dùng Markdown có chọn lọc: in đậm kết luận chính, số liệu, thời hạn và điều kiện quan trọng; dùng danh sách khi có nhiều bước, điều kiện hoặc trường hợp. Không in đậm cả đoạn.
- Với coverage=needs_clarification, chỉ nêu clarification_question của đơn vị đó.
- Với các đơn vị không cần clarification: nếu coverage=uncovered hoặc không có source_ref được phép, nói chưa tìm thấy căn cứ cho đúng ý đó.
- Nếu có applicable_amendments, áp dụng nội dung mới nhất trong đúng phạm vi nhưng không nhắc nhãn kỹ thuật amendment.
- Không hiển thị quá trình suy luận, metadata kỹ thuật hoặc tự tạo mục nguồn.

AUTHORIZED_EVIDENCE_BY_UNIT
{evidence_context}

FINAL_INSTRUCTIONS
Câu hỏi gốc: {query}

Các đơn vị bắt buộc phải xử lý theo đúng thứ tự:
{_to_pretty_json(required_units)}

Chỉ xuất câu trả lời cuối cùng cho sinh viên."""
    return prompt, evidence_context


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
    source_groups: list[list[dict[str, Any]]] = []
    for unit in units:
        authorized_sources = [
            source
            for source in sources
            if _source_supports_unit(source, unit)
        ]
        authorized_sources = _assign_evidence_roles(
            authorized_sources,
            unit_question=unit["question"],
            original_query=query,
        )
        source_groups.append(authorized_sources)

    source_budgets = _allocate_source_content_budgets(
        units,
        source_groups,
        max_context_chars=max_context_chars,
    )
    packet_units: list[dict[str, Any]] = []
    for unit, authorized_sources, budgets in zip(
        units,
        source_groups,
        source_budgets,
        strict=True,
    ):
        authorized_sources = [
            rendered
            for source, budget in zip(authorized_sources, budgets, strict=True)
            if (rendered := _source_for_unit(source, unit, budget))["content"]
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


def limit_context(context: str, max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS) -> str:
    context = (context or "").strip()
    if max_context_chars <= 0:
        return ""
    if len(context) <= max_context_chars:
        return context
    marker = "\n\n[Evidence đã được rút gọn.]"
    if max_context_chars <= len(marker):
        return context[:max_context_chars]
    return context[: max_context_chars - len(marker)].rstrip() + marker


def _resolve_primary_citations(
    retrieval_result: dict[str, Any],
    selected_citations: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if selected_citations is not None:
        return [dict(citation) for citation in selected_citations]

    citations = retrieval_result.get("citations") or []
    if citations and any(citation.get("content") or citation.get("document") for citation in citations):
        return [dict(citation) for citation in citations]

    # Forced retrieval evaluation provides retrieved items without a QueryPlan.
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
            clarification_question = None
            if coverage == "needs_clarification":
                by_cohort = result.get("clarification_by_cohort")
                clarification_question = (
                    by_cohort.get(cohort_key)
                    if isinstance(by_cohort, dict)
                    else task.get("clarification_question")
                    or result.get("clarification_question")
                )
            units.append(
                {
                    "task_id": task_id,
                    "question": str(task.get("question") or result.get("question") or "").strip(),
                    "mode": str(task.get("mode") or result.get("mode") or "rag"),
                    "cohort": cohort_key,
                    "coverage": coverage,
                    "clarification_question": clarification_question,
                }
            )

    if units:
        return units

    return [
        {
            "task_id": "_unplanned",
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
        "source_cohort": (
            citation.get("source_cohort")
            or metadata.get("source_cohort")
            or citation.get("cohort")
            or metadata.get("cohort")
        ),
        "applicable_cohorts": [str(value) for value in applicable_cohorts],
        "applicability_validated": bool(
            citation.get("applicability_validated")
            or metadata.get("applicability_validated")
        ),
        "applicability": citation.get("applicability") or metadata.get("applicability"),
        **(
            {"resolved_result": citation["resolved_result"]}
            if citation.get("resolved_result") is not None
            else {}
        ),
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
    if task_id != "_unplanned" and task_id not in supports_task_ids:
        return False

    target_cohort = None if unit["cohort"] == "default" else unit["cohort"]
    return is_validated_source_applicable(source, target_cohort)


def _assign_evidence_roles(
    sources: list[dict[str, Any]],
    *,
    unit_question: str,
    original_query: str,
) -> list[dict[str, Any]]:
    """Mark one uniquely requested article without treating rank as authority."""

    query_text = _fold_text(f"{unit_question} {original_query}")
    article_numbers = set(re.findall(r"\bdieu\s+(\d+)\b", query_text))
    article_matches = [
        index
        for index, source in enumerate(sources)
        if _article_number(source.get("article_label")) in article_numbers
    ]

    target_index: int | None = None
    if len(article_matches) == 1:
        target_index = article_matches[0]

    if target_index is None:
        return [{**source, "role": "candidate"} for source in sources]
    return [
        {
            **source,
            "role": "target" if index == target_index else "candidate",
        }
        for index, source in enumerate(sources)
    ]


def _fold_text(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = text.replace("đ", "d")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _article_number(article_label: Any) -> str | None:
    match = re.search(r"\bdieu\s+(\d+)\b", _fold_text(article_label))
    return match.group(1) if match else None


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

    content = _source_content_for_unit(source, unit)
    return {
        key: value
        for key, value in {
            **source,
            "content": limit_context(content, max_chars),
        }.items()
        if key != "parent_content"
    }


def _source_content_for_unit(source: dict[str, Any], unit: dict[str, Any]) -> str:
    if unit.get("mode") == "rag" and source.get("parent_content"):
        return str(source["parent_content"])
    return str(source.get("content") or "")


def _allocate_source_content_budgets(
    units: list[dict[str, Any]],
    source_groups: list[list[dict[str, Any]]],
    *,
    max_context_chars: int,
) -> list[list[int]]:
    """Protect exact targets, then share candidate budget by unit and source."""

    usable = max(0, int(max_context_chars) * 3 // 4)
    budgets = [[0 for _ in sources] for sources in source_groups]
    target_entries: list[tuple[int, int, int]] = []
    candidate_entries_by_unit: list[list[tuple[int, int]]] = []
    for unit_index, (unit, sources) in enumerate(
        zip(units, source_groups, strict=True)
    ):
        unit_candidates: list[tuple[int, int]] = []
        for source_index, source in enumerate(sources):
            content_length = len(_source_content_for_unit(source, unit))
            if source.get("role") == "target":
                target_entries.append((unit_index, source_index, content_length))
            else:
                unit_candidates.append((source_index, content_length))
        candidate_entries_by_unit.append(unit_candidates)

    target_allocations = _fair_allocations(
        [length for _, _, length in target_entries],
        usable,
    )
    for (unit_index, source_index, _), allocation in zip(
        target_entries,
        target_allocations,
        strict=True,
    ):
        budgets[unit_index][source_index] = allocation

    remaining = usable - sum(target_allocations)
    candidate_unit_indexes = [
        unit_index
        for unit_index, entries in enumerate(candidate_entries_by_unit)
        if entries
    ]
    candidate_unit_allocations = _fair_allocations(
        [
            sum(length for _, length in candidate_entries_by_unit[unit_index])
            for unit_index in candidate_unit_indexes
        ],
        remaining,
    )
    for unit_index, unit_allocation in zip(
        candidate_unit_indexes,
        candidate_unit_allocations,
        strict=True,
    ):
        entries = candidate_entries_by_unit[unit_index]
        source_allocations = _fair_allocations(
            [length for _, length in entries],
            unit_allocation,
        )
        for (source_index, _), allocation in zip(
            entries,
            source_allocations,
            strict=True,
        ):
            budgets[unit_index][source_index] = allocation
    return budgets


def _fair_allocations(
    needs: list[int],
    available: int,
) -> list[int]:
    """Water-fill a bounded budget and redistribute every unused share."""

    allocations = [0 for _ in needs]
    pending = [index for index, need in enumerate(needs) if need > 0]
    remaining = max(0, available)
    while pending and remaining > 0:
        share, remainder = divmod(remaining, len(pending))
        completed = [index for index in pending if needs[index] <= share]
        if completed:
            for index in completed:
                allocations[index] = needs[index]
                remaining -= needs[index]
                pending.remove(index)
            continue
        for position, index in enumerate(pending):
            allocation = share + int(position < remainder)
            allocations[index] = allocation
            remaining -= allocation
        break
    return allocations


def _has_primary_evidence(retrieval_result: dict[str, Any]) -> bool:
    return bool(
        retrieval_result.get("citations")
        or retrieval_result.get("retrieved_items")
        or retrieval_result.get("structured_result")
    )


def _to_pretty_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str)
