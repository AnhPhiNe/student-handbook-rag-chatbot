from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.common.cohort import valid_cohorts


QUESTION_STYLES = {
    "realistic",
    "paraphrase",
    "typo_no_accent",
    "stress",
    "ambiguous",
    "unanswerable",
}
TOPICS = {
    "hoc_bong",
    "hoc_phi",
    "nghi_hoc",
    "diem",
    "ren_luyen",
    "tot_nghiep",
    "ngoai_ngu",
    "phong_ban",
    "bieu_mau",
    "nganh_hoc",
    "khac",
}
EXPECTED_PATHS = {
    "structured",
    "regulation_rag",
    "mixed",
    "clarify",
    "out_of_domain",
}
COHORT_SENSITIVITY = {
    "none",
    "single_cohort",
    "multi_cohort_risk",
}
QUESTION_SPECIFICITY = {
    "specific",
    "broad",
    "ambiguous",
    "unanswerable",
}
EXPECTED_ANSWER_BEHAVIORS = {
    "direct_answer",
    "scoped_summary",
    "clarify_or_scope",
    "abstain",
}

COMMON_REQUIRED_FIELDS = {
    "id",
    "suite",
    "query",
    "cohort",
    "tags",
    "expected_intent",
    "expected_strategy",
}


def load_json(path: Path) -> Any:
    """Load a UTF-8 JSON artifact."""

    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    """Persist a UTF-8 JSON artifact with stable formatting."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def stable_json_hash(value: Any) -> str:
    """Hash a JSON-compatible value using stable key ordering."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _doc_metadata(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("metadata") or {}


def _doc_id(item: dict[str, Any]) -> str:
    metadata = _doc_metadata(item)
    return str(
        item.get("_id")
        or metadata.get("parent_section_id")
        or item.get("parent_section_id")
        or ""
    ).strip()


def _record_id(record: dict[str, Any]) -> str:
    for key in (
        "record_id",
        "service_id",
        "office_profile_id",
        "faculty_profile_id",
        "program_id",
        "table_id",
        "form_id",
        "rule_id",
        "formula_id",
        "source_record_id",
    ):
        value = record.get(key)
        if value:
            return str(value)
    return ""


def _slug_tail(value: str, prefix: str) -> str:
    if not value.startswith(prefix):
        return ""
    return value[len(prefix) :].strip("_")


def _legacy_structured_record_ids(
    catalog: str,
    record: dict[str, Any],
) -> set[str]:
    """Accept equivalent structured IDs from older frozen holdout manifests.

    Runtime artifacts evolved from per-cohort directory files and extracted
    table IDs into a cleaner shared registry. The holdout still references some
    of those older IDs, so the validator maps them to the same current records
    instead of forcing the dataset to be rewritten.
    """

    ids: set[str] = set()
    cohort = str(record.get("cohort") or "").strip()
    normalized_cohort = _normalize_eval_cohort(cohort)

    for key in (
        "record_id",
        "service_id",
        "office_profile_id",
        "faculty_profile_id",
        "program_id",
        "table_id",
        "form_id",
        "rule_id",
        "formula_id",
        "source_record_id",
    ):
        value = str(record.get(key) or "").strip()
        if value:
            ids.add(value)

    # Preserve explicit aliases when a structured catalog migrates from an
    # older ID scheme.  Unlike positional heuristics, these aliases are
    # source-record metadata and remain valid after records are reordered.
    legacy_ids = record.get("legacy_record_ids") or []
    if isinstance(legacy_ids, str):
        legacy_ids = [legacy_ids]
    if isinstance(legacy_ids, list):
        ids.update(str(value).strip() for value in legacy_ids if str(value).strip())

    table_id = str(record.get("table_id") or "").strip()
    table_subtype = str(record.get("table_subtype") or "").strip()
    source_parent_id = str(record.get("source_parent_id") or "").strip()
    if table_id:
        ids.add(table_id)
    if source_parent_id and table_subtype:
        ids.add(f"{source_parent_id}_{table_subtype}")
        if source_parent_id.startswith("K48-K49_"):
            ids.add(f"{source_parent_id.removeprefix('K48-K49_')}_{table_subtype}")

    if (
        catalog in {"structured_tables_registry", "scoring_tables"}
        and normalized_cohort
    ):
        scoring_table_id = str(record.get("table_id") or "").strip()
        if scoring_table_id in {"grade_10_to_letter", "grade_10_to_letter_foundation"}:
            ids.add(
                f"{normalized_cohort}_QuyCheDaoTao_Chuong3_Dieu10_grade_scale_general"
            )
        if scoring_table_id in {"conduct_classification", "conduct"}:
            ids.add(
                f"{normalized_cohort}_QuyCheDanhGiaKetQuaRenLuyen_Chuong3_Dieu9_conduct_classification"
            )
            ids.add(
                f"{normalized_cohort}_QuyCheDanhGiaRenLuyen_Chuong3_Dieu9_conduct_classification"
            )

    if catalog == "student_faculty_profiles":
        source_record_id = str(record.get("source_record_id") or "").strip()
        profile_id = str(record.get("faculty_profile_id") or "").strip()
        slug = _slug_tail(profile_id, "all_")
        if source_record_id and slug:
            for cohort_alias in valid_cohorts():
                ids.add(f"{cohort_alias}_{slug}")
                ids.add(f"{cohort_alias}_{cohort_alias}_{slug}")

    if catalog == "program_directory":
        record_id = str(record.get("record_id") or "").strip()
        # Program record IDs repeat across handbook editions (for example,
        # ``program_2`` exists in both K50 and K51).  Prefix aliases must
        # therefore use the record's actual cohort.  Adding both K50 and K51
        # for every record made later records overwrite earlier ones in the
        # evaluation source index and could validate a K50 case against K51
        # provenance.
        if record_id and normalized_cohort:
            ids.add(f"{normalized_cohort}_{record_id}")

    ids.discard("")
    return ids


def _structured_catalog_aliases(catalog: str, record: dict[str, Any]) -> set[str]:
    aliases = {catalog}
    aliases.update(
        str(record.get(field) or "").strip()
        for field in ("lookup_group", "table_type", "table_subtype")
        if str(record.get(field) or "").strip()
    )
    default_alias = {
        "student_service_directory": "service",
        "student_office_profiles": "office",
        "student_faculty_profiles": "faculty",
        "program_directory": "program",
        "formula_rules": "formula",
        "foreign_language_equivalency_table": "foreign_language",
    }.get(catalog)
    if default_alias:
        aliases.add(default_alias)
    aliases.discard("")
    if catalog in {"structured_tables_registry", "scoring_tables"}:
        table_type = str(record.get("table_type") or "").strip()
        table_id = str(record.get("table_id") or "").strip()
        table_name = str(record.get("table_name") or "").lower()
        if table_type == "scholarship":
            aliases.add("scholarship")
        elif table_type in {"conduct", "scoring"} or record.get("lookup_group"):
            aliases.add("scoring")
        elif table_type == "study_duration":
            aliases.add("study_duration")
        elif table_type == "foreign_language":
            aliases.add("foreign_language")
        if table_id == "scholarship_classification" or "học bổng" in table_name:
            aliases.add("scholarship")
        if table_id == "conduct_classification" or "rèn luyện" in table_name:
            aliases.update({"conduct", "scoring"})
    return aliases


def _structured_source_index(
    root: Path,
) -> dict[tuple[str, str], dict[str, Any]]:
    relative_paths = {
        "student_service_directory": (
            "data/processed/directories/student_service_directory.json"
        ),
        "student_office_profiles": (
            "data/processed/directories/student_office_profiles.json"
        ),
        "student_faculty_profiles": (
            "data/processed/directories/student_faculty_profiles.json"
        ),
        "program_directory": "data/processed/directories/program_directory.json",
        "structured_tables_registry": (
            "data/processed/tables/structured_tables_registry.json"
        ),
        "formula_rules": "data/processed/tables/formula_rules.json",
        "foreign_language_equivalency_table": (
            "data/processed/tables/foreign_language_equivalency_table.json"
        ),
        "scoring_tables": "data/processed/tables/scoring_tables.json",
    }
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for catalog, relative in relative_paths.items():
        path = root / relative
        if not path.exists():
            continue
        try:
            records = load_json(path)
        except json.JSONDecodeError:
            continue
        if not isinstance(records, list):
            continue
        for record in records:
            if isinstance(record, dict):
                record_id = _record_id(record)
                if record_id:
                    for source_id in _legacy_structured_record_ids(catalog, record):
                        for alias in _structured_catalog_aliases(catalog, record):
                            index[(alias, source_id)] = record
    docstore_path = root / "data/processed/chunks/all_docstore_items.json"
    if docstore_path.exists():
        try:
            docstore = load_json(docstore_path)
        except json.JSONDecodeError:
            docstore = []
        if isinstance(docstore, list):
            for item in docstore:
                if not isinstance(item, dict):
                    continue
                metadata = _doc_metadata(item)
                parent_id = _doc_id(item)
                if "QuyCheDaoTao_Chuong1_Dieu3" not in parent_id:
                    continue
                record = {
                    "record_id": f"{parent_id}_study_duration_chinh_quy",
                    "table_id": f"{parent_id}_study_duration_chinh_quy",
                    "table_type": "study_duration",
                    "table_subtype": "study_duration_chinh_quy",
                    "table_name": "Thời gian học tập chuẩn và tối đa",
                    "cohort": metadata.get("cohort") or item.get("cohort"),
                    "source_parent_id": parent_id,
                    "document_id": metadata.get("document_id")
                    or item.get("document_id"),
                }
                for source_id in _legacy_structured_record_ids(
                    "structured_tables_registry", record
                ):
                    for alias in _structured_catalog_aliases(
                        "structured_tables_registry", record
                    ):
                        index[(alias, source_id)] = record
    return index


def _normalize_eval_cohort(value: Any) -> str | None:
    normalized = str(value or "").strip().upper().replace("_", "-")
    if normalized in {"K48", "K49", "K48-K49", "K49-K48"}:
        return "K48-K49"
    if normalized in {"K50", "K51"}:
        return normalized
    return None


def _structured_record_matches_cohort(
    record: dict[str, Any], expected_cohort: str | None
) -> bool:
    from src.common.cohort import is_cohort_applicable

    return is_cohort_applicable(record, expected_cohort)


def _validate_common(case: dict[str, Any], suite: str, errors: list[str]) -> None:
    missing = sorted(field for field in COMMON_REQUIRED_FIELDS if field not in case)
    if missing:
        errors.append(f"{suite}:{case.get('id', '<missing-id>')}: missing {missing}")
    if case.get("suite") != suite:
        errors.append(
            f"{case.get('id')}: suite={case.get('suite')!r}, expected {suite!r}"
        )
    if not str(case.get("query") or "").strip():
        errors.append(f"{suite}:{case.get('id')}: empty query")
    if not isinstance(case.get("tags"), list):
        errors.append(f"{suite}:{case.get('id')}: tags must be a list")
    if case.get("question_style") not in QUESTION_STYLES:
        errors.append(
            f"{suite}:{case.get('id')}: invalid question_style={case.get('question_style')!r}"
        )
    if case.get("topic") not in TOPICS:
        errors.append(f"{suite}:{case.get('id')}: invalid topic={case.get('topic')!r}")
    if case.get("expected_path") not in EXPECTED_PATHS:
        errors.append(
            f"{suite}:{case.get('id')}: invalid expected_path={case.get('expected_path')!r}"
        )
    if case.get("cohort_sensitivity") not in COHORT_SENSITIVITY:
        errors.append(
            f"{suite}:{case.get('id')}: invalid cohort_sensitivity={case.get('cohort_sensitivity')!r}"
        )
    if case.get("question_specificity") not in QUESTION_SPECIFICITY:
        errors.append(
            f"{suite}:{case.get('id')}: invalid question_specificity={case.get('question_specificity')!r}"
        )
    if case.get("expected_answer_behavior") not in EXPECTED_ANSWER_BEHAVIORS:
        errors.append(
            f"{suite}:{case.get('id')}: invalid expected_answer_behavior={case.get('expected_answer_behavior')!r}"
        )
    if case.get("eval_split") not in {"realistic", "stress"}:
        errors.append(
            f"{suite}:{case.get('id')}: invalid eval_split={case.get('eval_split')!r}"
        )


def _validate_deterministic_contract(case: dict[str, Any], errors: list[str]) -> None:
    """Fail closed when a deterministic case cannot express its V6 gold contract."""
    case_id = str(case.get("id") or "<missing-id>")
    contract = str(case.get("contract_version") or "").strip()
    if not contract.startswith("query-plan-"):
        errors.append(f"{case_id}: invalid deterministic contract_version={contract!r}")

    expected = case.get("expected_plan")
    if not isinstance(expected, dict):
        errors.append(f"{case_id}: expected_plan must be an object")
        return
    required_plan_fields = {
        "task_count",
        "allowed_modes",
        "required_modes",
        "mode_counts",
        "lookup_types",
        "cohorts",
        "out_of_domain",
        "needs_clarification",
    }
    missing_plan_fields = sorted(required_plan_fields - set(expected))
    if missing_plan_fields:
        errors.append(f"{case_id}: expected_plan missing fields {missing_plan_fields}")

    task_count = expected.get("task_count")
    if (
        not isinstance(task_count, int)
        or isinstance(task_count, bool)
        or not 0 <= task_count <= 3
    ):
        errors.append(f"{case_id}: invalid expected_plan.task_count={task_count!r}")
        task_count = None
    allowed_task_modes = {"structured", "rag", "clarify"}
    for field in ("allowed_modes", "required_modes", "lookup_types", "cohorts"):
        value = expected.get(field)
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            errors.append(f"{case_id}: expected_plan.{field} must be a string list")
    allowed_modes_value = expected.get("allowed_modes")
    required_modes_value = expected.get("required_modes")
    allowed_modes = allowed_modes_value if isinstance(allowed_modes_value, list) else []
    required_modes = (
        required_modes_value if isinstance(required_modes_value, list) else []
    )
    if any(mode not in allowed_task_modes for mode in allowed_modes + required_modes):
        errors.append(f"{case_id}: expected_plan contains unsupported task mode")
    if not set(required_modes) <= set(allowed_modes):
        errors.append(f"{case_id}: required_modes must be a subset of allowed_modes")

    mode_counts = expected.get("mode_counts")
    if not isinstance(mode_counts, dict) or any(
        mode not in allowed_task_modes
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 0
        for mode, count in (mode_counts or {}).items()
    ):
        errors.append(f"{case_id}: invalid expected_plan.mode_counts")
    elif task_count is not None and sum(mode_counts.values()) != task_count:
        errors.append(f"{case_id}: mode_counts must sum to task_count")
    for field in ("out_of_domain", "needs_clarification"):
        if not isinstance(expected.get(field), bool):
            errors.append(f"{case_id}: expected_plan.{field} must be boolean")

    expected_tasks = case.get("expected_tasks")
    if not isinstance(expected_tasks, list):
        errors.append(f"{case_id}: expected_tasks must be a list")
        return
    if task_count is not None and len(expected_tasks) != task_count:
        errors.append(f"{case_id}: expected_tasks length must equal task_count")
    for index, task in enumerate(expected_tasks, start=1):
        prefix = f"{case_id}: expected_tasks[{index}]"
        if not isinstance(task, dict):
            errors.append(f"{prefix} must be an object")
            continue
        mode = task.get("mode")
        if mode not in allowed_task_modes:
            errors.append(f"{prefix}.mode is invalid")
        if mode != "clarify" and (
            not isinstance(task.get("intent"), str) or not task.get("intent")
        ):
            errors.append(f"{prefix}.intent must be a non-empty string")
        cohorts = task.get("cohorts")
        if not isinstance(cohorts, list) or any(
            not isinstance(cohort, str) for cohort in cohorts
        ):
            errors.append(f"{prefix}.cohorts must be a string list")
        if mode == "structured" and not str(task.get("lookup_type") or "").strip():
            errors.append(f"{prefix}.lookup_type is required for structured mode")
        if "slots" in task and not isinstance(task.get("slots"), dict):
            errors.append(f"{prefix}.slots must be an object")
        if "required_slot_keys" in task and not isinstance(
            task.get("required_slot_keys"), list
        ):
            errors.append(f"{prefix}.required_slot_keys must be a list")
        if "slot_value_alternatives" in task and not isinstance(
            task.get("slot_value_alternatives"), dict
        ):
            errors.append(f"{prefix}.slot_value_alternatives must be an object")


def _validate_deterministic_v7_contract(
    case: dict[str, Any],
    errors: list[str],
    *,
    expected_contract: str = "query-plan-outcome-equivalent-v7",
) -> None:
    """Validate outcome golds without prescribing one QueryPlan emission.

    V7 deliberately evaluates architectural outcomes.  It may constrain a mode,
    lookup capability or grounded slot when that distinction is material, but it
    does not require an exact task order, task identifier or raw slot spelling.
    """

    case_id = str(case.get("id") or "<missing-id>")
    contract = str(case.get("contract_version") or "").strip()
    if contract != expected_contract:
        errors.append(
            f"{case_id}: invalid deterministic contract={contract!r}; "
            f"expected {expected_contract!r}"
        )

    outcomes = case.get("accepted_outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        errors.append(f"{case_id}: accepted_outcomes must be a non-empty list")
        return

    allowed_states = {"answer", "clarify", "out_of_domain", "safe_unavailable"}
    allowed_modes = {"structured", "rag", "clarify"}
    seen_names: set[str] = set()
    for index, outcome in enumerate(outcomes, start=1):
        prefix = f"{case_id}: accepted_outcomes[{index}]"
        if not isinstance(outcome, dict):
            errors.append(f"{prefix} must be an object")
            continue
        name = str(outcome.get("name") or "").strip()
        if not name:
            errors.append(f"{prefix}.name must be non-empty")
        elif name in seen_names:
            errors.append(f"{prefix}.name is duplicated")
        seen_names.add(name)
        if outcome.get("state") not in allowed_states:
            errors.append(f"{prefix}.state is invalid")

        modes = outcome.get("allowed_modes")
        if not isinstance(modes, list) or any(
            mode not in allowed_modes for mode in modes
        ):
            errors.append(f"{prefix}.allowed_modes must contain supported modes")

        task_count = outcome.get("task_count")
        if task_count is not None:
            if not isinstance(task_count, dict):
                errors.append(f"{prefix}.task_count must be an object")
            else:
                minimum = task_count.get("min")
                maximum = task_count.get("max")
                if (
                    not isinstance(minimum, int)
                    or isinstance(minimum, bool)
                    or not isinstance(maximum, int)
                    or isinstance(maximum, bool)
                    or minimum < 0
                    or maximum > 3
                    or minimum > maximum
                ):
                    errors.append(
                        f"{prefix}.task_count must satisfy 0 <= min <= max <= 3"
                    )

        required_tasks = outcome.get("required_tasks") or []
        if not isinstance(required_tasks, list):
            errors.append(f"{prefix}.required_tasks must be a list")
            continue
        for task_index, task in enumerate(required_tasks, start=1):
            task_prefix = f"{prefix}.required_tasks[{task_index}]"
            if not isinstance(task, dict):
                errors.append(f"{task_prefix} must be an object")
                continue
            mode = task.get("mode")
            if mode not in allowed_modes:
                errors.append(f"{task_prefix}.mode is invalid")
            if mode == "structured" and not str(task.get("lookup_type") or "").strip():
                errors.append(f"{task_prefix}.lookup_type is required")
            for field in ("required_slot_keys", "cohorts"):
                if field in task and (
                    not isinstance(task.get(field), list)
                    or any(not isinstance(item, str) for item in task[field])
                ):
                    errors.append(f"{task_prefix}.{field} must be a string list")
            if "slot_value_alternatives" in task and not isinstance(
                task.get("slot_value_alternatives"), dict
            ):
                errors.append(
                    f"{task_prefix}.slot_value_alternatives must be an object"
                )


def _validate_grounded_deterministic_contract(
    case: dict[str, Any],
    errors: list[str],
    *,
    expected_contract: str,
    require_fact_lock_scope: bool,
) -> None:
    """Validate outcome gold plus optional grounded-execution assertions."""

    _validate_deterministic_v7_contract(
        case,
        errors,
        expected_contract=expected_contract,
    )
    case_id = str(case.get("id") or "<missing-id>")
    for outcome_index, outcome in enumerate(
        case.get("accepted_outcomes") or [], start=1
    ):
        for task_index, task in enumerate(outcome.get("required_tasks") or [], start=1):
            prefix = (
                f"{case_id}: accepted_outcomes[{outcome_index}]"
                f".required_tasks[{task_index}]"
            )
            if "execution_units" in task:
                units = task["execution_units"]
                if (not isinstance(units, list) or not units
                        or any(not isinstance(unit, dict) or "execution_units" in unit for unit in units)):
                    errors.append(f"{prefix}.execution_units must be non-empty flat task objects")
                else:
                    unit_cohorts = [c for unit in units for c in unit.get("cohorts", [])]
                    if (any(len(unit.get("cohorts", [])) != 1 or unit.get("mode") != "structured"
                            or unit.get("lookup_type") != task.get("lookup_type") for unit in units)
                            or sorted(unit_cohorts) != sorted(task.get("cohorts", []))):
                        errors.append(f"{prefix}.execution_units must cover each declared cohort once")
                    _validate_grounded_deterministic_contract(
                        {**case, "id": prefix, "accepted_outcomes": [{
                            "name": "execution-units", "state": "answer", "allowed_modes": ["structured"],
                            "task_count": {"min": len(units), "max": len(units)}, "required_tasks": units}]},
                        errors, expected_contract=expected_contract,
                        require_fact_lock_scope=require_fact_lock_scope,
                    )
            if "expected_source_ids" in task and (
                not isinstance(task.get("expected_source_ids"), list)
                or not task["expected_source_ids"]
                or any(
                    not isinstance(item, str) or not item.strip()
                    for item in task["expected_source_ids"]
                )
            ):
                errors.append(
                    f"{prefix}.expected_source_ids must be a non-empty string list"
                )
            for field in ("expected_evidence_fields", "expected_resolved_fields"):
                if field in task and (
                    not isinstance(task.get(field), dict) or not task[field]
                ):
                    errors.append(f"{prefix}.{field} must be a non-empty object")
            if "expected_evidence_rows" in task and (
                not isinstance(task["expected_evidence_rows"], list)
                or not task["expected_evidence_rows"]
                or any(not isinstance(row, dict) or not row for row in task["expected_evidence_rows"])
            ):
                errors.append(f"{prefix}.expected_evidence_rows must contain non-empty objects")
            if "resolved_result_required" in task and not isinstance(
                task.get("resolved_result_required"), bool
            ):
                errors.append(f"{prefix}.resolved_result_required must be boolean")
            if task.get("mode") != "structured" or not require_fact_lock_scope:
                continue
            fact_lock_applicable = task.get("fact_lock_applicable")
            if not isinstance(fact_lock_applicable, bool):
                errors.append(f"{prefix}.fact_lock_applicable must be boolean")
            elif fact_lock_applicable:
                if task.get("resolved_result_required") is not True:
                    errors.append(
                        f"{prefix}.resolved_result_required must be true when "
                        "fact_lock_applicable=true"
                    )
                if not isinstance(
                    task.get("expected_resolved_fields"), dict
                ) or not task.get("expected_resolved_fields"):
                    errors.append(
                        f"{prefix}.expected_resolved_fields is required when "
                        "fact_lock_applicable=true"
                    )
            elif (
                "expected_resolved_fields" in task
                or task.get("resolved_result_required") is True
            ):
                errors.append(
                    f"{prefix} must not assert resolved_result when "
                    "fact_lock_applicable=false"
                )


def _validate_deterministic_v8_contract(
    case: dict[str, Any], errors: list[str]
) -> None:
    """Validate V8 grounded execution assertions."""

    _validate_grounded_deterministic_contract(
        case,
        errors,
        expected_contract="query-plan-grounded-outcome-v8",
        require_fact_lock_scope=False,
    )


def _validate_deterministic_v9_contract(
    case: dict[str, Any], errors: list[str]
) -> None:
    """Validate V9 grounded assertions and explicit fact-lock applicability."""

    _validate_grounded_deterministic_contract(
        case,
        errors,
        expected_contract="query-plan-grounded-outcome-v9",
        require_fact_lock_scope=True,
    )


