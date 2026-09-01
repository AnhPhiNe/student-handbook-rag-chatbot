from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from src.common.cohort import valid_cohorts


EXPECTED_CASE_COUNTS = {
    "deterministic": 120,
    "retrieval": 180,
    "answers": 100,
    "production": 60,
}

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

DATASET_FILES = {
    "deterministic": "deterministic_tool_cases.json",
    "retrieval": "retrieval_cases.json",
    "answers": "generated_answer_cases.json",
    "production": "production_cases.json",
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
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def stable_json_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_query(value: str) -> str:
    value = re.sub(r"^\s*case\s+\d+\s*:\s*", "", value, flags=re.IGNORECASE)
    text = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


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


def _judgment_ids(case: dict[str, Any]) -> list[str]:
    return [
        str(item.get("parent_section_id") or "").strip()
        for item in case.get("relevance_judgments", [])
        if isinstance(item, dict) and str(item.get("parent_section_id") or "").strip()
    ]


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

    if catalog in {"structured_tables_registry", "scoring_tables"} and normalized_cohort:
        scoring_table_id = str(record.get("table_id") or "").strip()
        if scoring_table_id in {"grade_10_to_letter", "grade_10_to_letter_foundation"}:
            ids.add(f"{normalized_cohort}_QuyCheDaoTao_Chuong3_Dieu10_grade_scale_general")
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


def _structured_catalog_aliases(
    catalog: str, record: dict[str, Any]
) -> set[str]:
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


def _structured_source_ids(root: Path) -> set[str]:
    return {record_id for _, record_id in _structured_source_index(root)}


def _normalize_eval_cohort(value: Any) -> str | None:
    normalized = str(value or "").strip().upper().replace("_", "-")
    if normalized in {"K48", "K49", "K48-K49", "K49-K48"}:
        return "K48-K49"
    if normalized in {"K50", "K51"}:
        return normalized
    return None


def _query_cohorts(query: str) -> set[str]:
    return {
        cohort
        for match in re.findall(
            r"\bK(?:48(?:\s*[-/]\s*K?49)?|49|50|51)\b",
            query,
            flags=re.IGNORECASE,
        )
        if (cohort := _normalize_eval_cohort(match.replace(" ", "")))
    }


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


def _validate_deterministic_contract(
    case: dict[str, Any], errors: list[str]
) -> None:
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
        errors.append(
            f"{case_id}: expected_plan missing fields {missing_plan_fields}"
        )

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
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
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
    case: dict[str, Any], errors: list[str]
) -> None:
    """Validate V7 outcome golds without prescribing one QueryPlan emission.

    V7 deliberately evaluates architectural outcomes.  It may constrain a mode,
    lookup capability or grounded slot when that distinction is material, but it
    does not require an exact task order, task identifier or raw slot spelling.
    """

    case_id = str(case.get("id") or "<missing-id>")
    contract = str(case.get("contract_version") or "").strip()
    if contract != "query-plan-outcome-equivalent-v7":
        errors.append(f"{case_id}: invalid V7 deterministic contract={contract!r}")

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
        if not isinstance(modes, list) or any(mode not in allowed_modes for mode in modes):
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
                    errors.append(f"{prefix}.task_count must satisfy 0 <= min <= max <= 3")

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
                errors.append(f"{task_prefix}.slot_value_alternatives must be an object")


def validate_bundle(
    bundle_dir: Path,
    docstore_path: Path,
    *,
    require_frozen: bool = True,
    enforce_docstore_hash: bool = True,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    datasets: dict[str, list[dict[str, Any]]] = {}

    for suite, filename in DATASET_FILES.items():
        path = bundle_dir / filename
        if not path.exists():
            errors.append(f"missing dataset: {path}")
            datasets[suite] = []
            continue
        value = load_json(path)
        if not isinstance(value, list):
            errors.append(f"dataset must be a JSON list: {path}")
            datasets[suite] = []
            continue
        datasets[suite] = value
        # Architecture-aligned regression bundles may deliberately add cases to
        # cover QueryPlan scenarios that did not exist in the legacy v9 suite.
        # The manifest is loaded below, so defer count validation until its
        # versioned contract is available.
        expected_count = None


    manifest_path = bundle_dir / "manifest.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else {}
    if not manifest:
        errors.append("missing manifest.json")
    if require_frozen and not manifest.get("frozen"):
        errors.append("manifest must set frozen=true")
    if manifest.get("generation_model") != "gemini-3.1-flash-lite":
        errors.append("manifest generation_model must be gemini-3.1-flash-lite")
    if manifest.get("judge_model") != "openai/gpt-oss-120b":
        errors.append("manifest judge_model must be openai/gpt-oss-120b")
    if manifest.get("counts") != EXPECTED_CASE_COUNTS:
        manifest_counts = manifest.get("counts") or {}
        if set(manifest_counts) != set(EXPECTED_CASE_COUNTS):
            errors.append(f"manifest counts mismatch: {manifest.get('counts')}")
    expected_counts = manifest.get("counts") or EXPECTED_CASE_COUNTS
    for suite, cases in datasets.items():
        expected_count = expected_counts.get(suite)
        if expected_count is None or len(cases) != int(expected_count):
            errors.append(
                f"{suite}: expected {expected_count} cases, found {len(cases)}"
            )
    if manifest.get("docstore_hash") and manifest.get("docstore_hash") != file_hash(
        docstore_path
    ):
        message = "manifest docstore hash mismatch"
        if enforce_docstore_hash:
            errors.append(message)
        else:
            warnings.append(message)

    docstore = load_json(docstore_path)
    docs_by_id = {_doc_id(item): item for item in docstore if _doc_id(item)}
    project_root = docstore_path.parents[3]
    structured_source_index = _structured_source_index(project_root)
    structured_ids = {record_id for _, record_id in structured_source_index}
    strict_structured_sources = bool(manifest.get("strict_structured_sources"))
    strict_cohort_conflicts = bool(manifest.get("strict_cohort_conflicts"))
    strict_query_duplicates = bool(manifest.get("strict_query_duplicates"))

    seen_ids: set[str] = set()
    normalized_queries: list[tuple[str, str, bool, str | None]] = []
    parent_usage: dict[tuple[str, str], set[str]] = {}

    for suite, cases in datasets.items():
        for case in cases:
            _validate_common(case, suite, errors)
            case_id = str(case.get("id") or "")
            if case_id in seen_ids:
                errors.append(f"duplicate case id: {case_id}")
            seen_ids.add(case_id)
            normalized = normalize_query(str(case.get("query") or ""))
            normalized_queries.append(
                (
                    case_id,
                    normalized,
                    bool(case.get("near_duplicate_reviewed", False)),
                    str(case.get("duplicate_group") or "").strip() or None,
                )
            )
            explicit_cohorts = _query_cohorts(str(case.get("query") or ""))
            selected_cohort = _normalize_eval_cohort(case.get("cohort"))
            cohort_conflict = bool(
                explicit_cohorts
                and selected_cohort
                and selected_cohort not in explicit_cohorts
            )
            if (
                cohort_conflict
                and case.get("expected_path") != "clarify"
                and not case.get("cohort_conflict_reviewed")
            ):
                message = (
                    f"{case_id}: query cohort {sorted(explicit_cohorts)} conflicts "
                    f"with selected cohort {selected_cohort}"
                )
                if strict_cohort_conflicts:
                    errors.append(message)
                else:
                    warnings.append(message)

            if suite in {"retrieval", "answers"}:
                judgments = case.get("relevance_judgments")
                if not isinstance(judgments, list) or (
                    not judgments
                    and case.get("answerability") != "unanswerable"
                    and case.get("expected_path")
                    not in {"structured", "mixed", "clarify", "out_of_domain"}
                ):
                    errors.append(f"{case_id}: missing relevance_judgments")
                for judgment in judgments or []:
                    source_id = str(judgment.get("parent_section_id") or "").strip()
                    grade = judgment.get("grade")
                    if source_id not in docs_by_id:
                        errors.append(
                            f"{case_id}: unknown parent_section_id={source_id}"
                        )
                        continue
                    if grade not in {1, 2}:
                        errors.append(f"{case_id}: invalid relevance grade={grade!r}")
                    doc = docs_by_id[source_id]
                    metadata = _doc_metadata(doc)
                    expected_cohort = case.get("cohort")
                    actual_cohort = metadata.get("cohort") or doc.get("cohort")
                    from src.common.cohort import is_cohort_applicable

                    if (
                        expected_cohort not in {None, "", "general", "all"}
                        and not is_cohort_applicable(doc, expected_cohort)
                    ):
                        errors.append(
                            f"{case_id}: source cohort {actual_cohort!r} != {expected_cohort!r}"
                        )
                    actual_document = metadata.get("document_id") or doc.get(
                        "document_id"
                    )
                    if (
                        judgment.get("document_id")
                        and judgment.get("document_id") != actual_document
                    ):
                        errors.append(
                            f"{case_id}: source document {actual_document!r} != {judgment.get('document_id')!r}"
                        )
                    actual_content_type = metadata.get("content_type") or doc.get(
                        "content_type"
                    )
                    if (
                        judgment.get("content_type")
                        and judgment.get("content_type") != actual_content_type
                    ):
                        errors.append(
                            f"{case_id}: source content_type {actual_content_type!r} != {judgment.get('content_type')!r}"
                        )
                    # Automatically expanded cohort-edition anchors describe the
                    # same reviewed source target; they must not inflate the
                    # dataset's independent parent-usage diversity check.
                    if judgment.get("anchor_source") != "equivalent_cohort_edition":
                        parent_usage.setdefault(
                            (str(expected_cohort), source_id), set()
                        ).add(normalized)

            if suite == "answers":
                for field in (
                    "ground_truth",
                    "required_facts",
                    "forbidden_claims",
                    "answerability",
                    "expected_citations",
                ):
                    if field not in case:
                        errors.append(f"{case_id}: missing answer field {field}")
                if case.get("generation_model") != "gemini-3.1-flash-lite":
                    errors.append(f"{case_id}: wrong generation model")
                if case.get("judge_model") != "openai/gpt-oss-120b":
                    errors.append(f"{case_id}: wrong judge model")
                structured_sources = case.get("expected_structured_sources") or []
                if case.get("expected_path") in {"structured", "mixed"} and not (
                    case.get("relevance_judgments") or structured_sources
                ):
                    errors.append(
                        f"{case_id}: structured/mixed answer missing structured sources"
                    )
                for source in structured_sources:
                    source_id = str((source or {}).get("source_id") or "").strip()
                    catalog = str((source or {}).get("catalog") or "").strip()
                    if not source_id:
                        errors.append(f"{case_id}: empty structured source_id")
                        continue
                    if source_id not in structured_ids:
                        errors.append(f"{case_id}: unknown structured source_id={source_id}")
                        continue
                    record = structured_source_index.get((catalog, source_id))
                    if catalog and record is None:
                        message = (
                            f"{case_id}: structured source_id={source_id} does not "
                            f"belong to catalog={catalog}"
                        )
                        if strict_structured_sources:
                            errors.append(message)
                        else:
                            warnings.append(message)
                        continue
                    if record is not None and not _structured_record_matches_cohort(
                        record, case.get("cohort")
                    ):
                        message = (
                            f"{case_id}: structured source_id={source_id} does not "
                            f"apply to cohort={case.get('cohort')}"
                        )
                        if strict_structured_sources:
                            errors.append(message)
                        else:
                            warnings.append(message)
            elif suite == "deterministic":
                for field in ("case_type", "expected_group", "expected_llm_called"):
                    if field not in case:
                        errors.append(f"{case_id}: missing deterministic field {field}")
                if manifest.get("schema_version") == "architecture-evaluation-v6":
                    _validate_deterministic_contract(case, errors)
                elif manifest.get("schema_version") == "architecture-evaluation-v7":
                    _validate_deterministic_v7_contract(case, errors)
            elif suite == "production" and not case.get("scenario"):
                errors.append(f"{case_id}: missing production scenario")

    normalized_index: dict[str, tuple[str, str | None]] = {}
    for case_id, normalized, _, duplicate_group in normalized_queries:
        if not normalized:
            continue
        if normalized in normalized_index:
            other_id, other_group = normalized_index[normalized]
            if not duplicate_group or duplicate_group != other_group:
                message = f"exact duplicate query: {case_id} == {other_id}"
                if strict_query_duplicates:
                    errors.append(message)
                else:
                    warnings.append(message)
        else:
            normalized_index[normalized] = (case_id, duplicate_group)

    for index, (case_id, normalized, reviewed, duplicate_group) in enumerate(
        normalized_queries
    ):
        if reviewed or not normalized:
            continue
        for other_id, other, other_reviewed, other_group in normalized_queries[
            index + 1 :
        ]:
            if other_reviewed or not other:
                continue
            if duplicate_group and duplicate_group == other_group:
                continue
            ratio = SequenceMatcher(None, normalized, other).ratio()
            if ratio >= 0.96:
                message = (
                    f"unreviewed near duplicate ({ratio:.3f}): {case_id} ~ {other_id}"
                )
                if (
                    manifest.get("schema_version") == "architecture-evaluation-v7"
                    and not manifest.get("frozen")
                ):
                    warnings.append(message)
                else:
                    errors.append(message)

    legacy_queries: dict[str, str] = {}
    for legacy_path in bundle_dir.parent.glob("*.json"):
        try:
            legacy_value = load_json(legacy_path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(legacy_value, list):
            continue
        for legacy_case in legacy_value:
            if not isinstance(legacy_case, dict) or not legacy_case.get("query"):
                continue
            normalized = normalize_query(str(legacy_case["query"]))
            if normalized:
                legacy_queries.setdefault(normalized, legacy_path.name)

    for case_id, normalized, _, _ in normalized_queries:
        if normalized in legacy_queries:
            errors.append(
                f"legacy query overlap: {case_id} also exists in {legacy_queries[normalized]}"
            )

    max_parent_query_usage = int(manifest.get("max_parent_query_usage") or 2)
    for (cohort, source_id), unique_queries in parent_usage.items():
        count = len(unique_queries)
        if count > max_parent_query_usage:
            errors.append(
                f"parent usage exceeds {max_parent_query_usage} for "
                f"cohort={cohort}: {source_id} used {count} times"
            )

    deterministic = datasets.get("deterministic", [])
    expected_det_types = manifest.get("deterministic_case_type_counts") or {
        "positive": 60,
        "hard_negative": 40,
        "ambiguous": 12,
        "out_of_domain": 8,
    }
    actual_det_types = Counter(case.get("case_type") for case in deterministic)
    if dict(actual_det_types) != expected_det_types:
        errors.append(
            f"deterministic case distribution mismatch: {dict(actual_det_types)}"
        )
    lookup_case_types = set(
        manifest.get("deterministic_lookup_case_types") or ["positive"]
    )
    positive_groups = Counter(
        case.get("lookup_group")
        for case in deterministic
        if case.get("case_type") in lookup_case_types
    )
    expected_positive_groups = manifest.get("deterministic_lookup_group_counts")
    if expected_positive_groups is None:
        expected_positive_groups = manifest.get(
            "deterministic_positive_lookup_counts"
        )
    positive_groups_valid = (
        dict(positive_groups) == expected_positive_groups
        if expected_positive_groups is not None
        else len(positive_groups) == 10
        and all(count == 6 for count in positive_groups.values())
    )
    if not positive_groups_valid:
        errors.append(
            f"deterministic positive lookup coverage mismatch: {dict(positive_groups)}"
        )

    retrieval = datasets.get("retrieval", [])
    regulation = [
        case for case in retrieval if case.get("case_type") == "regulation_true_rag"
    ]
    expected_retrieval_n = int(expected_counts.get("retrieval") or 0)
    if len(regulation) != expected_retrieval_n:
        errors.append(
            f"retrieval expected {expected_retrieval_n} regulation cases, "
            f"found {len(regulation)}"
        )
    expected_reg_cohorts = manifest.get("retrieval_cohort_counts") or {
        "K48-K49": 46,
        "K50": 45,
        "K51": 45,
        "general": 44,
    }
    actual_reg_cohorts = Counter(case.get("cohort") for case in regulation)
    if dict(actual_reg_cohorts) != expected_reg_cohorts:
        errors.append(
            f"retrieval regulation cohort distribution mismatch: {dict(actual_reg_cohorts)}"
        )
    retrieval_split = Counter(case.get("eval_split") for case in retrieval)
    expected_retrieval_split = manifest.get("retrieval_eval_split_counts") or {
        "realistic": 135,
        "stress": 45,
    }
    if dict(retrieval_split) != expected_retrieval_split:
        errors.append(f"retrieval eval_split mismatch: {dict(retrieval_split)}")
    retrieval_tags = Counter(
        tag for case in retrieval for tag in case.get("tags") or []
    )
    required_tags = {
        "keyword",
        "paraphrase",
        "student_style",
        "typo_no_diacritics",
        "numeric_fact",
        "condition_procedure",
        "multi_source",
        "graph_reference",
        "cohort_sensitive",
    }
    missing_tags = sorted(tag for tag in required_tags if retrieval_tags[tag] == 0)
    if missing_tags:
        errors.append(f"retrieval coverage tags missing: {missing_tags}")
    if not any(
        judgment.get("grade") == 1
        for case in retrieval
        for judgment in case.get("relevance_judgments") or []
    ):
        errors.append("retrieval dataset has no supporting relevance grade=1")

    if manifest.get("retrieval_contract") in {
        "regulation-rag-source-first-v3",
        "regulation-rag-question-target-holdout-v6",
        "regulation-rag-outcome-draft-v7",
    }:
        forbidden_fragments = [
            normalize_query(value)
            for value in manifest.get("retrieval_forbidden_query_fragments") or []
        ]
        for case in retrieval:
            case_id = str(case.get("id") or "")
            if case.get("expected_path") != "regulation_rag":
                errors.append(f"{case_id}: retrieval case must use regulation_rag")
            if case.get("case_type") != "regulation_true_rag":
                errors.append(
                    f"{case_id}: retrieval case must be regulation_true_rag"
                )
            normalized = normalize_query(str(case.get("query") or ""))
            for fragment in forbidden_fragments:
                if fragment and fragment in normalized:
                    errors.append(
                        f"{case_id}: generated/unnatural query fragment={fragment!r}"
                    )
            for judgment in case.get("relevance_judgments") or []:
                source_id = str(judgment.get("parent_section_id") or "")
                source = docs_by_id.get(source_id) or {}
                content_type = (_doc_metadata(source).get("content_type"))
                if content_type != "regulation_text":
                    errors.append(
                        f"{case_id}: RAG anchor {source_id} is not regulation_text"
                    )

    answers = datasets.get("answers", [])
    answer_types = Counter(case.get("case_type") for case in answers)
    expected_answer_types = manifest.get("answer_case_type_counts") or {
        "regulation_true_rag": 86,
        "structured_mixed": 4,
        "unanswerable": 10,
    }
    if dict(answer_types) != expected_answer_types:
        errors.append(f"answer case distribution mismatch: {dict(answer_types)}")
    answer_split = Counter(case.get("eval_split") for case in answers)
    expected_answer_split = manifest.get("answer_eval_split_counts") or {
        "realistic": 75,
        "stress": 25,
    }
    if dict(answer_split) != expected_answer_split:
        errors.append(f"answer eval_split mismatch: {dict(answer_split)}")

    evaluation_contract = manifest.get("evaluation_contract")
    if evaluation_contract in {
        "comprehensive-source-grounded-answer-v4",
        "comprehensive-question-target-holdout-v6",
        "comprehensive-outcome-draft-v7",
    }:
        expected_answer_contract = (
            "answer-quality-target-holdout-v6"
            if evaluation_contract == "comprehensive-question-target-holdout-v6"
            else "answer-quality-outcome-draft-v7"
            if evaluation_contract == "comprehensive-outcome-draft-v7"
            else "answer-quality-source-grounded-v4"
        )
        expected_paths = manifest.get("answer_path_counts") or {}
        actual_paths = Counter(case.get("expected_path") for case in answers)
        if dict(actual_paths) != expected_paths:
            errors.append(f"answer path distribution mismatch: {dict(actual_paths)}")

        expected_rag_cohorts = manifest.get("answer_rag_cohort_counts") or {}
        actual_rag_cohorts = Counter(
            case.get("cohort")
            for case in answers
            if case.get("case_type") == "regulation_true_rag"
        )
        if dict(actual_rag_cohorts) != expected_rag_cohorts:
            errors.append(
                f"answer RAG cohort distribution mismatch: {dict(actual_rag_cohorts)}"
            )

        expected_lookup_counts = manifest.get("answer_structured_lookup_counts") or {}
        actual_lookup_counts = Counter(
            case.get("lookup_group")
            for case in answers
            if case.get("case_type") == "structured_answer"
        )
        if dict(actual_lookup_counts) != expected_lookup_counts:
            errors.append(
                f"answer structured lookup coverage mismatch: {dict(actual_lookup_counts)}"
            )

        path_by_type = {
            "regulation_true_rag": "regulation_rag",
            "structured_answer": "structured",
            "mixed_answer": "mixed",
            "clarification": "clarify",
            "unanswerable": "regulation_rag",
            "out_of_domain": "out_of_domain",
        }
        for case in answers:
            case_id = str(case.get("id") or "")
            case_type = str(case.get("case_type") or "")
            if case.get("contract_version") != expected_answer_contract:
                errors.append(
                    f"{case_id}: wrong answer contract; expected "
                    f"{expected_answer_contract}"
                )
            if path_by_type.get(case_type) != case.get("expected_path"):
                errors.append(
                    f"{case_id}: case_type={case_type} has invalid path={case.get('expected_path')}"
                )
            if not str(case.get("ground_truth") or "").strip():
                errors.append(f"{case_id}: empty v4 ground truth")
            if not case.get("required_facts"):
                errors.append(f"{case_id}: empty v4 required facts")
            if case_type == "mixed_answer" and not (
                case.get("relevance_judgments")
                and case.get("expected_structured_sources")
            ):
                errors.append(f"{case_id}: mixed answer missing an evidence family")

    production = datasets.get("production", [])
    production_scenarios = Counter(case.get("scenario") for case in production)
    expected_production_scenarios = manifest.get(
        "production_scenario_counts"
    ) or {
        "cold_rag": 20,
        "deterministic": 10,
        "warm_cache": 10,
        "streaming": 10,
        "burst": 10,
    }
    if dict(production_scenarios) != expected_production_scenarios:
        errors.append(
            f"production scenario distribution mismatch: {dict(production_scenarios)}"
        )
    burst_concurrency = Counter(
        int(case.get("concurrency") or 0)
        for case in production
        if case.get("scenario") == "burst"
    )
    if dict(burst_concurrency) != {3: 5, 5: 5}:
        errors.append(
            f"production burst concurrency mismatch: {dict(burst_concurrency)}"
        )

    expected_hashes = manifest.get("dataset_hashes") or {}
    actual_hashes: dict[str, str] = {}
    for suite, cases in datasets.items():
        actual_hashes[suite] = stable_json_hash(cases)
        if expected_hashes and expected_hashes.get(suite) != actual_hashes[suite]:
            errors.append(f"{suite}: manifest dataset hash mismatch")
    audit_template_path = bundle_dir / "human_audit_template.json"
    expected_audit_hash = (manifest.get("auxiliary_hashes") or {}).get(
        "human_audit_template"
    )
    if not audit_template_path.exists():
        errors.append("missing human_audit_template.json")
    else:
        audit_template = load_json(audit_template_path)
        if expected_audit_hash != stable_json_hash(audit_template):
            errors.append("human audit template hash mismatch")
        expected_audit_n = int(manifest.get("human_audit_required_n") or 20)
        repeat_value = manifest.get("human_audit_repeat_n")
        expected_repeat_n = 5 if repeat_value is None else int(repeat_value)
        if len(audit_template) != expected_audit_n:
            errors.append(
                f"human audit template expected {expected_audit_n} rows, found {len(audit_template)}"
            )
        if sum(bool(row.get("repeat_for_consistency")) for row in audit_template) != expected_repeat_n:
            errors.append(
                f"human audit template must mark exactly {expected_repeat_n} repeated scores"
            )

    counts = {suite: len(cases) for suite, cases in datasets.items()}
    breakdowns = {
        suite: {
            "cohort": dict(Counter(str(case.get("cohort")) for case in cases)),
            "case_type": dict(Counter(str(case.get("case_type")) for case in cases)),
            "scenario": dict(Counter(str(case.get("scenario")) for case in cases)),
        }
        for suite, cases in datasets.items()
    }

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": counts,
        "breakdowns": breakdowns,
        "dataset_hashes": actual_hashes,
        "docstore_parent_count": len(docs_by_id),
    }
