from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from src.common.cohort import (
    is_cohort_applicable,
    is_validated_source_applicable,
    normalize_cohort,
    valid_cohorts,
)
from src.common.score import grounded_score, parse_score
from src.common.text import slot_values

from .formula_lookup import formula_lookup
from .foreign_language_lookup import foreign_language_lookup, is_reference_level_selector
from .catalog_relationship import resolve_relationship
from .directory_selector import DirectorySelector
from .office_lookup import normalize_text, office_lookup
from .program_lookup import program_lookup
from .ordinal_labels import annotate_minimum_levels
from .scholarship_lookup import scholarship_table_lookup
from .study_duration_lookup import study_duration_lookup
from .structured_lookup import scoring_lookup_from_reference
from .structured_routing import load_lookup_registry, validate_fact_lock_inputs, validate_structured_task


_REGISTRY = load_lookup_registry()
_LOOKUP_TOOL_SPECS = _REGISTRY.get("tools", {})
_RELATIONSHIPS = _REGISTRY.get("relationships", {})
# Lookups answered from regulation tables, with the table types each reads.
_REFERENCE_TABLE_TYPES: dict[str, set[str]] = {
    name: set(spec["table_types"])
    for name, spec in _LOOKUP_TOOL_SPECS.items()
    if spec.get("table_types")
}


@dataclass(frozen=True)
class StructuredResolution:
    """Carry deterministic lookup output and its supporting evidence."""

    lookup_type: str
    strategy: str
    result_kind: str
    result: dict[str, Any]
    target_chunk_types: list[str]

    @property
    def resolution_status(self) -> str:
        """Separate evidence availability from a uniquely resolved value."""
        if self.result_kind == "clarification":
            return "needs_clarification"
        if self.result_kind == "unavailable":
            return "unavailable"
        return "resolved" if self.result.get("resolved_result") else "evidence_only"


def _slot_value(task: dict[str, Any], *names: str) -> str | list[str]:
    """The first non-empty slot among `names` (literal span first); a list of names stays a list."""
    spans = task.get("slot_spans") or {}
    slots = task.get("slots") or {}
    for name in names:
        for source in (spans, slots):
            value = source.get(name)
            values = [str(item).strip() for item in slot_values(value) if str(item).strip()]
            if values:
                return values if isinstance(value, list) else values[0]
    return ""


def _formula_article_number(result: dict[str, Any]) -> str | None:
    match = re.search(
        r"\bĐiều\s+(\d+)\b", str(result.get("source_article") or ""), re.IGNORECASE
    )
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
            if str(
                table.get("source_parent_id") or table.get("source_section_id") or ""
            )
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
                str(
                    table.get("source_parent_id")
                    or table.get("source_section_id")
                    or ""
                )
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
        {page for table in candidates for page in table.get("source_pages") or []}
    )
    return bound


def _reference_component_gap(
    lookup_type: str,
    *,
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

    entity_norms = [normalize_text(value) for value in slot_values(slots.get("certificate_or_language"))
                    if value is not None and str(value).strip()]
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
                and entity_norm
                and (candidate_norm in entity_norm or entity_norm in candidate_norm)
                for candidate_norm in map(normalize_text, declared_names)
                for entity_norm in entity_norms
            ):
                input_rows.append(row)

    if not input_rows:
        return None

    requirements = input_rows[0].get("input_requirements") or {}
    component_slots = requirements.get("component_slots") or {}
    required_slots = {
        str(component): str((component_slots.get(component) or {}).get("slot") or f"{component}_score")
        for component in requirements.get("required_components") or []
    }

    def has_score(value: Any) -> bool:
        # Requested field/level names are selectors, not personal operands.
        # Accept only a scalar number, optionally labelled with the score unit.
        return bool(re.fullmatch(
            r"(?:diem\s*)?[+-]?\d+(?:[.,]\d+)?(?:\s*diem)?",
            normalize_text(str(value).replace(",", ".")) if value is not None else "",
        ))

    runtime_slots = slots
    if not has_score(runtime_slots.get("score_or_level")) and not any(
        has_score(runtime_slots.get(name)) for name in required_slots.values()
    ):
        return None

    missing: list[dict[str, str]] = []
    for component in requirements.get("required_components") or []:
        spec = component_slots.get(component) or {}
        slot_name = required_slots[str(component)]
        if not has_score(runtime_slots.get(slot_name)):
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
            f"Bạn vui lòng cung cấp điểm riêng cho các kỹ năng còn thiếu: {labels}."
        ),
        "content_type": "structured_lookup_clarification",
    }


def _reference_input_clarification(
    lookup_type: str,
    *,
    candidates: list[dict[str, Any]],
    cohort: str | None,
    slots: dict[str, Any],
) -> dict[str, Any] | None:
    gap = _reference_component_gap(
        lookup_type, candidates=candidates, cohort=cohort, slots=slots,
    )
    # Candidates are already cohort-scoped. Reuse the certificate lookup's row
    # selection: a JLPT N3 column must not exempt a TOEIC score requirement.
    selected = foreign_language_lookup("", candidates, slots=slots) if gap is not None else None
    if gap is not None and is_reference_level_selector(
        slots.get("score_or_level"), (selected or {}).get("items") or [],
    ):
        # A requested reference column needs no personal score for every skill.
        # Partial scores remain context, not proof of a personal equivalency.
        return None
    return gap


def _matches_reference_spec(table: dict[str, Any], spec: dict[str, Any]) -> bool:
    """Match one complete registry selector, never a cross-product of fields."""
    for key, table_key in (("table_types", "table_type"), ("table_subtypes", "table_subtype")):
        if spec.get(key) and table.get(table_key) not in spec[key]:
            return False
    suffixes = tuple(spec.get("table_id_suffixes") or [])
    return not suffixes or str(table.get("table_id") or "").endswith(suffixes)


def _select_reference_tables(
    lookup_type: str,
    slots: dict[str, Any] | None,
    tables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Select canonical tables once for both evidence and value resolution."""
    candidates = tables
    runtime_slots = slots or {}
    tool = _LOOKUP_TOOL_SPECS.get(lookup_type, {})
    for selector_name in ("table_selector", "scope_selector"):
        selector = tool.get(selector_name) or {}
        applicable_operations = selector.get("applies_to_operations")
        selector_input = runtime_slots.get(selector.get("slot"))
        if isinstance(selector_input, list):
            selector_values = [str(value) for value in selector_input if str(value).strip()]
        elif selector_input is None or not str(selector_input).strip():
            selector_values = []
        else:
            selector_values = [str(selector_input)]
        specs = [
            (selector.get("values") or {}).get(value)
            for value in selector_values
        ]
        specs = [spec for spec in specs if isinstance(spec, dict)]
        if not specs:
            continue
        scoped_operation_specs = []
        if applicable_operations:
            operation_specs = (tool.get("table_selector") or {}).get("values") or {}
            operations = slot_values(runtime_slots.get("operation")) or list(operation_specs)
            scoped_operation_specs = [operation_specs[operation] for operation in operations
                                      if operation in applicable_operations and operation in operation_specs]

        # A list of selector values means the union of complete selector
        # specifications.  Combining each field independently would create a
        # cross-product and could select a table that matches no real value.
        candidates = [
            table for table in candidates
            if (applicable_operations and not any(
                _matches_reference_spec(table, spec) for spec in scoped_operation_specs
            )) or any(_matches_reference_spec(table, spec) for spec in specs)
        ]
    return candidates


def _rows_resolved_in_table(
    lookup_type: str,
    table: dict[str, Any],
    *,
    slots: dict[str, Any],
    cohort: str | None,
) -> list[dict[str, Any]] | None:
    """Resolve the row an operand selects inside one of several applicable tables.

    Scoring is the only lookup where several applicable tables mean several
    *mutually exclusive* answers to the same question: K51 grades foundation
    and remaining courses on different scales, so 5,2 is Dat in one table and
    Khong dat in the other. Without a course_scope slot the dispatcher cannot
    tell which one the student means, so it keeps them all and locks no fact.
    Picking the row inside each table is still arithmetic, and arithmetic
    belongs to the resolver rather than to a composer reading intervals out of
    a rendered table.

    Other lookups are excluded because their multiple tables are complementary,
    not exclusive: a scholarship question returns the amount, classification,
    eligibility and formula tables, which describe different facets and have no
    single row to resolve.
    """

    if lookup_type != "scoring" or not slots:
        return None
    resolved = scoring_lookup_from_reference(slots, table, cohort=cohort)
    if not resolved:
        return None
    items = resolved.get("items")
    if isinstance(items, list):
        return [row for row in items if isinstance(row, dict)] or None
    result = resolved.get("result")
    return [result] if isinstance(result, dict) else None


def _reference_table_lookup(
    lookup_type: str,
    *,
    query: str,
    candidates: list[dict[str, Any]],
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

    effective_cohort = normalize_cohort(cohort)
    if not candidates:
        return None

    clarification = _reference_input_clarification(
        lookup_type,
        candidates=candidates,
        cohort=effective_cohort,
        slots=slots,
    )
    if clarification is not None:
        return clarification

    candidates = sorted(candidates,
        key=lambda table: (
            str(table.get("cohort") or ""),
            str(table.get("table_subtype") or ""),
            str(table.get("table_id") or ""),
        )
    )
    leaf_lookups: list[dict[str, Any]] = []
    for table in candidates:
        rows = annotate_minimum_levels(
            [dict(row) for row in table.get("rows") or [] if isinstance(row, dict)]
        )
        source_section = table.get("source_parent_id") or table.get("source_section_id")
        resolved_rows = (
            _rows_resolved_in_table(lookup_type, table, slots=slots, cohort=cohort)
            if len(candidates) > 1
            else None
        )
        leaf_lookups.append(
            {
                "lookup_type": lookup_type,
                "input_value": query,
                "result": {
                    "table_id": table.get("table_id"),
                    "table_subtype": table.get("table_subtype"),
                    "rows": rows,
                    **({"resolved_rows": resolved_rows} if resolved_rows else {}),
                },
                **({"resolved_rows": resolved_rows} if resolved_rows else {}),
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
                    **(
                        {"resolved_rows": item["resolved_rows"]}
                        if item.get("resolved_rows")
                        else {}
                    ),
                }
                for item in leaf_lookups
            ],
            "table_count": len(leaf_lookups),
        },
        "sub_lookups": leaf_lookups,
        "source_pages": sorted(
            {page for item in leaf_lookups for page in item.get("source_pages") or []}
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
    selected_tables: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Resolve only inside the single canonical table selected for evidence."""

    if len(selected_tables) != 1:
        return None
    if _has_multiple_result_choices(lookup_type, slots):
        return None

    if lookup_type == "scoring":
        resolved = (
            scoring_lookup_from_reference(slots, selected_tables[0], cohort=cohort)
            if slots
            else None
        )
        if not resolved:
            return None
        items = resolved.get("items")
        if isinstance(items, list):
            return resolved if len(items) == 1 else None
        # Scalar scoring resolvers expose one deterministic result mapping
        # rather than an ``items`` collection.
        return resolved if isinstance(resolved.get("result"), dict) else None

    if lookup_type == "foreign_language":
        if _reference_component_gap(
            lookup_type, candidates=selected_tables, cohort=cohort, slots=slots,
        ) is not None:
            return None  # Partial personal scores may show thresholds, never a fact lock.
        resolved = foreign_language_lookup(
            query,
            selected_tables,
            cohort=cohort,
            slots=slots,
        )
        return resolved if resolved and resolved.get("result_count") == 1 else None

    if lookup_type == "study_duration":
        resolved = study_duration_lookup(
            query,
            selected_tables,
            cohort=cohort,
            slots=slots,
        )
        tables = ((resolved or {}).get("result") or {}).get("tables") or []
        row_count = sum(len(table.get("rows") or []) for table in tables)
        return resolved if resolved and row_count == 1 else None

    if lookup_type == "scholarship_classification":
        aspect = str(slots.get("aspect") or "")
        table_id = {
            "amount": "scholarship_amount",
            "classification": "scholarship_classification",
        }.get(aspect)
        if table_id is None or not slots.get("score_or_label"):
            return None
        resolved = scholarship_table_lookup(
            query,
            selected_tables,
            cohort=cohort,
            slots=slots,
            table_id=table_id,
        )
        return resolved if resolved and len(resolved.get("items") or []) == 1 else None

    return None


def _has_multiple_result_choices(
    lookup_type: str,
    slots: dict[str, Any] | None,
) -> bool:
    """Return whether result-affecting slots contain distinct inputs."""

    if not isinstance(slots, dict):
        return False
    slot_schema = (_LOOKUP_TOOL_SPECS.get(lookup_type) or {}).get("slot_schema") or {}
    for slot_name, slot_value_spec in slot_schema.items():
        if str((slot_value_spec or {}).get("verification_role") or "result_input") == "reading_intent":
            continue
        value = slots.get(slot_name)
        if not isinstance(value, list):
            continue
        choices = {
            normalize_text(item).strip()
            for item in value
            if item is not None and normalize_text(item).strip()
        }
        if (
            lookup_type == "foreign_language"
            and slot_name == "certificate_or_language"
        ):
            # Multiple certificate names may identify one combined catalog
            # row. The foreign-language resolver checks actual row cardinality.
            continue
        if (
            lookup_type == "foreign_language"
            and slot_name == "score_or_level"
            and choices
            and choices <= {"bac 3", "bac 4"}
        ):
            # These are requested output columns from one certificate row, not
            # multiple personal scores to evaluate.
            continue
        if len(choices) > 1:
            return True
    return False


def resolve_structured_task(
    task: dict[str, Any],
    *,
    query: str,
    cohort: str | None,
    formula_rules: list[dict[str, Any]],
    office_directory: list[dict[str, Any]],
    student_service_directory: list[dict[str, Any]],
    student_faculty_profiles: list[dict[str, Any]] | None,
    structured_tables_registry: list[dict[str, Any]],
    program_directory: list[dict[str, Any]],
    directory_selector: DirectorySelector | None = None,
    grounding: str | None = None,
) -> StructuredResolution | None:
    """Run one validated structured task with the resolver for its lookup family.

    ``query`` is the task's question. ``grounding`` is the student's own words
    (see `grounding_text`); a table row is pinned only from values found there.
    It defaults to ``query`` for callers that run a task on its own.

    Four families: reference tables (scoring, scholarship, foreign language,
    study duration and the other regulation tables), directories (student
    services, offices, faculties), the program catalog, and formulas. A
    ``None`` has no classified cause and must not trigger a fallback. A known
    missing source returns an unavailable result; ambiguity returns clarification.
    """

    lookup_type = str(task.get("lookup_type") or "").strip()
    if not lookup_type:
        return None
    effective_cohort = normalize_cohort(cohort or task.get("cohort"))
    # The dispatcher executes only the normalized runtime payload. Missing and
    # explicitly empty mappings are both authoritative.
    slots = task.get("slots") or {}
    if not isinstance(slots, dict):
        slots = {}

    if lookup_type in _REFERENCE_TABLE_TYPES:
        return _resolve_reference_table(
            lookup_type, task, slots, query=query, grounding=grounding or query, cohort=effective_cohort,
            structured_tables_registry=structured_tables_registry,
        )
    directories = {
        "student_service": student_service_directory,
        "office": office_directory,
        "faculty": student_faculty_profiles or [],
    }
    if lookup_type in directories:
        return _resolve_directory(
            lookup_type, task, slots, query=query, cohort=effective_cohort,
            directories=directories, directory_selector=directory_selector, grounding=grounding or query,
        )
    if lookup_type == "program":
        return _resolve_program(
            task, slots, query=query, cohort=effective_cohort,
            program_directory=program_directory,
            faculty_profiles=student_faculty_profiles or [], grounding=grounding or query,
            directory_selector=directory_selector,
        )
    if lookup_type == "formula":
        if formula_rules and not any(is_validated_source_applicable(rule, effective_cohort) for rule in formula_rules):
            return _missing_source(task, query, effective_cohort, grounding or query, formula_rules)
        result = formula_lookup(query, formula_rules, cohort=effective_cohort, slots=slots)
        result = _bind_formula_source(result, structured_tables_registry, cohort=effective_cohort)
        return _resolution(lookup_type, "formula_lookup", result, result_kind="formula")
    return None


def _resolve_reference_table(
    lookup_type: str,
    task: dict[str, Any],
    slots: dict[str, Any],
    *,
    query: str,
    grounding: str,
    cohort: str | None,
    structured_tables_registry: list[dict[str, Any]],
) -> StructuredResolution | None:
    """Return every applicable reference table, and pin a row when exactly one fits.

    The composer always receives the complete tables. When the task's values
    are grounded in the student's words and select exactly one row, that row is
    also attached as `resolved_result` (the fact lock), and the answer must
    state it.
    """
    resolution_slots = _grounded_resolution_slots(task, slots, grounding) if lookup_type == "scoring" else slots
    family = [
        table for table in structured_tables_registry
        if table.get("data_category") == "regulation_table"
        and table.get("table_type") in _REFERENCE_TABLE_TYPES[lookup_type]
    ]
    scoped = [table for table in family if is_validated_source_applicable(table, cohort)]
    if family and not scoped:
        return _missing_source(task, query, cohort, grounding, family)
    if any(not isinstance(table.get("rows"), list) or not table["rows"]
           or not all(isinstance(row, dict) and row for row in table["rows"])
           for table in scoped):
        return _unavailable(lookup_type, cohort, "invalid_catalog")
    candidates = _select_reference_tables(lookup_type, slots, scoped)
    if scoped and not candidates:
        return _unavailable(lookup_type, cohort, "selector_conflict")
    result = _reference_table_lookup(
        lookup_type,
        query=query,
        candidates=candidates,
        cohort=cohort,
        slots=resolution_slots,
    )
    # Keep the complete reference table for UI rendering, but expose a
    # deterministic fact lock when an existing domain resolver identifies
    # exactly one row. Ungrounded, invalid, or non-unique lookups stay unlocked.
    if (
        result is not None
        and not result.get("needs_clarification")
        and not validate_fact_lock_inputs(task, query=grounding)
    ):
        resolved_result = _unique_reference_resolution(
            lookup_type,
            query=query,
            slots=resolution_slots,
            cohort=cohort,
            selected_tables=candidates,
        )
        if resolved_result is not None:
            source = candidates[0]
            result = dict(result)
            result["resolved_result"] = {
                **resolved_result,
                "cohort": cohort,
                "source_cohort": source.get("source_cohort") or source.get("cohort"),
                "table_id": source.get("table_id"),
                "source_parent_id": source.get("source_parent_id") or source.get("source_section_id"),
            }
    # A planner-supplied request for missing information is not a resolved
    # lookup merely because a reference table can be displayed. Do not
    # infer personal intent from keywords or make list requests clarify.
    clarification = task.get("clarification_question")
    if (result is not None and not result.get("needs_clarification")
            and not result.get("resolved_result")
            and task.get("intent") == "direct_value"
            and isinstance(clarification, str) and clarification.strip()):
        result = {
            "lookup_type": lookup_type, "cohort": cohort,
            "needs_clarification": True,
            "clarification_question": clarification.strip(),
            "content_type": "structured_lookup_clarification",
        }
    return _resolution(
        lookup_type,
        "reference_table_lookup",
        result,
        result_kind=_result_kind(result),
        target_chunk_types=["structured_lookup"],
    )


def _grounded_resolution_slots(
    task: dict[str, Any],
    slots: dict[str, Any],
    grounding: str,
) -> dict[str, Any]:
    """The scoring slots a row may be computed from: operands grounded in the student's words.

    Each numeric score must appear in them (with its scale, e.g.
    "3,6/4", when the student wrote one). If any does not, no slots are
    returned: the tables are still shown as evidence but no row is computed.
    """
    if slots.get("score_or_grade") is None:
        return slots
    operands = slots["score_or_grade"]
    values = operands if isinstance(operands, list) else [operands]
    grounded_values = []
    for value in values:
        if parse_score(value) is None:
            grounded_values.append(value)
            continue
        score = grounded_score(
            value, (task.get("slot_spans") or {}).get("score_or_grade"), grounding,
        )
        if score is None:
            return {}
        grounded_values.append(
            f"{score.value}/{score.scale}" if score.scale is not None else str(score.value)
        )
    if not grounded_values:
        return {}
    # Never discard a denominator present in the original task.
    return {**slots, "score_or_grade": grounded_values if isinstance(operands, list) else grounded_values[0]}


_DIRECTORY_CANDIDATE_SLOT = {"student_service": "service", "office": "office", "faculty": "faculty"}
_DIRECTORY_STRATEGY = {
    "student_service": "student_service_lookup",
    "office": "office_lookup",
    "faculty": "faculty_lookup",
}
_DIRECTORY_CONTENT_TYPES = {
    "student_service": ["student_service_directory", "student_office_profile"],
    "office": ["student_office_profile"],
    "faculty": ["student_faculty_profile"],
}


def _resolve_directory(
    lookup_type: str,
    task: dict[str, Any],
    slots: dict[str, Any],
    *,
    query: str,
    cohort: str | None,
    directories: dict[str, list[dict[str, Any]]],
    directory_selector: DirectorySelector | None,
    grounding: str,
) -> StructuredResolution | None:
    """Find the service, office or faculty the student names; ask when it is unclear."""
    candidate_text = (
        _slot_value(task, _DIRECTORY_CANDIDATE_SLOT[lookup_type], "faculty", "office", "program_or_faculty")
        or query
    )
    result = office_lookup(
        query,
        directories[lookup_type],
        candidate_text=candidate_text,
        lookup_type=lookup_type,
        cohort=cohort,
        selector=directory_selector,
    )
    # A configured selector's verified NONE differs from unknown resolution.
    # Empty catalogs or unavailable/ambiguous selectors cannot authorize RAG.
    if result is None and directory_selector is not None and any(
        is_validated_source_applicable(item, cohort) for item in directories[lookup_type]
    ):
        return _missing_source(task, query, cohort, grounding, directories[lookup_type])
    if result is not None and result.get("resolution_status") in {"ambiguous", "unresolved"}:
        options = result.get("clarification_options") or []
        if options:
            result["clarification_question"] = (
                "Câu hỏi của bạn liên quan đến nhiều đơn vị. Bạn cần hỗ trợ cụ thể về mảng nào dưới đây?\n\n"
                + "\n".join(options)
            )
        else:
            result["clarification_question"] = (
                f"Mình chưa xác định được đơn vị ứng với \"{result.get('candidate_text')}\". "
                "Bạn ghi rõ tên đơn vị hoặc việc cần hỗ trợ giúp mình nhé."
            )
        return _resolution(
            lookup_type,
            "office_lookup_clarification",
            result,
            result_kind="clarification",
            target_chunk_types=[],
        )
    requested_field = slots.get("requested_field") or ""
    # A grounded directory record remains valid structured evidence even
    # when it does not contain the optional field requested by the user.
    # The Composer receives the record and must state that the available
    # evidence does not provide that field instead of inventing a value.
    if result is not None:
        result["requested_field"] = (
            list(requested_field) if isinstance(requested_field, list)
            else str(requested_field)
        )
        result = resolve_relationship(
            result, source_lookup=lookup_type,
            requested_field=requested_field, cohort=cohort,
            relationships=_RELATIONSHIPS,
            catalogs=directories,
        )
    return _resolution(
        lookup_type,
        _DIRECTORY_STRATEGY[lookup_type],
        result,
        result_kind=_result_kind(result),
        target_chunk_types=_DIRECTORY_CONTENT_TYPES[lookup_type],
    )


def _resolve_program(
    task: dict[str, Any],
    slots: dict[str, Any],
    *,
    query: str,
    cohort: str | None,
    program_directory: list[dict[str, Any]],
    faculty_profiles: list[dict[str, Any]],
    directory_selector: DirectorySelector | None,
    grounding: str,
) -> StructuredResolution | None:
    """Answer from the program catalog: does a program exist, list them, or find its faculty."""
    candidate_text = _slot_value(task, "program_or_faculty") or query
    intent = task.get("intent")
    scope = str(slots.get("scope") or "school")
    requested_field = slots.get("requested_field") or ""
    requested = set(requested_field) if isinstance(requested_field, list) else {str(requested_field)}
    if "faculty" in requested or requested & {"email", "phone", "website", "office", "all"}:
        action = "resolve_faculty"
    elif intent == "exists" or "exists" in requested:
        action = "exists"
    elif intent == "list_items" or "programs" in requested:
        action = "list"
    else:
        action = "resolve_faculty"
    result = program_lookup(
        program_directory,
        candidate_text=candidate_text,
        cohort=cohort,
        action=action,
        scope=scope,
        selector=directory_selector,
    )
    if result is None and directory_selector is not None and program_directory:
        return _missing_source(task, query, cohort, grounding, program_directory)
    if result is not None:
        result = resolve_relationship(
            result, source_lookup="program", requested_field=requested_field,
            cohort=cohort, relationships=_RELATIONSHIPS,
            catalogs={"faculty": faculty_profiles, "program": program_directory},
        )
    return _resolution("program", "program_lookup", result, result_kind=_result_kind(result))


def _result_kind(result: dict[str, Any] | None) -> str:
    return "clarification" if result and result.get("needs_clarification") else "structured"


def _unavailable(lookup_type: str, cohort: str | None, reason: str) -> StructuredResolution:
    """Keep a known failure cause without changing the resolver interface."""
    return StructuredResolution(
        lookup_type=lookup_type, strategy="structured_lookup", result_kind="unavailable",
        result={"lookup_type": lookup_type, "cohort": cohort, "unavailable_reason": reason},
        target_chunk_types=[],
    )


def _missing_source(
    task: dict[str, Any], query: str, cohort: str | None, grounding: str,
    catalog: list[dict[str, Any]],
) -> StructuredResolution:
    """Only a validated request with no pending clarification may fall back."""
    errors = validate_structured_task({**task, "cohort": cohort}, query=query, grounding_context=grounding)
    lookup_type = str(task.get("lookup_type") or "")
    # Missing cohort/identity/content is corruption or an unknown source, not
    # proof that this cohort has no answer. Fail closed before authorizing RAG.
    identity_fields = {
        "formula": "rule_id", "program": "program_name", "student_service": "service",
        "office": "unit_name", "faculty": "unit_name",
    }
    healthy = bool(catalog) and all(
        isinstance(item, dict) and normalize_cohort(item.get("cohort")) in valid_cohorts()
        and item.get(identity_fields.get(lookup_type, "table_id"))
        and (item.get("source_parent_id") or item.get("document_id") or item.get("source_pages"))
        and (bool(item.get("formula_text")) if lookup_type == "formula" else
             bool(item.get("raw_text") and item.get("faculty_name")) if lookup_type == "program" else
             (isinstance(item.get("rows"), list) and bool(item["rows"])
              and all(isinstance(row, dict) and row for row in item["rows"]))
             if lookup_type in _REFERENCE_TABLE_TYPES else
             bool(item.get("raw_text") or item.get("service") or item.get("phones") or item.get("emails")))
        for item in catalog
    )
    reason = ("invalid_catalog" if not healthy else
              "invalid_input" if errors or task.get("clarification_question") else "no_source")
    return _unavailable(lookup_type, cohort, reason)


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
        target_chunk_types=target_chunk_types
        or [str(result.get("content_type") or "structured_lookup")],
    )
