from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any


REGISTRY_VERSION = "section_evidence_v1"

_STOPWORDS = {
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
    "can",
    "hoi",
    "neu",
    "va",
    "hoac",
    "voi",
}

_NUMERIC_QUESTION_TERMS = {
    "bao",
    "nhieu",
    "may",
    "dot",
    "thang",
    "nam",
    "tin",
    "chi",
    "dieu",
    "kien",
    "truong",
    "hop",
    "muc",
}

_GENERIC_FOCUS_TERMS = {
    "sinh vien",
    "hoc tap",
    "quy dinh",
    "quy che",
    "dieu kien",
    "truong hop",
    "thoi gian",
    "nha truong",
    "chuong trinh",
}

_GENERIC_FOCUS_TOKENS = {
    "sinh",
    "vien",
    "hoc",
    "tap",
    "quy",
    "dinh",
    "che",
    "dieu",
    "kien",
    "truong",
    "hop",
    "thoi",
    "gian",
    "chuong",
    "trinh",
}

_LIST_QUESTION_TERMS = {
    "dieu",
    "kien",
    "truong",
    "hop",
    "gom",
    "nhung",
    "nao",
    "can",
    "bao",
    "nhieu",
    "may",
    "dot",
    "thang",
    "muc",
}


def build_section_evidence_registry(
    docstore_path: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    docstore = json.loads(Path(docstore_path).read_text(encoding="utf-8"))
    sections: dict[str, list[dict[str, Any]]] = {}
    block_count = 0

    for item in docstore:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") or {}
        content_type = str(metadata.get("content_type") or metadata.get("chunk_type") or "")
        if content_type and content_type not in {"regulation_text", "regulation_sections", "regulation"}:
            continue

        blocks = _extract_blocks_from_docstore_item(item)
        if not blocks:
            continue

        for block in blocks:
            section_key = _section_key_from_block(block)
            sections.setdefault(section_key, []).append(block)
            block_count += 1

    registry = {
        "version": REGISTRY_VERSION,
        "source": str(docstore_path),
        "block_count": block_count,
        "section_count": len(sections),
        "sections": sections,
    }

    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(registry, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return registry


def select_evidence_blocks(
    *,
    item: dict[str, Any],
    query: str,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    config = config or {}
    if not bool(config.get("enabled", False)):
        return []
    if not _is_regulation_item(item):
        return []

    registry_path = str(
        config.get("registry_path")
        or "data/processed/metadata/section_evidence_registry.json"
    )
    registry = load_evidence_registry(registry_path)
    blocks = _blocks_for_item(registry, item)
    if not blocks:
        return []

    cheap_top_k = max(1, int(config.get("cheap_candidate_top_k", 12)))
    rerank_top_k = max(1, int(config.get("rerank_evidence_top_k", 3)))
    query_terms = _query_terms(query)
    scored = [
        (_lexical_score(block, query, query_terms, item), block) for block in blocks
    ]
    scored = [(score, block) for score, block in scored if score > 0]
    if not scored:
        scored = [(0.001, block) for block in _important_blocks(blocks)[:cheap_top_k]]

    candidates = [
        block for _, block in sorted(scored, key=lambda pair: pair[0], reverse=True)[:cheap_top_k]
    ]
    if not candidates:
        return []

    selected = _rerank_candidates(query, candidates, rerank_top_k, config)
    selected = _ensure_focus_coverage(
        selected=selected,
        candidates=candidates,
        query_terms=query_terms,
        top_k=rerank_top_k,
    )
    selected = _attach_structural_children(
        selected=selected,
        all_blocks=blocks,
        query=query,
        query_terms=query_terms,
        max_extra=int(config.get("max_structural_evidence_blocks", 8)),
    )
    selected = _attach_neighbors(
        selected=selected,
        all_blocks=blocks,
        query=query,
        query_terms=query_terms,
        window=max(0, int(config.get("neighbor_window", 1))),
    )
    return selected[: max(rerank_top_k + 4, rerank_top_k)]


def format_evidence_for_prompt(blocks: list[dict[str, Any]]) -> str:
    if not blocks:
        return ""

    condition_lines: list[str] = []
    table_lines: list[str] = []
    other_lines: list[str] = []

    for block in blocks:
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        prefix = _block_prefix(block)
        line = f"- {prefix}{text}" if prefix else f"- {text}"
        block_type = str(block.get("block_type") or "")
        if block_type == "table_like_row":
            table_lines.append(line)
        elif block_type in {"clause", "item", "bullet", "numbered_condition"}:
            condition_lines.append(line)
        else:
            other_lines.append(line)

    sections: list[str] = ["THÔNG TIN TRỌNG TÂM TỪ NGUỒN:"]
    if condition_lines:
        sections.append(
            "ĐIỀU KIỆN / TRƯỜNG HỢP / MỐC SỐ LIỆU:\n"
            + "\n".join(_dedupe_lines(condition_lines))
        )
    if table_lines:
        sections.append(
            "BẢNG/DÒNG ĐÃ GOM TỪ NGUỒN:\n"
            + "\n".join(_dedupe_lines(table_lines))
        )
    if other_lines:
        sections.append("\n".join(_dedupe_lines(other_lines)))
    return "\n\n".join(sections)


def build_evidence_context(
    *,
    item: dict[str, Any] | None,
    query: str | None,
    config: dict[str, Any] | None,
) -> str:
    if not item:
        return ""
    blocks = select_evidence_blocks(item=item, query=query or "", config=config or {})
    return format_evidence_for_prompt(blocks)


@lru_cache(maxsize=4)
def load_evidence_registry(path: str) -> dict[str, Any]:
    registry_path = Path(path)
    if not registry_path.exists():
        return {}
    try:
        return json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _extract_blocks_from_docstore_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = item.get("metadata") or {}
    base = {
        "document_id": str(item.get("document_id") or metadata.get("document_id") or ""),
        "cohort": str(item.get("cohort") or metadata.get("cohort") or ""),
        "parent_section_id": str(metadata.get("parent_section_id") or item.get("_id") or ""),
        "source_section": str(metadata.get("title") or metadata.get("source_section") or ""),
        "source_pages": metadata.get("source_pages") or [],
        "section_title": str(metadata.get("title") or metadata.get("article") or ""),
    }

    blocks: list[dict[str, Any]] = []
    block_index = 0
    for table in item.get("tables") or []:
        if not isinstance(table, dict):
            continue
        table_name = str(table.get("table_name") or table.get("table_id") or "Bảng")
        rows = table.get("rows") or []
        columns = table.get("columns") or []
        if table_name:
            blocks.append(
                _make_block(
                    base,
                    block_index,
                    "heading",
                    table_name,
                    list_marker=None,
                    parent_marker="table",
                )
            )
            block_index += 1
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_text = _format_table_row(row, columns)
            if row_text:
                blocks.append(
                    _make_block(
                        base,
                        block_index,
                        "table_like_row",
                        row_text,
                        list_marker=None,
                        parent_marker="table",
                    )
                )
                block_index += 1

    content = _strip_docstore_preamble(str(item.get("content") or ""))
    for raw_block in _split_text_blocks(content):
        text = raw_block.strip()
        if not text:
            continue
        block_type, list_marker, parent_marker = _classify_text_block(text)
        blocks.append(
            _make_block(
                base,
                block_index,
                block_type,
                text,
                list_marker=list_marker,
                parent_marker=parent_marker,
            )
        )
        block_index += 1

    return blocks


def _make_block(
    base: dict[str, Any],
    block_index: int,
    block_type: str,
    text: str,
    *,
    list_marker: str | None,
    parent_marker: str | None,
) -> dict[str, Any]:
    text = _clean_text(text)
    signals = _signals(text)
    evidence_id = "|".join(
        [
            base.get("document_id", ""),
            base.get("cohort", ""),
            base.get("parent_section_id", ""),
            str(block_index),
        ]
    )
    return {
        "evidence_id": evidence_id,
        **base,
        "block_type": block_type,
        "block_index": block_index,
        "list_marker": list_marker,
        "parent_marker": parent_marker,
        "text": text,
        "signals": signals,
    }


def _format_table_row(row: dict[str, Any], columns: list[Any]) -> str:
    ordered_columns = [str(column) for column in columns if str(column) in row]
    if not ordered_columns:
        ordered_columns = [str(column) for column in row.keys()]
    parts = []
    for column in ordered_columns:
        value = str(row.get(column) or "").strip()
        if value:
            parts.append(f"{column}: {value}")
    return " | ".join(parts)


def _strip_docstore_preamble(content: str) -> str:
    marker = "Nội dung:"
    if marker in content:
        content = content.split(marker, 1)[1].strip()
    return _strip_generated_focus_sections(content.strip())


def _strip_generated_focus_sections(content: str) -> str:
    markers = (
        "THÔNG TIN TRỌNG TÂM ĐÃ TÁCH TỪ NGUỒN:",
        "THÔNG TIN TRỌNG TÂM TỪ NGUỒN:",
    )
    for marker in markers:
        if marker in content:
            content = content.split(marker, 1)[0].strip()
    return content


def _split_text_blocks(content: str) -> list[str]:
    lines = [_clean_text(line) for line in content.splitlines()]
    lines = [line for line in lines if line]
    blocks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        if current:
            blocks.append(" ".join(current).strip())
            current = []

    for line in lines:
        if _starts_new_block(line):
            flush()
            current = [line]
        else:
            current.append(line)
    flush()

    expanded: list[str] = []
    marker_pattern = re.compile(r"(?=(?:^|\s)(?:\d+\.|[a-zđ]\)|[-•]\s))", re.IGNORECASE)
    for block in blocks:
        if len(block) < 650:
            expanded.append(block)
            continue
        pieces = [piece.strip() for piece in marker_pattern.split(block) if piece.strip()]
        if len(pieces) <= 1:
            expanded.append(block)
        else:
            expanded.extend(pieces)
    return expanded


def _starts_new_block(line: str) -> bool:
    return bool(
        re.match(r"^(Điều|Chương|Mục)\b", line, flags=re.IGNORECASE)
        or re.match(r"^\d+\.", line)
        or re.match(r"^[a-zđ]\)", line, flags=re.IGNORECASE)
        or re.match(r"^[-•]\s+", line)
    )


def _classify_text_block(text: str) -> tuple[str, str | None, str | None]:
    stripped = text.strip()
    if re.match(r"^(Điều|Chương|Mục)\b", stripped, flags=re.IGNORECASE):
        return "heading", None, None
    numbered = re.match(r"^(\d+)\.", stripped)
    if numbered:
        return (
            "numbered_condition" if _has_numeric_signal(stripped) else "clause",
            numbered.group(1),
            "numbered",
        )
    item = re.match(r"^([a-zđ])\)", stripped, flags=re.IGNORECASE)
    if item:
        return "item", item.group(1), "lettered"
    if re.match(r"^[-•]\s+", stripped):
        return "bullet", None, "bullet"
    if _looks_table_like(stripped):
        return "table_like_row", None, "table"
    return "clause", None, None


def _signals(text: str) -> dict[str, Any]:
    normalized = _normalize_text(text)
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) >= 3 and token not in _STOPWORDS
    ]
    keywords: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token not in seen:
            seen.add(token)
            keywords.append(token)
    return {
        "numbers": re.findall(r"\d+(?:[.,]\d+)?", text),
        "time_terms": re.findall(
            r"(?:tháng\s+\d+|\d+\s*(?:năm|tháng|tín chỉ|đợt|%))",
            text,
            flags=re.IGNORECASE,
        ),
        "keywords": keywords[:24],
    }


def _query_terms(query: str) -> list[str]:
    normalized = _normalize_text(query)
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) >= 3 and token not in _STOPWORDS
    ]
    phrases: list[str] = []
    for size in (3, 2):
        for index in range(max(0, len(tokens) - size + 1)):
            phrases.append(" ".join(tokens[index : index + size]))
    seen: set[str] = set()
    result: list[str] = []
    for term in [*phrases, *tokens]:
        if term and term not in seen:
            seen.add(term)
            result.append(term)
    return result[:24]


def _lexical_score(
    block: dict[str, Any],
    query: str,
    query_terms: list[str],
    item: dict[str, Any] | None = None,
) -> float:
    normalized_text = _normalize_text(str(block.get("text") or ""))
    normalized_title = _normalize_text(
        f"{block.get('section_title') or ''} {block.get('source_section') or ''}"
    )
    score = 0.0
    for term in query_terms:
        if term in normalized_text:
            score += 2.0 if " " in term else 1.0
        if term in normalized_title:
            score += 0.6

    query_norm = _normalize_text(query)
    signals = block.get("signals") or {}
    if _is_numeric_or_condition_question(query_norm):
        if signals.get("numbers"):
            score += 1.25
        if signals.get("time_terms"):
            score += 1.25
        if str(block.get("block_type")) in {"table_like_row", "numbered_condition", "item"}:
            score += 0.8

    item_metadata = (item or {}).get("metadata") or {}
    source_title = _normalize_text(str(item_metadata.get("title") or item_metadata.get("source_section") or ""))
    if source_title and normalized_title and source_title in normalized_title:
        score += 0.3
    return score


def _important_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(block: dict[str, Any]) -> tuple[int, int]:
        block_type = str(block.get("block_type") or "")
        text = str(block.get("text") or "")
        priority = {
            "table_like_row": 0,
            "numbered_condition": 1,
            "item": 2,
            "clause": 3,
            "bullet": 4,
            "heading": 5,
        }.get(block_type, 6)
        if _has_numeric_signal(text):
            priority -= 1
        return (priority, int(block.get("block_index") or 0))

    return sorted(blocks, key=key)


def _rerank_candidates(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    if not bool(config.get("use_cross_encoder_reranker", False)):
        return candidates[:top_k]
    try:
        from src.retrieval.core.cross_encoder_reranker import get_local_reranker

        pseudo_docs = [
            {
                "content": str(block.get("text") or ""),
                "metadata": {"title": str(block.get("section_title") or "")},
                "_evidence_id": block.get("evidence_id"),
            }
            for block in candidates
        ]
        reranked = get_local_reranker().rerank(query, pseudo_docs, top_n=top_k)
        by_id = {block.get("evidence_id"): block for block in candidates}
        selected = [
            by_id.get(doc.get("_evidence_id"))
            for doc in reranked
            if doc.get("_evidence_id") in by_id
        ]
        selected = [block for block in selected if block is not None]
        return selected[:top_k] or candidates[:top_k]
    except Exception:
        if bool(config.get("fallback_to_lexical_scoring", True)):
            return candidates[:top_k]
        return []


def _ensure_focus_coverage(
    *,
    selected: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    query_terms: list[str],
    top_k: int,
) -> list[dict[str, Any]]:
    focus_terms = _focus_terms(query_terms)
    if not focus_terms or not candidates:
        return selected[:top_k]

    selected_ids = {str(block.get("evidence_id")) for block in selected}
    selected_has_focus = any(
        _focus_overlap_count(block, focus_terms) > 0 for block in selected
    )
    if selected_has_focus:
        return selected[:top_k]

    focused = [
        block
        for block in candidates
        if str(block.get("evidence_id")) not in selected_ids
        and _focus_overlap_count(block, focus_terms) > 0
    ]
    if not focused:
        return selected[:top_k]

    focused.sort(
        key=lambda block: (
            _focus_overlap_count(block, focus_terms),
            _has_numeric_signal(str(block.get("text") or "")),
            -int(block.get("block_index") or 0),
        ),
        reverse=True,
    )
    return [focused[0], *selected][:top_k]


def _attach_structural_children(
    *,
    selected: list[dict[str, Any]],
    all_blocks: list[dict[str, Any]],
    query: str,
    query_terms: list[str],
    max_extra: int,
) -> list[dict[str, Any]]:
    if not selected or max_extra <= 0 or not _is_list_or_fact_question(query):
        return selected

    by_index = {int(block.get("block_index") or 0): block for block in all_blocks}
    selected_ids = {str(block.get("evidence_id")) for block in selected}
    expanded = list(selected)

    for block in selected:
        block_type = str(block.get("block_type") or "")
        if block_type in {"clause", "numbered_condition"} and _introduces_child_list(block):
            added = 0
            start_index = int(block.get("block_index") or 0) + 1
            for offset in range(start_index, start_index + 16):
                child = by_index.get(offset)
                if not child or _section_key_from_block(child) != _section_key_from_block(block):
                    break
                child_type = str(child.get("block_type") or "")
                if child_type == "heading" or child.get("parent_marker") == "numbered":
                    break
                if child_type in {"item", "bullet", "table_like_row", "numbered_condition", "clause"}:
                    child_id = str(child.get("evidence_id"))
                    if child_id not in selected_ids:
                        selected_ids.add(child_id)
                        expanded.append(child)
                        added += 1
                if added >= max_extra:
                    break
            continue

        if block_type in {"item", "bullet", "table_like_row"}:
            for sibling in _sibling_run(block, all_blocks):
                sibling_id = str(sibling.get("evidence_id"))
                if sibling_id in selected_ids:
                    continue
                if _sibling_is_useful(block, sibling, query_terms):
                    selected_ids.add(sibling_id)
                    expanded.append(sibling)
                if len(expanded) - len(selected) >= max_extra:
                    break

    expanded.sort(key=lambda block: int(block.get("block_index") or 0))
    return expanded


def _attach_neighbors(
    *,
    selected: list[dict[str, Any]],
    all_blocks: list[dict[str, Any]],
    query: str,
    query_terms: list[str],
    window: int,
) -> list[dict[str, Any]]:
    if not selected or window <= 0:
        return selected
    by_index = {int(block.get("block_index") or 0): block for block in all_blocks}
    selected_ids = {str(block.get("evidence_id")) for block in selected}
    expanded: list[dict[str, Any]] = []

    for block in selected:
        index = int(block.get("block_index") or 0)
        for neighbor_index in range(index - window, index + window + 1):
            neighbor = by_index.get(neighbor_index)
            if not neighbor:
                continue
            neighbor_id = str(neighbor.get("evidence_id"))
            if neighbor_id in selected_ids:
                if neighbor not in expanded:
                    expanded.append(neighbor)
                continue
            if _neighbor_is_relevant(block, neighbor, query, query_terms):
                selected_ids.add(neighbor_id)
                expanded.append(neighbor)

    expanded.sort(key=lambda block: int(block.get("block_index") or 0))
    return expanded


def _neighbor_is_relevant(
    anchor: dict[str, Any],
    neighbor: dict[str, Any],
    query: str,
    query_terms: list[str],
) -> bool:
    if _section_key_from_block(anchor) != _section_key_from_block(neighbor):
        return False
    same_group = (
        anchor.get("parent_marker")
        and anchor.get("parent_marker") == neighbor.get("parent_marker")
    )
    if same_group and anchor.get("parent_marker") in {"table", "lettered", "numbered", "bullet"}:
        return True
    score = _lexical_score(neighbor, query, query_terms)
    if score >= 1.2:
        return True
    anchor_signals = anchor.get("signals") or {}
    neighbor_signals = neighbor.get("signals") or {}
    if set(anchor_signals.get("numbers") or []) & set(neighbor_signals.get("numbers") or []):
        return True
    if set(anchor_signals.get("time_terms") or []) & set(neighbor_signals.get("time_terms") or []):
        return True
    return False


def _focus_terms(query_terms: list[str]) -> list[str]:
    focus: list[str] = []
    for term in query_terms:
        normalized = _normalize_text(term)
        if not normalized or normalized in _GENERIC_FOCUS_TERMS:
            continue
        tokens = normalized.split()
        if len(tokens) >= 2:
            specific_tokens = [
                token for token in tokens if token not in _GENERIC_FOCUS_TOKENS
            ]
            if specific_tokens:
                focus.append(normalized)
            continue
        if len(normalized) >= 4 and normalized not in _STOPWORDS:
            focus.append(normalized)
    return focus[:10]


def _focus_overlap_count(block: dict[str, Any], focus_terms: list[str]) -> int:
    if not focus_terms:
        return 0
    text = _normalize_text(
        f"{block.get('section_title') or ''} {block.get('source_section') or ''} {block.get('text') or ''}"
    )
    return sum(1 for term in focus_terms if term in text)


def _is_list_or_fact_question(query: str) -> bool:
    normalized = _normalize_text(query)
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    if tokens & _LIST_QUESTION_TERMS:
        return True
    return any(
        phrase in normalized
        for phrase in (
            "nhu nao",
            "gom gi",
            "gom nhung gi",
            "can gi",
            "xet sao",
            "luc nao",
            "khi nao",
        )
    )


def _introduces_child_list(block: dict[str, Any]) -> bool:
    text = _normalize_text(str(block.get("text") or ""))
    return any(
        phrase in text
        for phrase in (
            "nhu sau",
            "cac dieu kien sau",
            "dieu kien sau",
            "cac truong hop sau",
            "truong hop sau",
            "bao gom",
            "gom",
        )
    )


def _sibling_run(anchor: dict[str, Any], all_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    anchor_index = int(anchor.get("block_index") or 0)
    anchor_type = str(anchor.get("block_type") or "")
    anchor_parent = str(anchor.get("parent_marker") or "")
    if not anchor_parent:
        return []

    blocks_by_index = {
        int(block.get("block_index") or 0): block for block in all_blocks
    }
    result: list[dict[str, Any]] = []

    index = anchor_index - 1
    while index >= 0:
        block = blocks_by_index.get(index)
        if not _same_sibling_group(anchor, block, anchor_type, anchor_parent):
            break
        result.append(block)
        index -= 1

    result.reverse()
    result.append(anchor)

    index = anchor_index + 1
    while True:
        block = blocks_by_index.get(index)
        if not _same_sibling_group(anchor, block, anchor_type, anchor_parent):
            break
        result.append(block)
        index += 1

    return result


def _same_sibling_group(
    anchor: dict[str, Any],
    block: dict[str, Any] | None,
    anchor_type: str,
    anchor_parent: str,
) -> bool:
    if not block:
        return False
    if _section_key_from_block(anchor) != _section_key_from_block(block):
        return False
    if str(block.get("block_type") or "") != anchor_type:
        return False
    return str(block.get("parent_marker") or "") == anchor_parent


def _sibling_is_useful(
    anchor: dict[str, Any],
    sibling: dict[str, Any],
    query_terms: list[str],
) -> bool:
    if sibling == anchor:
        return True
    if str(anchor.get("parent_marker") or "") in {"lettered", "bullet", "table"}:
        return True
    score = _lexical_score(sibling, " ".join(query_terms), query_terms)
    return score >= 1.0


def _blocks_for_item(registry: dict[str, Any], item: dict[str, Any]) -> list[dict[str, Any]]:
    sections = registry.get("sections") or {}
    if not isinstance(sections, dict):
        return []
    keys = _registry_keys_for_item(item)
    blocks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in keys:
        for block in sections.get(key, []) or []:
            evidence_id = str(block.get("evidence_id") or "")
            if evidence_id and evidence_id not in seen:
                seen.add(evidence_id)
                blocks.append(block)
    return blocks


def _registry_keys_for_item(item: dict[str, Any]) -> list[str]:
    metadata = item.get("metadata") or {}
    document_id = str(
        metadata.get("document_id")
        or item.get("document_id")
        or _split_chunk_id(str(item.get("chunk_id") or ""))[0]
        or ""
    )
    cohort = str(metadata.get("cohort") or item.get("cohort") or "")
    candidates = [
        metadata.get("parent_section_id"),
        metadata.get("source_section"),
        metadata.get("title"),
        item.get("parent_section_id"),
        item.get("chunk_id"),
    ]
    keys: list[str] = []
    for section_id in candidates:
        if not section_id:
            continue
        key = _section_key(document_id, cohort, str(section_id))
        if key not in keys:
            keys.append(key)
    return keys


def _section_key_from_block(block: dict[str, Any]) -> str:
    return _section_key(
        str(block.get("document_id") or ""),
        str(block.get("cohort") or ""),
        str(block.get("parent_section_id") or block.get("source_section") or ""),
    )


def _section_key(document_id: str, cohort: str, section_id: str) -> str:
    return "|".join([document_id.strip(), cohort.strip(), section_id.strip()])


def _is_regulation_item(item: dict[str, Any]) -> bool:
    metadata = item.get("metadata") or {}
    content_type = str(metadata.get("content_type") or "")
    chunk_type = str(metadata.get("chunk_type") or "")
    return content_type in {"regulation_text", "regulation_sections"} or chunk_type in {
        "regulation",
        "regulation_text",
        "regulation_sections",
    }


def _split_chunk_id(chunk_id: str) -> tuple[str, str]:
    if "::" in chunk_id:
        left, right = chunk_id.split("::", 1)
        return left, right
    return "", chunk_id


def _is_numeric_or_condition_question(query_norm: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", query_norm))
    return bool(tokens & _NUMERIC_QUESTION_TERMS)


def _looks_table_like(text: str) -> bool:
    return " | " in text or len(re.findall(r"\d+(?:[.,]\d+)?", text)) >= 2


def _has_numeric_signal(text: str) -> bool:
    return bool(re.search(r"\d+(?:[.,]\d+)?", text))


def _block_prefix(block: dict[str, Any]) -> str:
    marker = str(block.get("list_marker") or "").strip()
    if marker:
        text = str(block.get("text") or "").lstrip()
        if re.match(rf"^{re.escape(marker)}(?:\.|\))\s+", text, flags=re.IGNORECASE):
            return ""
        if str(block.get("block_type")) == "item":
            return f"{marker}) "
        if str(block.get("block_type")) in {"clause", "numbered_condition"}:
            return f"{marker}. "
    return ""


def _dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        key = _normalize_text(line)
        if key not in seen:
            seen.add(key)
            result.append(line)
    return result


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    without_marks = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return without_marks.replace("đ", "d").replace("Đ", "D").lower()
