from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from src.common.cohort import (
    is_cohort_applicable,
    is_validated_source_applicable,
    normalize_cohort,
)

from .formula_lookup import formula_lookup
from .foreign_language_lookup import foreign_language_lookup
from .office_lookup import normalize_text, office_lookup
from .program_lookup import program_lookup
from .study_duration_lookup import study_duration_lookup
from .structured_lookup import structured_lookup_from_slots
from .structured_routing import load_lookup_registry, validate_fact_lock_inputs


_REFERENCE_TABLE_TYPES: dict[str, set[str]] = {
    "foreign_language": {"foreign_language"},
    "scholarship_classification": {"scholarship"},
    "study_duration": {"study_duration"},
    "scoring": {"scoring", "conduct"},
}
_LOOKUP_TOOL_SPECS = load_lookup_registry().get("tools", {})


@dataclass(frozen=True)
class StructuredResolution:
    lookup_type: str
    strategy: str
    result_kind: str
    result: dict[str, Any]
    target_chunk_types: list[str]


def _slot_text(decision: dict[str, Any], *names: str) -> str:
    spans = decision.get("slot_spans") or {}
    slots = decision.get("slots") or {}
    for name in names:
        for source in (spans, slots):
            value = source.get(name)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, list) and value:
                joined = " ".join(str(v).strip() for v in value if str(v).strip())
                if joined:
                    return joined
    return ""


def _formula_article_number(result: dict[str, Any]) -> str | None:
    match = re.search(r"\bĐiều\s+(\d+)\b", str(result.get("source_article") or ""), re.IGNORECASE)
    return match.group(1) if match else None


def _bind_formula_source(
    result: dict[str, Any] | None,
    registry: list[dict[str, Any]],
    *,
    cohort: str | None,
) -> dict[str, Any] | None:
    """Bind formula provenance by canonical parent identity.

    Formula type or planner slots are not source identities. Prefer the parent
    ID emitted by extraction; use document/article only as a legacy fallback
    when that pair resolves to exactly one parent.
    """

    if result is None:
        return None
    sub_lookups = result.get("sub_lookups")
    if isinstance(sub_lookups, list) and sub_lookups:
        bound_sub_lookups = []
        for item in sub_lookups:
            if not isinstance(item, dict):
                continue
            bound_item = _bind_formula_source(item, registry, cohort=cohort)
            if bound_item is not None:
                bound_sub_lookups.append(bound_item)
        bound = dict(result)
        bound["sub_lookups"] = bound_sub_lookups
        bound["result"] = bound_sub_lookups
        bound["formula_count"] = len(bound_sub_lookups)
        return bound

    document_id = str(result.get("document_id") or "").strip()
    declared_parent_id = str(result.get("source_parent_id") or "").strip()
    if declared_parent_id:
        candidates = [
            table
            for table in registry
            if str(table.get("source_parent_id") or table.get("source_section_id") or "")
            == declared_parent_id
            and is_cohort_applicable(table, cohort)
        ]
    else:
        article_number = _formula_article_number(result)
        if not article_number or not document_id:
            return result
        article_pattern = re.compile(
            rf"(?:^|_)Dieu{re.escape(article_number)}(?:_|$)",
            re.IGNORECASE,
        )
        candidates = [
            table
            for table in registry
            if str(table.get("document_id") or "") == document_id
            and is_cohort_applicable(table, cohort)
            and article_pattern.search(
                str(table.get("source_parent_id") or table.get("source_section_id") or "")
            )
        ]
    parent_ids = list(
        dict.fromkeys(
            str(table.get("source_parent_id") or table.get("source_section_id") or "")
            for table in candidates
            if table.get("source_parent_id") or table.get("source_section_id")
        )
    )
    if len(parent_ids) != 1:
        return result

    bound = dict(result)
    bound["source_parent_ids"] = parent_ids
    bound["source_parent_id"] = parent_ids[0]
    bound["source_section"] = parent_ids[0]
    bound["source_pages"] = sorted(
        {
            page
            for table in candidates
            for page in table.get("source_pages") or []
        }
    )
    return bound


def _reference_input_clarification(
    lookup_type: str,
    *,
    query: str,
    candidates: list[dict[str, Any]],
    cohort: str | None,
    slots: dict[str, Any],
) -> dict[str, Any] | None:
    """Validate conditional table inputs declared by the selected data row.

    Small reference tables remain table-first.  This check only prevents a
    scalar value from being treated as sufficient when the table itself says
    that a result requires several independent components.
    """

    if lookup_type != "foreign_language":
        return None

    entity_text = str(slots.get("certificate_or_language") or query or "")
    entity_norm = normalize_text(entity_text)
    input_rows: list[dict[str, Any]] = []
    for table in candidates:
        for row in table.get("rows") or []:
            if not isinstance(row, dict):
                continue
            requirements = row.get("input_requirements") or {}
            if requirements.get("score_mode") != "per_component":
                continue
            declared_names = [
                str(row.get(field) or "")
                for field in ("certificate", "language", "level_or_scale")
            ]
            declared_names.extend(
                str(alias)
                for alias in requirements.get("entity_aliases") or []
                if str(alias).strip()
            )
            if any(
                candidate_norm
                and (
                    candidate_norm in entity_norm
                    or entity_norm in candidate_norm
                )
                for candidate_norm in map(normalize_text, declared_names)
            ):
                input_rows.append(row)

    if not input_rows:
        return None

    scalar_supplied = slots.get("score_or_level") not in (None, "", [])
    component_supplied = any(
        slots.get(name) not in (None, "", [])
        for name in (
            "listening_score",
            "reading_score",
            "speaking_score",
            "writing_score",
        )
    )
    if not scalar_supplied and not component_supplied:
        return None

    requirements = input_rows[0].get("input_requirements") or {}
    component_slots = requirements.get("component_slots") or {}
    missing: list[dict[str, str]] = []
    for component in requirements.get("required_components") or []:
        spec = component_slots.get(component) or {}
        slot_name = str(spec.get("slot") or f"{component}_score")
        if slots.get(slot_name) in (None, "", []):
            missing.append(
                {
                    "component": str(component),
                    "slot": slot_name,
                    "label": str(spec.get("label") or component),
                }
            )
    if not missing:
        return None

    labels = ", ".join(item["label"] for item in missing)
    return {
        "lookup_type": lookup_type,
        "cohort": cohort,
        "needs_clarification": True,
        "missing_slots": [item["slot"] for item in missing],
        "input_requirements": requirements,
        "clarification_question": (
            "Bạn vui lòng cung cấp điểm riêng cho các kỹ năng còn thiếu: "
            f"{labels}."
        ),
        "content_type": "structured_lookup_clarification",
    }


def _reference_table_lookup(
    lookup_type: str,
    *,
    query: str,
    registry: list[dict[str, Any]],
    cohort: str | None,
    slots: dict[str, Any],
) -> dict[str, Any] | None:
    """Fetch complete small reference tables without irreversible row filtering.

    QueryPlan classifies the structured domain and cohort.  The answer composer
    receives every applicable row and performs the semantic selection requested
    in the original task question.  Directory lookups are intentionally not
    handled here because their catalogs are larger and still need an entity
    shortlist.
    """

    table_types = _REFERENCE_TABLE_TYPES.get(lookup_type)
    if not table_types:
        return None

    effective_cohort = normalize_cohort(cohort)
    candidates = [
        table
        for table in registry
        if table.get("data_category") == "regulation_table"
        and str(table.get("table_type") or "") in table_types
        and is_validated_source_applicable(table, effective_cohort)
        and isinstance(table.get("rows"), list)
        and bool(table.get("rows"))
    ]
    if not candidates:
        return None

    clarification = _reference_input_clarification(
        lookup_type,
        query=query,
        candidates=candidates,
        cohort=effective_cohort,
        slots=slots,
    )
    if clarification is not None:
        return clarification

    selector = (_LOOKUP_TOOL_SPECS.get(lookup_type, {}).get("table_selector") or {})
    selector_slot = str(selector.get("slot") or "")
    selector_value = str(slots.get(selector_slot) or "") if selector_slot else ""
    selector_spec = (selector.get("values") or {}).get(selector_value)
    if isinstance(selector_spec, dict):
        selected_types = set(selector_spec.get("table_types") or [])
        selected_subtypes = set(selector_spec.get("table_subtypes") or [])
        selected = [
            table
            for table in candidates
            if (not selected_types or table.get("table_type") in selected_types)
            and (
                not selected_subtypes
                or table.get("table_subtype") in selected_subtypes
            )
        ]
        # A stale selector must not turn valid table evidence into uncovered.
        # Fall back to the complete lookup family when the configured selector
        # has no matching table in the current dataset.
        if selected:
            candidates = selected

    candidates.sort(
        key=lambda table: (
            str(table.get("cohort") or ""),
            str(table.get("table_subtype") or ""),
            str(table.get("table_id") or ""),
        )
    )
    leaf_lookups: list[dict[str, Any]] = []
    for table in candidates:
        rows = [dict(row) for row in table.get("rows") or [] if isinstance(row, dict)]
        source_section = table.get("source_parent_id") or table.get("source_section_id")
        leaf_lookups.append(
            {
                "lookup_type": lookup_type,
                "input_value": query,
                "result": {
                    "table_id": table.get("table_id"),
                    "table_subtype": table.get("table_subtype"),
                    "rows": rows,
                },
                "items": rows,
                "display_rows": rows,
                "table_id": table.get("table_id"),
                "table_name": table.get("table_name") or lookup_type,
                "table_subtype": table.get("table_subtype"),
                "source_pages": table.get("source_pages") or [],
                "source_label": table.get("document_title")
                or "Bảng dữ liệu có cấu trúc trong Sổ tay sinh viên HCMUE",
                "cohort": effective_cohort or table.get("cohort"),
                "source_cohort": table.get("source_cohort") or table.get("cohort"),
                "applicable_cohorts": table.get("applicable_cohorts"),
                "applicability": table.get("applicability"),
                "applicability_validated": table.get("applicability_validated"),
                "applicability_basis_parent_id": table.get(
                    "applicability_basis_parent_id"
                ),
                "document_id": table.get("document_id"),
                "source_section": source_section,
                "source_parent_id": source_section,
                "content_type": "structured_lookup",
            }
        )

    if len(leaf_lookups) == 1:
        return leaf_lookups[0]

    return {
        "lookup_type": lookup_type,
        "input_value": query,
        "cohort": effective_cohort,
        "result": {
            "tables": [
                {
                    "table_id": item.get("table_id"),
                    "table_name": item.get("table_name"),
                    "table_subtype": item.get("table_subtype"),
                    "cohort": item.get("cohort"),
                    "applicability": item.get("applicability"),
                    "rows": item.get("items") or [],
                }
                for item in leaf_lookups
            ],
            "table_count": len(leaf_lookups),
        },
        "sub_lookups": leaf_lookups,
        "source_pages": sorted(
            {
                page
                for item in leaf_lookups
                for page in item.get("source_pages") or []
            }
        ),
        "table_name": "Các bảng tra cứu áp dụng",
        "source_label": "Dữ liệu có cấu trúc trong Sổ tay sinh viên HCMUE",
        "content_type": "multi_structured_lookup",
    }


def _unique_reference_resolution(
    lookup_type: str,
    *,
    query: str,
    slots: dict[str, Any],
    cohort: str | None,
    scoring_tables: list[dict[str, Any]],
    foreign_language_tables: list[dict[str, Any]],
    structured_tables_registry: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return a fact-lock candidate only when an existing resolver is unique."""

    if lookup_type == "scoring":
        resolved = structured_lookup_from_slots(
            slots,
            scoring_tables,
            cohort=cohort,
        ) if slots else None
        return resolved if resolved and len(resolved.get("items") or []) == 1 else None

    if lookup_type == "foreign_language":
        resolved = foreign_language_lookup(
            query,
            foreign_language_tables,
            cohort=cohort,
            slots=slots,
        )
        return resolved if resolved and resolved.get("result_count") == 1 else None

    if lookup_type == "study_duration":
        resolved = study_duration_lookup(
            query,
            structured_tables_registry,
            cohort=cohort,
            slots=slots,
        )
        tables = ((resolved or {}).get("result") or {}).get("tables") or []
        row_count = sum(len(table.get("rows") or []) for table in tables)
        return resolved if resolved and row_count == 1 else None

    return None


def _resolve_single_lookup(
    lookup_type: str,
    *,
    decision: dict[str, Any],
    query: str,
    effective_cohort: str | None,
    scoring_tables: list[dict[str, Any]],
    formula_rules: list[dict[str, Any]],
    office_directory: list[dict[str, Any]],
    student_service_directory: list[dict[str, Any]],
    student_faculty_profiles: list[dict[str, Any]] | None,
    foreign_language_tables: list[dict[str, Any]],
    structured_tables_registry: list[dict[str, Any]],
    program_directory: list[dict[str, Any]],
    detected_entities: list[dict[str, Any]] | None = None,
    model: Any | None = None,
) -> StructuredResolution | None:
    slots = decision.get("slots") or {}

    if lookup_type in _REFERENCE_TABLE_TYPES:
        result = _reference_table_lookup(
            lookup_type,
            query=query,
            registry=structured_tables_registry,
            cohort=effective_cohort,
            slots=slots,
        )
        # Keep the complete reference table for UI rendering, but expose a
        # deterministic fact lock when an existing domain resolver identifies
        # exactly one row. Ungrounded, invalid, or non-unique lookups stay unlocked.
        fact_lock_errors = validate_fact_lock_inputs(decision, query=query)
        if (
            result is not None
            and not result.get("needs_clarification")
            and not fact_lock_errors
        ):
            resolved_result = _unique_reference_resolution(
                lookup_type,
                query=query,
                slots=slots,
                cohort=effective_cohort,
                scoring_tables=scoring_tables,
                foreign_language_tables=foreign_language_tables,
                structured_tables_registry=structured_tables_registry,
            )
            if resolved_result is not None:
                result = dict(result)
                result["resolved_result"] = resolved_result
        return _resolution(
            lookup_type,
            "reference_table_lookup",
            result,
            result_kind=(
                "clarification"
                if result and result.get("needs_clarification")
                else "structured"
            ),
            target_chunk_types=["structured_lookup"],
        )

    if lookup_type in {"student_service", "office", "faculty"}:
        matching_config = _LOOKUP_TOOL_SPECS.get(lookup_type, {}).get("matching") or {}
        candidate_slot = {
            "student_service": "service",
            "office": "office",
            "faculty": "faculty",
        }[lookup_type]
        candidate_text = (
            _slot_text(decision, candidate_slot)
            or _slot_text(decision, "faculty")
            or _slot_text(decision, "office")
            or _slot_text(decision, "program_or_faculty")
            or query
        )
        if lookup_type == "student_service":
            directory = student_service_directory + office_directory
        else:
            directory = office_directory + (student_faculty_profiles or [])

        routing = {
            "intent": "office_query",
            "content_type": "office_directory",
            "target_chunk_types": ["office_directory"],
        }
        result = office_lookup(
            query,
            directory,
            cohort=effective_cohort,
            detected_entities=detected_entities,
            routing=routing,
            candidate_text=candidate_text,
            require_confident_match=True,
            model=model if lookup_type == "student_service" else None,
            min_confidence=float(matching_config.get("min_confidence", 0.72)),
            ambiguity_margin=float(matching_config.get("ambiguity_margin", 0.08)),
        )
        if result is not None and result.get("resolution_status") == "ambiguous":
            options = result.get("clarification_options") or []
            result["clarification_question"] = (
                "Câu hỏi của bạn liên quan đến nhiều đơn vị. Bạn cần hỗ trợ cụ thể về mảng nào dưới đây?\n\n" + "\n".join(options)
            )
            return _resolution(
                lookup_type,
                "office_lookup_clarification",
                result,
                result_kind="clarification",
                target_chunk_types=[],
            )
        requested_field = str(slots.get("requested_field") or "")
        # A grounded directory record remains valid structured evidence even
        # when it does not contain the optional field requested by the user.
        # The Composer receives the record and must state that the available
        # evidence does not provide that field instead of inventing a value.
        if result is not None:
            result["requested_field"] = requested_field
        strategies = {
            "student_service": "student_service_lookup",
            "office": "office_lookup",
            "faculty": "faculty_lookup",
        }
        target_content_types = {
            "student_service": ["student_service_directory", "student_office_profile"],
            "office": ["student_office_profile", "student_faculty_profile"],
            "faculty": ["student_faculty_profile", "student_office_profile"],
        }
        return _resolution(
            lookup_type,
            strategies[lookup_type],
            result,
            target_chunk_types=target_content_types.get(lookup_type, ["student_office_profile"]),
        )

    if lookup_type == "program":
        candidate_text = _slot_text(decision, "program_or_faculty") or query
        intent = decision.get("intent")
        scope = str(slots.get("scope") or "school")
        requested_field = str(slots.get("requested_field") or "")
        if requested_field == "faculty":
            action = "resolve_faculty"
        elif intent == "exists" or requested_field == "exists":
            action = "exists"
        elif intent == "list_items" or requested_field == "programs":
            action = "list"
        else:
            action = "resolve_faculty"
        result = program_lookup(
            candidate_text,
            program_directory,
            cohort=effective_cohort,
            detected_entities=detected_entities,
            routing={
                "content_type": "program_directory",
                "action": action,
                "scope": scope,
            },
        )
        return _resolution(lookup_type, "program_lookup", result)

    if lookup_type == "formula":
        result = formula_lookup(
            query,
            formula_rules,
            cohort=effective_cohort,
            slots=slots,
        )
        result = _bind_formula_source(
            result,
            structured_tables_registry,
            cohort=effective_cohort,
        )
        return _resolution(
            lookup_type,
            "formula_lookup",
            result,
            result_kind="formula",
        )

    return None



def _is_valid_probe_result(
    resolution: StructuredResolution | None,
) -> bool:
    if not resolution or not resolution.result or resolution.result_kind == "clarification":
        return False
    res_data = resolution.result
    if isinstance(res_data, dict):
        if "result" in res_data and isinstance(res_data["result"], list):
            return len(res_data["result"]) > 0
        if "rows" in res_data and isinstance(res_data["rows"], list):
            return len(res_data["rows"]) > 0
        if "items" in res_data and isinstance(res_data["items"], list):
            return len(res_data["items"]) > 0
        if "table" in res_data and isinstance(res_data["table"], dict):
            return bool(res_data["table"])
        if res_data.get("exists") is True:
            return True
        if res_data.get("formula_text"):
            return True
    elif isinstance(res_data, list):
        return len(res_data) > 0
    return False


def resolve_structured_decision(
    decision: dict[str, Any],
    *,
    query: str,
    cohort: str | None,
    scoring_tables: list[dict[str, Any]],
    formula_rules: list[dict[str, Any]],
    office_directory: list[dict[str, Any]],
    student_service_directory: list[dict[str, Any]],
    student_faculty_profiles: list[dict[str, Any]] | None,
    foreign_language_tables: list[dict[str, Any]],
    structured_tables_registry: list[dict[str, Any]],
    program_directory: list[dict[str, Any]],
    detected_entities: list[dict[str, Any]] | None = None,
    model: Any | None = None,
    probe_other_domains: bool = True,
) -> StructuredResolution | None:
    lookup_type = str(decision.get("lookup_type") or "").strip()
    effective_cohort = normalize_cohort(cohort or decision.get("cohort"))

    lookup_kwargs = {
        "decision": decision,
        "query": query,
        "effective_cohort": effective_cohort,
        "scoring_tables": scoring_tables,
        "formula_rules": formula_rules,
        "office_directory": office_directory,
        "student_service_directory": student_service_directory,
        "student_faculty_profiles": student_faculty_profiles,
        "foreign_language_tables": foreign_language_tables,
        "structured_tables_registry": structured_tables_registry,
        "program_directory": program_directory,
        "detected_entities": detected_entities,
        "model": model,
    }

    primary_res = _resolve_single_lookup(lookup_type, **lookup_kwargs) if lookup_type else None

    # QueryPlan assigns exactly one structured tool to each task.  Keep the
    # historical cross-domain probing only for the legacy route path.
    if not probe_other_domains:
        return primary_res

    # When Router explicitly determines single pure regulation without lookup_type, skip structured probing
    if decision.get("execution_mode") == "regulation" and not lookup_type:
        return None

    candidate_domains = [
        "foreign_language",
        "scholarship_classification",
        "study_duration",
        "scoring",
        "formula",
        "program",
        "office",
        "student_service",
    ]

    collected: list[StructuredResolution] = []
    seen_lookups: set[str] = set()
    if primary_res and _is_valid_probe_result(primary_res):
        collected.append(primary_res)
        seen_lookups.add(primary_res.lookup_type)
        if primary_res.lookup_type in {"office", "faculty", "student_service"}:
            seen_lookups.update({"office", "faculty", "student_service"})

    for cand_type in candidate_domains:
        if cand_type in seen_lookups:
            continue
        cand_res = _resolve_single_lookup(cand_type, **lookup_kwargs)
        if _is_valid_probe_result(cand_res):
            collected.append(cand_res)
            seen_lookups.add(cand_type)
            if cand_type in {"office", "faculty", "student_service"}:
                seen_lookups.update({"office", "faculty", "student_service"})

    if len(collected) >= 2:
        combined_result = {
            "lookup_type": "multi_structured",
            "input_value": query,
            "cohort": effective_cohort,
            "lookup_count": len(collected),
            "result": [
                {
                    "lookup_type": item.lookup_type,
                    "table_name": item.result.get("table_name") or item.lookup_type,
                    "data": item.result.get("result") or item.result.get("items") or item.result,
                }
                for item in collected
            ],
            "sub_lookups": [
                item.result
                for item in collected
                if item.result and isinstance(item.result, dict)
            ],
            "source_pages": sorted(
                list(
                    {
                        p
                        for item in collected
                        for p in (item.result.get("source_pages") or [])
                    }
                )
            ),
            "table_name": "Các bảng tra cứu liên quan",
            "source_label": "Dữ liệu tra cứu tổng hợp trong Sổ tay sinh viên HCMUE",
            "content_type": "multi_structured_lookup",
        }
        all_target_chunks = list({ct for item in collected for ct in item.target_chunk_types})
        return StructuredResolution(
            lookup_type="multi_structured",
            strategy="multi_structured_lookup",
            result_kind="multi_structured",
            result=combined_result,
            target_chunk_types=all_target_chunks,
        )
    elif len(collected) == 1:
        return collected[0]

    return primary_res


def _resolution(
    lookup_type: str,
    strategy: str,
    result: dict[str, Any] | None,
    *,
    result_kind: str = "structured",
    target_chunk_types: list[str] | None = None,
) -> StructuredResolution | None:
    if result is None:
        return None
    return StructuredResolution(
        lookup_type=lookup_type,
        strategy=strategy,
        result_kind=result_kind,
        result=result,
        target_chunk_types=target_chunk_types or [
            str(result.get("content_type") or "structured_lookup")
        ],
    )
