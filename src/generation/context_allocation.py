from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContextAllocationConfig:
    strategy: str = "equal_split"
    min_chars_per_doc: int = 400
    max_chars_per_doc: int = 1800
    sentence_boundary: bool = True
    cache_version: str = "context_alloc_v1"

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
        )

    def cache_fingerprint(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "cache_version": self.cache_version,
        }


def build_context_for_prompt(
    retrieval_result: dict[str, Any],
    *,
    selected_citations: list[dict[str, Any]] | None = None,
    max_context_chars: int,
    allocation_config: ContextAllocationConfig | dict[str, Any] | None = None,
) -> str:
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
