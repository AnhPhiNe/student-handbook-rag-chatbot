from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.common.cohort import is_cohort_applicable, normalize_cohort

from .formula_lookup import formula_lookup
from .foreign_language_lookup import foreign_language_lookup
from .office_lookup import normalize_text, office_lookup
from .program_lookup import program_lookup
from .scholarship_lookup import scholarship_classification_lookup
from .study_duration_lookup import study_duration_lookup
from .structured_lookup import structured_lookup_from_slots


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


def _result_supports_requested_field(
    result: dict[str, Any] | None,
    requested_field: str,
) -> bool:
    if result is None or requested_field in {"", "all"}:
        return result is not None
    field_map = {
        "unit": "unit_name",
        "phone": "phones",
        "email": "emails",
        "office": "office",
        "website": "websites",
        "services": "responsibilities",
    }
    record_field = field_map.get(requested_field)
    if record_field is None:
        return False
    records = result.get("result") or []
    return bool(records) and all(record.get(record_field) for record in records)


def _bind_regulation_source(
    result: dict[str, Any] | None,
    registry: list[dict[str, Any]],
    *,
    cohort: str | None,
    table_type: str,
    subtypes: set[str] | None = None,
) -> dict[str, Any] | None:
    if result is None:
        return None
    candidates = [
        table
        for table in registry
        if table.get("data_category") == "regulation_table"
        and table.get("table_type") == table_type
        and is_cohort_applicable(table, cohort)
        and (
            not subtypes
            or str(table.get("table_subtype") or "") in subtypes
        )
    ]
    source_parent_ids = list(
        dict.fromkeys(
            str(table.get("source_parent_id") or table.get("source_section_id"))
            for table in candidates
            if table.get("source_parent_id") or table.get("source_section_id")
        )
    )
    if not source_parent_ids:
        return result
    bound = dict(result)
    bound["source_parent_ids"] = source_parent_ids
    bound["source_parent_id"] = source_parent_ids[0]
    bound["source_section"] = source_parent_ids[0]
    if len({str(table.get("document_id") or "") for table in candidates}) == 1:
        bound["document_id"] = candidates[0].get("document_id")
    bound["source_pages"] = sorted(
        {
            page
            for table in candidates
            for page in table.get("source_pages") or []
        }
    )
    return bound


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

    if lookup_type == "foreign_language":
        result = foreign_language_lookup(
            query,
            foreign_language_tables,
            cohort=effective_cohort,
            slots=slots,
        )
        result = _bind_regulation_source(
            result,
            structured_tables_registry,
            cohort=effective_cohort,
            table_type="foreign_language",
        )
        return _resolution(lookup_type, "foreign_language_lookup", result)

    if lookup_type == "study_duration":
        result = study_duration_lookup(
            query,
            structured_tables_registry,
            cohort=effective_cohort,
            slots=slots,
        )
        result = _bind_regulation_source(
            result,
            structured_tables_registry,
            cohort=effective_cohort,
            table_type="study_duration",
        )
        return _resolution(lookup_type, "study_duration_lookup", result)

    if lookup_type == "scholarship_classification":
        result = scholarship_classification_lookup(
            query,
            scoring_tables,
            cohort=effective_cohort,
            slots=slots,
        )
        result = _bind_regulation_source(
            result,
            structured_tables_registry,
            cohort=effective_cohort,
            table_type="scholarship",
        )
        return _resolution(
            lookup_type,
            "scholarship_classification_lookup",
            result,
        )

    if lookup_type == "scoring":
        result = structured_lookup_from_slots(
            slots,
            scoring_tables,
            cohort=effective_cohort,
        ) if slots else None
        if result is None:
            from .structured_lookup import structured_lookup
            result = structured_lookup(
                query,
                scoring_tables,
                cohort=effective_cohort,
            )
        operation = str(slots.get("operation") or "")
        subtype_map = {
            "grade_10_to_letter": {
                "grade_scale",
                "grade_10_to_letter",
            },
            "pass_fail_ungraded": {
                "grade_scale",
                "grade_10_to_letter",
                "pass_fail_ungraded",
            },
            "pass_threshold": {
                "grade_scale",
                "grade_10_to_letter",
                "pass_fail_ungraded",
            },
            "letter_to_grade_4": {"letter_to_grade4", "letter_to_grade_4"},
            "academic_classification": {"academic_classification"},
            "conduct_classification": {"conduct_classification", "conduct"},
        }
        canonical_type = (
            "conduct" if operation == "conduct_classification" else "scoring"
        )
        result = _bind_regulation_source(
            result,
            structured_tables_registry,
            cohort=effective_cohort,
            table_type=canonical_type,
            subtypes=subtype_map.get(operation),
        )
        return _resolution(lookup_type, "structured_lookup", result)

    if lookup_type in {"student_service", "office", "faculty"}:
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
            model=model,
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
        if not _result_supports_requested_field(result, requested_field):
            result = None
        elif result is not None:
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
        q_norm = normalize_text(candidate_text)
        scope = str(slots.get("scope") or ("faculty" if "khoa" in q_norm else "school"))
        requested_field = str(slots.get("requested_field") or "")
        if intent == "resolve_faculty" or requested_field == "faculty" or "thuoc khoa" in q_norm or "khoa nao" in q_norm or "o khoa" in q_norm:
            action = "resolve_faculty"
        elif intent == "exists" or requested_field == "exists":
            action = "exists"
        elif intent == "list_items" or requested_field in {"list", "programs", "nganh"} or "danh sach" in q_norm or "cac nganh" in q_norm or "co nhung nganh" in q_norm:
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
        formula_type = str(slots.get("formula_type") or "")
        if formula_type == "scholarship_score":
            result = _bind_regulation_source(
                result,
                structured_tables_registry,
                cohort=effective_cohort,
                table_type="scholarship",
            )
        else:
            result = _bind_regulation_source(
                result,
                structured_tables_registry,
                cohort=effective_cohort,
                table_type="scoring",
                subtypes={"academic_classification"},
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
    lookup_type: str,
    query_text: str,
) -> bool:
    if not resolution or not resolution.result or resolution.result_kind == "clarification":
        return False
    res_data = resolution.result
    if lookup_type in {"office", "faculty", "student_service"}:
        sel_method = res_data.get("selection_method")
        if sel_method == "catalog_fuzzy":
            q_norm = normalize_text(query_text)
            cues = ("email", "sdt", "dien thoai", "dia chi", "o dau", "lien he", "phong", "khoa", "van phong", "trung tam", "tram")
            if not any(cue in q_norm for cue in cues):
                return False
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
        if res_data.get("formula"):
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

    # Dynamic Table Probing for Inter-Table Composite Resolution (Structure A + Structure B)
    query_norm = " " + normalize_text(query) + " "
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

    has_conjunction = any(conj in query_norm for conj in [" va ", " voi ", " cung ", " hoac ", " lan "]) or "," in query
    if has_conjunction or not primary_res or not primary_res.result:
        collected: list[StructuredResolution] = []
        seen_lookups: set[str] = set()
        if primary_res and _is_valid_probe_result(primary_res, primary_res.lookup_type, query):
            collected.append(primary_res)
            seen_lookups.add(primary_res.lookup_type)
            if primary_res.lookup_type in {"office", "faculty", "student_service"}:
                seen_lookups.update({"office", "faculty", "student_service"})

        for cand_type in candidate_domains:
            if cand_type in seen_lookups:
                continue
            cand_res = _resolve_single_lookup(cand_type, **lookup_kwargs)
            if _is_valid_probe_result(cand_res, cand_type, query):
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
                    {
                        "lookup_type": item.lookup_type,
                        "strategy": item.strategy,
                        "table_name": item.result.get("table_name") or item.lookup_type,
                        "data": item.result.get("result") or item.result.get("items") or item.result,
                    }
                    for item in collected
                ],
                "source_pages": sorted(list({p for item in collected for p in (item.result.get("source_pages") or [])})),
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
        elif len(collected) == 1 and not primary_res:
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
