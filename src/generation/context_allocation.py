from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .evidence_selection import build_evidence_context


@dataclass(frozen=True)
class ContextAllocationConfig:
    strategy: str = "equal_split"
    min_chars_per_doc: int = 400
    max_chars_per_doc: int = 1800
    sentence_boundary: bool = True
    cache_version: str = "context_alloc_v1"
    evidence_selection: dict[str, Any] | None = None

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> "ContextAllocationConfig":
        config = config or {}
        strategy = str(config.get("strategy") or "equal_split").strip().lower()
        if strategy not in {"equal_split", "score_weighted"}:
            strategy = "equal_split"

        max_chars = max(1, int(config.get("max_chars_per_doc", 1800)))
        min_chars = max(0, int(config.get("min_chars_per_doc", 400)))
        min_chars = min(min_chars, max_chars)

        return cls(
            strategy=strategy,
            min_chars_per_doc=min_chars,
            max_chars_per_doc=max_chars,
            sentence_boundary=bool(config.get("sentence_boundary", True)),
            cache_version=str(config.get("cache_version") or "context_alloc_v1"),
            evidence_selection=dict(config.get("evidence_selection") or {}),
        )

    def cache_fingerprint(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "cache_version": self.cache_version,
            "evidence_selection_enabled": bool((self.evidence_selection or {}).get("enabled", False)),
            "evidence_registry_path": (self.evidence_selection or {}).get("registry_path"),
            "evidence_rerank_top_k": (self.evidence_selection or {}).get("rerank_evidence_top_k"),
        }


def build_context_for_prompt(
    retrieval_result: dict[str, Any],
    *,
    query: str | None = None,
    selected_citations: list[dict[str, Any]] | None = None,
    max_context_chars: int,
    allocation_config: ContextAllocationConfig | dict[str, Any] | None = None,
) -> str:
    """Thuật toán đóng gói và cắt gọt tài liệu (Context Allocation) trước khi đưa cho LLM.
    
    Vấn đề:
    LLM (như Gemini/Llama) có giới hạn về số lượng token (Max Token) có thể đọc trong một lần.
    Nếu Retrieval kéo lên 10 tài liệu quá dài, LLM sẽ bị "tràn bộ nhớ" (Context Window Overflow).
    
    Cách giải quyết (Thuật toán):
    1. Nhận danh sách các tài liệu (retrieval_result) và số ký tự tối đa cho phép (max_context_chars).
    2. Trừ đi phần dung lượng (budget) dành cho các tiêu đề (Headers - Tên tài liệu, trang số mấy).
    3. Phân bổ phần dung lượng còn lại cho các tài liệu theo chiến lược (strategy) đã cấu hình:
       - equal_split: Chia đều số ký tự cho tất cả tài liệu.
       - score_weighted: Chia nhiều số ký tự hơn cho tài liệu nào có điểm số Retrieval cao hơn.
    4. Cắt (truncate) các tài liệu sao cho không làm vỡ câu (giữ nguyên dấu chấm câu - sentence_boundary).
    5. Nối chúng lại với nhau kèm đường dẫn nguồn để đưa vào Prompt.
    
    Args:
        retrieval_result: Kết quả trả về từ luồng tìm kiếm.
        query: Câu hỏi của người dùng để ưu tiên cắt đúng đoạn chứa từ khóa.
        max_context_chars: Giới hạn ký tự tối đa LLM có thể đọc.
        
    Returns:
        str: Một khối văn bản (Context) đã được dồn nén tối ưu nhất để nhét vào Prompt.
    """
    config = (
        allocation_config
        if isinstance(allocation_config, ContextAllocationConfig)
        else ContextAllocationConfig.from_config(allocation_config)
    )
    max_context_chars = max(0, int(max_context_chars))
    if max_context_chars <= 0:
        return ""

    items = _filter_retrieved_items(
        retrieval_result.get("retrieved_items") or [],
        selected_citations=selected_citations or [],
    )
    if not items:
        return truncate_text(
            str(retrieval_result.get("context_for_llm") or ""),
            max_context_chars,
            sentence_boundary=config.sentence_boundary,
        )

    headers = [_source_header(index, item) for index, item in enumerate(items, start=1)]
    separator_budget = max(0, len("\n\n---\n\n") * (len(items) - 1))
    header_budget = sum(len(header) for header in headers) + separator_budget
    content_budget = max(0, max_context_chars - header_budget)

    budgets = allocate_context_budget(
        items,
        total_budget=content_budget,
        min_chars_per_doc=config.min_chars_per_doc,
        max_chars_per_doc=config.max_chars_per_doc,
        strategy=config.strategy,
    )

    blocks: list[str] = []
    for header, item, budget in zip(headers, items, budgets, strict=False):
        content = str(item.get("content") or "").strip()
        content = prepare_content_for_prompt(
            content,
            item=item,
            query=query or str(retrieval_result.get("query") or ""),
            budget=budget,
            sentence_boundary=config.sentence_boundary,
            evidence_config=config.evidence_selection,
        )
        truncated_content = truncate_text(
            content,
            budget,
            sentence_boundary=config.sentence_boundary,
        )
        blocks.append(f"{header}{truncated_content}")

    return truncate_text(
        "\n\n---\n\n".join(blocks),
        max_context_chars,
        sentence_boundary=config.sentence_boundary,
    )


def prepare_content_for_prompt(
    content: str,
    *,
    item: dict[str, Any] | None = None,
    query: str | None = None,
    budget: int = 1800,
    sentence_boundary: bool = True,
    evidence_config: dict[str, Any] | None = None,
) -> str:
    """Chuẩn hóa phần nguồn trước khi cắt để LLM đọc đúng đoạn liên quan hơn."""

    content = _strip_generated_focus_sections((content or "").strip())
    if not content:
        return ""

    metadata = (item or {}).get("metadata", {}) or {}
    evidence_context = build_evidence_context(item=item, query=query, config=evidence_config or {})

    if (
        not evidence_context
        and metadata.get("chunk_type") == "regulation"
        and len(content) <= budget
    ):
        return content

    query_terms = _query_terms(query or "")
    table_context = _normalized_table_context(content, metadata)
    section_context = _section_aware_context(content, query_terms)
    snippet_context = _snippet_aware_context(
        content,
        query_terms,
        max_chars=max(600, min(max(900, budget), 2200)),
        sentence_boundary=sentence_boundary,
    )

    blocks: list[str] = []
    focused_evidence_mode = bool(evidence_context) and _is_focused_evidence_question(query or "")
    if table_context:
        blocks.append("BẢNG/DANH SÁCH ĐÃ CHUẨN HÓA:\n" + table_context)
    if evidence_context:
        blocks.append(evidence_context)
    if section_context and not focused_evidence_mode and section_context not in table_context:
        blocks.append("ĐIỀU/MỤC LIÊN QUAN:\n" + section_context)
    if snippet_context and snippet_context not in table_context + section_context:
        blocks.append("ĐOẠN LIÊN QUAN:\n" + snippet_context)

    if blocks:
        raw_context = truncate_text(
            content,
            max(800, min(max(1200, budget), 2600)),
            sentence_boundary=sentence_boundary,
        )
        if raw_context:
            blocks.append("VĂN BẢN GỐC LIÊN QUAN:\n" + raw_context)
        return "\n\n".join(blocks)

    return content


def _strip_generated_focus_sections(content: str) -> str:
    """Remove evidence/context labels that may have been appended in older cached excerpts."""

    if not content:
        return ""

    generated_markers = (
        "thong tin trong tam",
        "bang danh sach da",
        "bang dong da gom",
        "dieu kien truong hop moc so lieu",
        "van ban goc lien quan",
    )
    lines = content.splitlines()
    for index, line in enumerate(lines):
        normalized = _normalize_text(line)
        if any(marker in normalized for marker in generated_markers):
            if index == 0:
                return content.strip()
            return "\n".join(lines[:index]).strip()
    return content


def _is_focused_evidence_question(query: str) -> bool:
    normalized = _normalize_text(query)
    if not normalized:
        return False
    focused_phrases = (
        "dieu kien",
        "truong hop",
        "bao nhieu",
        "may dot",
        "thang nao",
        "khi nao",
        "luc nao",
        "gom gi",
        "gom nhung gi",
        "can gi",
        "xet sao",
    )
    return any(phrase in normalized for phrase in focused_phrases)


def _query_terms(query: str) -> list[str]:
    normalized = _normalize_text(query)
    if not normalized:
        return []

    stopwords = {
        "la",
        "co",
        "cua",
        "cho",
        "toi",
        "minh",
        "ban",
        "nhung",
        "nao",
        "gi",
        "thi",
        "duoc",
        "khong",
        "bao",
        "nhieu",
        "may",
        "ve",
        "trong",
        "the",
        "nhu",
    }
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) >= 3 and token not in stopwords
    ]

    phrases: list[str] = []
    for size in (4, 3, 2):
        for index in range(0, max(0, len(tokens) - size + 1)):
            phrase = " ".join(tokens[index : index + size])
            if len(phrase) >= 8:
                phrases.append(phrase)

    seen: set[str] = set()
    result: list[str] = []
    for term in [*phrases, *tokens]:
        if term and term not in seen:
            seen.add(term)
            result.append(term)
    return result[:24]


def _normalized_table_context(content: str, metadata: dict[str, Any]) -> str:
    if not _looks_like_table(metadata, content):
        return ""

    rows = _compact_structured_lines(content)
    if not rows:
        return ""

    blocks = ["STRUCTURED SOURCE LINES:"]
    blocks.extend(f"- {row}" for row in rows[:12])
    return "\n".join(blocks).strip()

def _section_aware_context(content: str, query_terms: list[str]) -> str:
    if not query_terms:
        return ""

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if len(lines) < 3:
        return ""

    relevant_indices: list[int] = []
    for index, line in enumerate(lines):
        normalized_line = _normalize_text(line)
        if _term_score(normalized_line, query_terms) >= 2:
            relevant_indices.append(index)

    if not relevant_indices:
        return ""

    selected: list[str] = []
    for index in relevant_indices[:4]:
        start = _nearest_section_start(lines, index)
        end = _nearest_section_end(lines, index, start)
        selected.extend(lines[start : end + 1])

    return "\n".join(_dedupe_preserve_order(selected)).strip()


def _snippet_aware_context(
    content: str,
    query_terms: list[str],
    *,
    max_chars: int,
    sentence_boundary: bool,
) -> str:
    if not query_terms:
        return ""

    normalized_content = _normalize_text(content)
    best_index = -1
    best_score = 0
    best_term = ""
    for term in query_terms:
        start = 0
        while True:
            index = normalized_content.find(term, start)
            if index < 0:
                break
            window = normalized_content[max(0, index - 240) : index + 240]
            score = _term_score(window, query_terms)
            if score > best_score:
                best_score = score
                best_index = index
                best_term = term
            start = index + len(term)

    if best_index < 0 or best_score <= 0:
        return ""

    start = max(0, best_index - max_chars // 3)
    end = min(len(content), start + max_chars)
    boundary_start = _move_to_boundary(content, start, backward=True)
    if best_index - boundary_start <= max_chars // 2:
        start = boundary_start
    end = _move_to_boundary(content, end, backward=False)
    snippet = content[start:end].strip()
    truncated = truncate_text(snippet, max_chars, sentence_boundary=sentence_boundary)
    if best_term and best_term in _normalize_text(snippet) and best_term not in _normalize_text(truncated):
        return truncate_text(snippet, max_chars, sentence_boundary=False)
    return truncated


def _find_sentence_with_terms(content: str, terms: list[str]) -> str:
    normalized_terms = [_normalize_text(term) for term in terms]
    candidates = re.split(r"(?<=[.!?。])\s+|\n+", content)
    best = ""
    best_score = 0
    for candidate in candidates:
        normalized_candidate = _normalize_text(candidate)
        score = _term_score(normalized_candidate, normalized_terms)
        if score > best_score:
            best = candidate.strip()
            best_score = score
    return best if best_score > 0 else ""


def _looks_like_table(metadata: dict[str, Any], content: str) -> bool:
    if metadata.get("has_table") or metadata.get("chunk_type") == "table":
        return True
    return len(_compact_structured_lines(content)) >= 2


def _compact_structured_lines(content: str) -> list[str]:
    lines = [_collapse_space(line) for line in content.splitlines()]
    rows = [
        line
        for line in lines
        if line
        and (
            re.match(r"^(\d+\.|[a-z]\)|[-–•])\s+", line, flags=re.IGNORECASE)
            or len(re.findall(r"\b\d+(?:[,.]\d+)?\b", line)) >= 2
        )
    ]
    return _dedupe_preserve_order(rows)


def _nearest_section_start(lines: list[str], index: int) -> int:
    for cursor in range(index, -1, -1):
        if _is_section_marker(lines[cursor]):
            return cursor
    return max(0, index - 2)


def _nearest_section_end(lines: list[str], index: int, start: int) -> int:
    for cursor in range(index + 1, min(len(lines), start + 10)):
        if _is_section_marker(lines[cursor]):
            return max(index, cursor - 1)
    return min(len(lines) - 1, index + 4)


def _is_section_marker(line: str) -> bool:
    return bool(re.match(r"^(\d+\.|[a-z]\)|[IVX]+\.)\s+", line.strip(), flags=re.IGNORECASE))


def _term_score(text: str, terms: list[str]) -> int:
    score = 0
    for term in terms:
        if not term or term not in text:
            continue
        token_count = max(1, len(term.split()))
        score += token_count * token_count
    return score


def _normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.lower().replace("đ", "d")
    return _collapse_space(text)


def _collapse_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _move_to_boundary(text: str, index: int, *, backward: bool) -> int:
    index = max(0, min(len(text), index))
    boundaries = "\n.;:"
    if backward:
        candidates = [text.rfind(boundary, 0, index) for boundary in boundaries]
        best = max(candidates)
        return best + 1 if best >= 0 else index

    candidates = [text.find(boundary, index) for boundary in boundaries]
    positives = [candidate for candidate in candidates if candidate >= 0]
    return min(positives) + 1 if positives else index


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = _normalize_text(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def allocate_context_budget(
    items: list[dict[str, Any]],
    *,
    total_budget: int,
    min_chars_per_doc: int,
    max_chars_per_doc: int,
    strategy: str = "equal_split",
) -> list[int]:
    count = len(items)
    if count == 0:
        return []

    total_budget = max(0, int(total_budget))
    max_chars = max(1, int(max_chars_per_doc))
    min_chars = min(max(0, int(min_chars_per_doc)), max_chars)
    if total_budget <= 0:
        return [0] * count

    if total_budget < count * min_chars:
        return _split_evenly(total_budget, count, cap=max_chars)

    budgets = [min_chars] * count
    remaining = total_budget - sum(budgets)
    caps = [max_chars - min_chars for _ in range(count)]

    if strategy == "score_weighted":
        weights = [_score_for_item(item, index) for index, item in enumerate(items)]
        if not any(weight > 0 for weight in weights):
            weights = [1.0] * count
    else:
        weights = [1.0] * count

    _distribute_remaining(budgets, caps, weights, remaining)
    return budgets


def truncate_text(text: str, budget: int, *, sentence_boundary: bool = True) -> str:
    text = (text or "").strip()
    budget = max(0, int(budget))
    if len(text) <= budget:
        return text
    if budget <= 0:
        return ""
    if budget <= 24:
        return text[:budget].rstrip()

    cut = text[:budget].rstrip()
    if not sentence_boundary:
        return _trim_to_word(cut)

    boundary = _last_sentence_boundary(cut)
    min_boundary = max(40, int(budget * 0.45))
    if boundary >= min_boundary:
        return cut[:boundary].rstrip()

    return _trim_to_word(cut)


def _filter_retrieved_items(
    items: list[Any],
    *,
    selected_citations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    selected_chunk_ids = {
        str(citation.get("chunk_id"))
        for citation in selected_citations
        if citation.get("chunk_id")
    }
    selected_titles = {
        str(citation.get("title") or "").strip().lower()
        for citation in selected_citations
        if citation.get("title")
    }

    filtered: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata", {}) or {}
        chunk_id = str(item.get("chunk_id") or "")
        title = _item_title(item, metadata).lower()
        if selected_chunk_ids and chunk_id not in selected_chunk_ids:
            continue
        if not selected_chunk_ids and selected_titles and title not in selected_titles:
            continue
        filtered.append(item)
    return filtered


def _source_header(index: int, item: dict[str, Any]) -> str:
    metadata = item.get("metadata", {}) or {}
    title = _item_title(item, metadata)
    return "\n".join(
        [
            f"[Nguồn {index}]",
            f"Tiêu đề: {title}",
            f"Loại: {metadata.get('chunk_type')}",
            f"Trang: {metadata.get('source_pages')}",
            "Nội dung:",
            "",
        ]
    )


def _item_title(item: dict[str, Any], metadata: dict[str, Any]) -> str:
    return str(
        metadata.get("title")
        or metadata.get("form_name")
        or metadata.get("unit_name")
        or metadata.get("faculty_or_unit_name")
        or metadata.get("program_name")
        or metadata.get("faculty_name")
        or metadata.get("procedure_name")
        or metadata.get("rule_name")
        or item.get("chunk_id")
        or "Nguồn"
    ).strip()


def _score_for_item(item: dict[str, Any], index: int) -> float:
    rerank = item.get("rerank")
    if isinstance(rerank, dict):
        value = rerank.get("final_score")
        if _is_positive_number(value):
            return float(value)

    value = item.get("score")
    if _is_positive_number(value):
        return float(value)

    return 1.0 / float(index + 1)


def _is_positive_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def _split_evenly(total: int, count: int, *, cap: int) -> list[int]:
    if count <= 0:
        return []
    base = total // count
    remainder = total % count
    budgets = [min(base, cap) for _ in range(count)]
    for index in range(count):
        if remainder <= 0:
            break
        if budgets[index] < cap:
            budgets[index] += 1
            remainder -= 1
    return budgets


def _distribute_remaining(
    budgets: list[int],
    caps: list[int],
    weights: list[float],
    remaining: int,
) -> None:
    active = {index for index, cap in enumerate(caps) if cap > 0}
    remaining = max(0, int(remaining))

    while remaining > 0 and active:
        total_weight = sum(max(weights[index], 0.0) for index in active)
        if total_weight <= 0:
            effective_weights = {index: 1.0 for index in active}
        else:
            effective_weights = {index: max(weights[index], 0.0) for index in active}
        total_weight = sum(effective_weights.values()) or float(len(active))

        round_budget = remaining
        raw_shares = {
            index: round_budget * effective_weights[index] / total_weight
            for index in active
        }
        allocations = {
            index: min(caps[index], int(raw_shares[index])) for index in active
        }

        allocated_this_round = sum(allocations.values())
        if allocated_this_round < round_budget:
            leftovers = sorted(
                active,
                key=lambda index: (
                    raw_shares[index] - int(raw_shares[index]),
                    effective_weights[index],
                ),
                reverse=True,
            )
            for index in leftovers:
                if allocated_this_round >= round_budget:
                    break
                if allocations[index] >= caps[index]:
                    continue
                allocations[index] += 1
                allocated_this_round += 1

        if allocated_this_round <= 0:
            break

        for index, addition in allocations.items():
            budgets[index] += addition
            caps[index] -= addition
            remaining -= addition
            if caps[index] <= 0:
                active.remove(index)


def _last_sentence_boundary(text: str) -> int:
    matches = list(re.finditer(r"(?<=[\.\?!;:。！？])\s+|\n{1,}", text))
    if not matches:
        return -1
    return matches[-1].end()


def _trim_to_word(text: str) -> str:
    match = re.search(r"\s+\S*$", text)
    if match and match.start() >= 24:
        return text[: match.start()].rstrip()
    return text.rstrip()
