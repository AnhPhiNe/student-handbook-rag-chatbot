"""Data-backed gold audit utilities for the single-cohort-v2 bundle.

The audit deliberately does not use the production retriever to create RAG
ground truth.  Candidate evidence comes from the frozen legacy annotations and
the versioned BM25 corpus, while structured requests execute the selected
adapter directly against local source-of-truth resources.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.common.cohort import is_cohort_applicable
from src.evaluation.artifact_fingerprint import release_artifact_fingerprint
from src.evaluation.dataset import stable_json_hash
from src.evaluation.suites import load_runtime_resources
from src.retrieval.core.request_execution import RequestExecutionContext
from src.retrieval.core.structured_routing import load_lookup_registry
from src.retrieval.core.tool_registry import (
    AtomicToolRequest,
    ToolExecutionInput,
    ToolResources,
    build_tool_registry,
)


ROOT = Path(__file__).resolve().parents[2]
BUNDLE_DIR = ROOT / "data" / "eval" / "single_cohort_v2"
LEGACY_DIR = ROOT / "data" / "eval" / "final_holdout"
BM25_INDEX = ROOT / "data" / "processed" / "retrieval" / "bm25_index.json"
ANNOTATION_STATES = {"auto_verified", "review_required", "human_approved"}
GOLD_SCHEMA_VERSION = "single-cohort-v2.2"
FROZEN_GOLD_SCHEMA_VERSION = "single-cohort-v2.4"
CANDIDATE_DATASET_VERSION = "single-cohort-gold-candidate-1"
FROZEN_DATASET_VERSION = "single-cohort-gold-v2"

_STOPWORDS = {
    "cho", "cua", "dieu", "dinh", "duoc", "gi", "hay", "hop", "khi", "kien",
    "la", "lam", "nao", "noi", "qua", "quy", "ra", "sao", "the", "thi",
    "sinh", "thu", "toi", "tra", "trong", "truong", "tuc", "va", "ve", "vien",
    "voi", "xem", "xin", "xu",
}
_ALIASES = {
    "bao luu": "nghi hoc tam thoi",
    "tam dung hoc": "nghi hoc tam thoi",
    "rut hoc phan": "rut bot hoc phan da dang ky",
    "hoc cai thien": "hoc lai hoc cai thien diem",
    "hoc lai": "hoc lai hoc cai thien diem",
    "khieu nai diem": "phuc khao khieu nai ket qua hoc tap",
    "mien giam hoc phi": "mien giam hoc phi",
    "cap bang diem": "cap bang diem ket qua hoc tap",
    "mien hoc phan": "mien hoc mien thi cong nhan ket qua hoc tap chuyen doi tin chi",
    "tot nghiep": "cong nhan tot nghiep cap bang tot nghiep",
    "giay to khi tot nghiep": "bang tot nghiep bang diem hoc tap ren luyen giay to",
    "chuyen chuong trinh": "chuyen nganh chuyen chuong trinh dao tao",
    "chuyen nganh": "chuyen nganh chuyen chuong trinh dao tao",
    "canh bao hoc vu": "canh bao ket qua hoc tap",
    "xet thoi hoc": "buoc thoi hoc xet thoi hoc",
}


@dataclass(frozen=True)
class GoldAuditResult:
    dev: list[dict[str, Any]]
    hidden: list[dict[str, Any]]
    dev_review_queue: list[dict[str, Any]]
    review_queue: list[dict[str, Any]]
    report: dict[str, Any]


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _commit(root: Path = ROOT) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").casefold()).replace("đ", "d")
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def _expanded_tokens(value: Any) -> set[str]:
    text = _normalize(value)
    for source, replacement in _ALIASES.items():
        if source in text:
            text = f"{text} {replacement}"
    return {token for token in text.split() if len(token) > 2 and token not in _STOPWORDS}


def _alias_phrases(value: Any) -> set[str]:
    text = _normalize(value)
    phrases: set[str] = set()
    for source, replacement in _ALIASES.items():
        if source not in text:
            continue
        phrases.add(source)
        tokens = [token for token in replacement.split() if token not in _STOPWORDS]
        if len(tokens) >= 2:
            phrases.add(" ".join(tokens[:2]))
    return {phrase for phrase in phrases if " " in phrase}


def _annotation_query(case: Mapping[str, Any], request: Mapping[str, Any]) -> str:
    """Build evidence-search text from user-visible, provenance-bearing inputs.

    A follow-up span such as ``Nội dung đó ...`` is not independently meaningful.
    Candidate discovery may therefore use the grounded user turn, but never an
    expected answer, tool output, or hidden gold label.
    """
    parts = [str(request.get("query_span") or "")]
    expected = case.get("expected") if isinstance(case.get("expected"), Mapping) else {}
    if expected.get("context_mode") == "follow_up":
        grounded_parts: list[str] = []
        for turn in case.get("chat_history") or []:
            if isinstance(turn, Mapping) and turn.get("role") == "user":
                content = str(turn.get("content") or "").strip()
                if content:
                    grounded_parts.append(content)
        if grounded_parts:
            parts = grounded_parts
    return " ".join(parts)


def _file_versions(root: Path = ROOT) -> dict[str, str | None]:
    return release_artifact_fingerprint(root)


def _tool_resources(root: Path = ROOT) -> ToolResources:
    resources = load_runtime_resources(root)
    faculty_path = root / "data/processed/directories/student_faculty_profiles.json"
    return ToolResources(
        scoring_tables=resources["scoring_tables"],
        formula_rules=resources["formula_rules"],
        office_directory=resources["student_office_profiles"],
        student_service_directory=resources["student_service_directory"],
        student_faculty_profiles=_load(faculty_path),
        foreign_language_tables=resources["foreign_language_tables"],
        structured_tables_registry=resources["structured_tables_registry"],
        program_directory=resources["program_directory"],
    )


def _source_record(record: Mapping[str, Any]) -> dict[str, Any]:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
    pages = record.get("source_pages") or metadata.get("source_pages") or []
    return {
        "record_id": str(
            record.get("record_id")
            or record.get("source_record_id")
            or record.get("table_id")
            or record.get("row_id")
            or record.get("id")
            or record.get("_id")
            or ""
        )
        or None,
        "document_id": str(record.get("document_id") or metadata.get("document_id") or "")
        or None,
        "parent_section_id": str(
            record.get("parent_section_id")
            or record.get("source_parent_id")
            or metadata.get("parent_section_id")
            or ""
        )
        or None,
        "source_pages": sorted({int(page) for page in pages if str(page).isdigit()}),
        "cohort": record.get("cohort") or metadata.get("cohort"),
        "applicable_cohorts": sorted(
            {
                str(cohort)
                for cohort in (
                    record.get("applicable_cohorts")
                    or metadata.get("applicable_cohorts")
                    or []
                )
                if str(cohort)
            }
        ),
        "source_type": (
            record.get("source_type")
            or record.get("source_kind")
            or metadata.get("source_type")
        ),
    }


def _audit_structured_request(
    case: Mapping[str, Any],
    request: Mapping[str, Any],
    *,
    resources: ToolResources,
) -> dict[str, Any]:
    expected = case.get("expected") or {}
    cohort = expected.get("effective_cohort")
    atomic = AtomicToolRequest.from_mapping(request)
    context = RequestExecutionContext(
        request_id=str(request["request_id"]),
        request_index=int(str(request["request_id"]).removeprefix("r")) - 1,
        request_kind="structured",
        query_span=str(request["query_span"]),
        effective_query=str(case["query"]),
        effective_cohort=cohort,
        retrieval_query=str(request["query_span"]),
    )
    registry = build_tool_registry(load_lookup_registry().get("tools") or {})
    result = registry.execute(
        atomic.tool_name,
        ToolExecutionInput(
            request=atomic,
            decision=expected,
            context=context,
            query=str(request["query_span"]),
            effective_cohort=cohort,
            resources=resources,
        ),
    )
    records = [_source_record(record) for record in result.source_records]
    records = [record for record in records if any(value for value in record.values())]
    expected_status = str(request.get("expected_status"))
    status_matches = result.status == expected_status
    cohort_applicable = result.status != "ok" or bool(records) and all(
        is_cohort_applicable(record, cohort) for record in records
    )
    source_bound = result.status != "ok" or bool(records) and cohort_applicable
    source_data_verified = True
    if atomic.tool_name == "formula" and result.status == "ok":
        result_mapping = result.result if isinstance(result.result, Mapping) else {}
        rule_id = result_mapping.get("rule_id")
        matching_rules = [
            rule
            for rule in resources.formula_rules
            if rule.get("rule_id") == rule_id
        ]
        source_data_verified = bool(matching_rules) and all(
            str(rule.get("review_status") or "").casefold()
            in {"approved", "human_approved", "human_verified", "verified"}
            for rule in matching_rules
        )
    return {
        "annotation_state": (
            "auto_verified"
            if status_matches and source_bound and source_data_verified
            else "review_required"
        ),
        "audit_method": "direct_tool_adapter",
        "expected_status": expected_status,
        "actual_status": result.status,
        "status_matches": status_matches,
        "source_bound": source_bound,
        "cohort_applicable": cohort_applicable,
        "source_data_verified": source_data_verified,
        "source_records": records,
        "result": result.result if result.status == "ok" else None,
        "confidence": result.confidence,
        "provenance": result.provenance,
    }


def _bm25_chunks(root: Path = ROOT) -> list[dict[str, Any]]:
    value = _load(root / "data/processed/retrieval/bm25_index.json")
    return list(value.get("chunks") or []) if isinstance(value, Mapping) else list(value)


def _legacy_evidence(root: Path = ROOT) -> list[dict[str, Any]]:
    cases = _load(root / "data/eval/final_holdout/retrieval_cases.json")
    rows: list[dict[str, Any]] = []
    for case in cases:
        if case.get("cohort") == "general":
            continue
        search_text = " ".join(
            str(value or "")
            for value in (case.get("query"), case.get("source_topic"), case.get("topic"))
        )
        for judgment in case.get("relevance_judgments") or []:
            rows.append(
                {
                    "case_id": case.get("id"),
                    "cohort": case.get("cohort"),
                    "search_text": search_text,
                    "source_topic": str(case.get("source_topic") or ""),
                    "tokens": _expanded_tokens(search_text),
                    "judgment": judgment,
                }
            )
    return rows


def _chunk_groups(chunks: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        cohort = str(metadata.get("cohort") or "")
        parent = str(metadata.get("parent_section_id") or metadata.get("parent_chunk_id") or "")
        if cohort and parent:
            groups[(cohort, parent)].append(dict(chunk))
    return groups


def _candidate_from_group(
    cohort: str,
    parent_id: str,
    chunks: list[dict[str, Any]],
    query_tokens: set[str],
    *,
    origin: str,
    relevance_grade: int = 2,
    legacy_case_id: str | None = None,
) -> dict[str, Any]:
    ranked: list[tuple[float, dict[str, Any]]] = []
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        text = " ".join(
            str(value or "")
            for value in (metadata.get("source_section"), metadata.get("title"), chunk.get("content"))
        )
        tokens = _expanded_tokens(text)
        title_tokens = _expanded_tokens(
            metadata.get("source_section") or metadata.get("title")
        )
        title_coverage = len(query_tokens & title_tokens) / max(1, len(query_tokens))
        content_coverage = len(query_tokens & tokens) / max(1, len(query_tokens))
        ranked.append((0.8 * title_coverage + 0.2 * content_coverage, chunk))
    ranked.sort(key=lambda item: item[0], reverse=True)
    selected = [chunk for _, chunk in ranked[:5]]
    metadata = (selected[0].get("metadata") or {}) if selected else {}
    pages = sorted(
        {
            int(page)
            for chunk in selected
            for page in (chunk.get("metadata") or {}).get("source_pages") or []
            if str(page).isdigit()
        }
    )
    return {
        "origin": origin,
        "legacy_case_id": legacy_case_id,
        "cohort": cohort,
        "document_id": metadata.get("document_id"),
        "parent_section_id": parent_id,
        "chunk_ids": [str(chunk.get("chunk_id") or chunk.get("_id")) for chunk in selected],
        "source_pages": pages,
        "source_section": metadata.get("source_section") or metadata.get("title"),
        "evidence_excerpt": str(selected[0].get("content") or "")[:1200] if selected else "",
        "relevance_grade": relevance_grade,
        "lexical_coverage": round(ranked[0][0] if ranked else 0.0, 4),
    }


def _rag_candidates(
    case: Mapping[str, Any],
    request: Mapping[str, Any],
    cohort: str,
    *,
    legacy: list[dict[str, Any]],
    groups: Mapping[tuple[str, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    annotation_query = _annotation_query(case, request)
    query_tokens = _expanded_tokens(annotation_query)
    alias_phrases = _alias_phrases(annotation_query)
    ranked_legacy: list[tuple[float, dict[str, Any]]] = []
    for row in legacy:
        if row["cohort"] != cohort:
            continue
        coverage = len(query_tokens & row["tokens"]) / max(1, len(query_tokens))
        ranked_legacy.append((coverage, row))
    ranked_legacy.sort(key=lambda item: item[0], reverse=True)

    candidates_by_parent: dict[str, dict[str, Any]] = {}
    for match_score, row in ranked_legacy[:8]:
        judgment = row["judgment"]
        parent_id = str(judgment.get("parent_section_id") or "")
        chunks = groups.get((cohort, parent_id)) or []
        if not parent_id or not chunks:
            continue
        candidate = _candidate_from_group(
            cohort,
            parent_id,
            chunks,
            query_tokens,
            origin="frozen_legacy_gold",
            relevance_grade=int(judgment.get("grade") or 2),
            legacy_case_id=str(row["case_id"]),
        )
        source_score = len(query_tokens & _expanded_tokens(row["source_topic"])) / max(
            1, len(query_tokens)
        )
        candidate["annotation_match_score"] = round(
            0.55 * float(candidate["lexical_coverage"])
            + 0.45 * max(match_score, source_score),
            4,
        )
        previous = candidates_by_parent.get(parent_id)
        if previous is None or candidate["annotation_match_score"] > previous["annotation_match_score"]:
            candidates_by_parent[parent_id] = candidate

    direct: list[tuple[float, str, list[dict[str, Any]]]] = []
    for (group_cohort, parent_id), chunks in groups.items():
        if group_cohort != cohort:
            continue
        text = " ".join(
            str(value or "")
            for chunk in chunks
            for value in (
                (chunk.get("metadata") or {}).get("source_section"),
                (chunk.get("metadata") or {}).get("title"),
                chunk.get("content"),
            )
        )
        metadata = chunks[0].get("metadata") or {}
        title_tokens = _expanded_tokens(
            metadata.get("source_section") or metadata.get("title")
        )
        title_coverage = len(query_tokens & title_tokens) / max(1, len(query_tokens))
        content_coverage = len(query_tokens & _expanded_tokens(text)) / max(1, len(query_tokens))
        normalized_text = _normalize(text)
        phrase_match = 1.0 if any(phrase in normalized_text for phrase in alias_phrases) else 0.0
        coverage = min(
            1.0,
            0.8 * title_coverage + 0.2 * content_coverage + 0.35 * phrase_match,
        )
        direct.append((coverage, parent_id, chunks))
    direct.sort(key=lambda item: item[0], reverse=True)
    for coverage, parent_id, chunks in direct:
        if coverage <= 0:
            break
        candidate = _candidate_from_group(
            cohort, parent_id, chunks, query_tokens, origin="versioned_corpus"
        )
        candidate["annotation_match_score"] = round(coverage, 4)
        previous = candidates_by_parent.get(parent_id)
        if previous is None or candidate["annotation_match_score"] > previous["annotation_match_score"]:
            candidates_by_parent[parent_id] = candidate
    return sorted(
        candidates_by_parent.values(),
        key=lambda item: float(item.get("annotation_match_score") or 0),
        reverse=True,
    )[:10]


def _promoted_evidence(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    first = candidates[0]
    second_score = float(candidates[1].get("annotation_match_score") or 0) if len(candidates) > 1 else 0.0
    first_score = float(first.get("annotation_match_score") or 0)
    if (
        first.get("origin") != "frozen_legacy_gold"
        or first_score < 0.6
        or first_score - second_score < 0.15
    ):
        return None
    return {
        "document_ids": [first["document_id"]] if first.get("document_id") else [],
        "parent_section_ids": [first["parent_section_id"]],
        "chunk_ids": list(first.get("chunk_ids") or []),
        "source_pages": list(first.get("source_pages") or []),
        "relevance_grade": int(first.get("relevance_grade") or 2),
        "evidence_excerpts": [first.get("evidence_excerpt") or ""],
        "source_bindings": [
            {
                "document_id": first.get("document_id"),
                "parent_section_id": first.get("parent_section_id"),
                "chunk_ids": list(first.get("chunk_ids") or []),
                "source_pages": list(first.get("source_pages") or []),
                "relevance_grade": int(first.get("relevance_grade") or 2),
            }
        ],
    }


def _audit_suite(
    cases: list[dict[str, Any]],
    *,
    split: str,
    resources: ToolResources,
    legacy: list[dict[str, Any]],
    groups: Mapping[tuple[str, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    audited: list[dict[str, Any]] = []
    for source_case in cases:
        case = json.loads(json.dumps(source_case, ensure_ascii=False))
        expected = case.get("expected") or {}
        fault = case.get("fault_injection")
        request_states: list[str] = []
        for request in expected.get("atomic_requests") or []:
            if fault:
                request["gold_audit"] = {
                    "annotation_state": "auto_verified" if split == "dev" else "review_required",
                    "audit_method": "deterministic_fault_harness",
                    "fault_type": fault.get("type"),
                }
            elif request.get("request_kind") == "structured":
                audit = _audit_structured_request(case, request, resources=resources)
                expected_result = audit.pop("result")
                source_records = audit.pop("source_records")
                request["gold_audit"] = audit
                request["expected_source_contract"] = str(
                    audit.get("provenance", {}).get("source_contract")
                    or request.get("expected_source_contract")
                )
                request["expected_source_records"] = (
                    source_records if audit["actual_status"] == "ok" else []
                )
                request["expected_result"] = (
                    expected_result if audit["actual_status"] == "ok" else None
                )
            else:
                cohort = str(expected.get("effective_cohort") or "")
                candidates = _rag_candidates(
                    case, request, cohort, legacy=legacy, groups=groups
                )
                promoted = _promoted_evidence(candidates) if split == "dev" else None
                request["evidence_candidates"] = candidates
                request["expected_evidence"] = promoted or {}
                request["gold_audit"] = {
                    "annotation_state": "auto_verified" if promoted else "review_required",
                    "audit_method": (
                        "frozen_legacy_source_binding" if promoted else "candidate_only_not_gold"
                    ),
                    "candidate_count": len(candidates),
                }
            request_states.append(request["gold_audit"]["annotation_state"])

        if split == "hidden":
            state = "review_required"
        elif request_states and all(value == "auto_verified" for value in request_states):
            state = "auto_verified"
        elif not request_states:
            state = "auto_verified"
        else:
            state = "review_required"
        case["annotation"] = {
            "state": state,
            "reviewer": None,
            "reviewed_at": None,
        }
        audited.append(case)
    return audited


def _review_queue(
    cases: list[dict[str, Any]], *, include_auto_verified: bool
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        if (
            not include_auto_verified
            and case.get("annotation", {}).get("state") != "review_required"
        ):
            continue
        reviews = []
        for request in case.get("expected", {}).get("atomic_requests") or []:
            reviews.append(
                {
                    "request_id": request["request_id"],
                    "request_kind": request["request_kind"],
                    "tool_name": request.get("tool_name"),
                    "intent": request.get("intent"),
                    "query_span": request.get("query_span"),
                    "expected_status": request.get("expected_status"),
                    "decision": "pending",
                    "selected_parent_section_ids": [],
                    "candidate_evidence": request.get("evidence_candidates") or [],
                    "structured_audit": request.get("gold_audit") if request.get("request_kind") == "structured" else None,
                    "expected_source_records": request.get("expected_source_records") or [],
                    "notes": "",
                }
            )
        rows.append(
            {
                "case_id": case["id"],
                "query": case["query"],
                "selected_cohort": case.get("selected_cohort"),
                "chat_history": case.get("chat_history") or [],
                "fault_injection": case.get("fault_injection"),
                "expected_outcome": case.get("expected", {}).get("outcome"),
                "expected_effective_cohort": case.get("expected", {}).get("effective_cohort"),
                "decision": "pending",
                "reviewer": None,
                "reviewed_at": None,
                "request_reviews": reviews,
                "notes": "",
            }
        )
    return rows


def _audit_diagnostics(cases: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    cases = list(cases)
    requests = [
        request
        for case in cases
        if not case.get("fault_injection")
        for request in case.get("expected", {}).get("atomic_requests") or []
    ]
    rag_requests = [request for request in requests if request.get("request_kind") == "rag"]
    structured_requests = [
        request for request in requests if request.get("request_kind") == "structured"
    ]
    return {
        "rag_requests": len(rag_requests),
        "rag_requests_without_candidates": sum(
            not request.get("evidence_candidates") for request in rag_requests
        ),
        "structured_requests": len(structured_requests),
        "structured_status_mismatches": sum(
            (request.get("gold_audit") or {}).get("status_matches") is False
            for request in structured_requests
        ),
    }


def audit_bundle(
    bundle_dir: Path = BUNDLE_DIR,
    *,
    root: Path = ROOT,
) -> GoldAuditResult:
    resources = _tool_resources(root)
    legacy = _legacy_evidence(root)
    groups = _chunk_groups(_bm25_chunks(root))
    dev = _audit_suite(
        _load(bundle_dir / "dev.json"),
        split="dev",
        resources=resources,
        legacy=legacy,
        groups=groups,
    )
    hidden = _audit_suite(
        _load(bundle_dir / "hidden.json"),
        split="hidden",
        resources=resources,
        legacy=legacy,
        groups=groups,
    )
    dev_queue = _review_queue(dev, include_auto_verified=False)
    queue = _review_queue(hidden, include_auto_verified=True)
    states = Counter(case["annotation"]["state"] for case in dev + hidden)
    request_states = Counter(
        request["gold_audit"]["annotation_state"]
        for case in dev + hidden
        for request in case.get("expected", {}).get("atomic_requests") or []
    )
    report = {
        "schema_version": GOLD_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "commit": _commit(root),
        "provider": "deterministic",
        "data_versions": _file_versions(root),
        "counts": {"dev": len(dev), "hidden": len(hidden)},
        "audit_diagnostics": {
            "dev": _audit_diagnostics(dev),
            "hidden": _audit_diagnostics(hidden),
        },
        "case_annotation_states": dict(states),
        "request_annotation_states": dict(request_states),
        "hidden_review_required": len(queue),
        "gold_ready": not any(case["annotation"]["state"] == "review_required" for case in dev + hidden),
    }
    report["dev_review_required"] = len(dev_queue)
    return GoldAuditResult(dev, hidden, dev_queue, queue, report)


def apply_review(
    cases: list[dict[str, Any]],
    review_rows: list[dict[str, Any]],
    *,
    require_every_case: bool,
) -> list[dict[str, Any]]:
    by_id = {str(row.get("case_id")): row for row in review_rows}
    required_ids = {
        case["id"]
        for case in cases
        if require_every_case or case.get("annotation", {}).get("state") == "review_required"
    }
    if set(by_id) != required_ids:
        raise ValueError("Review file must contain every required case exactly once")
    approved: list[dict[str, Any]] = []
    for source_case in cases:
        case = json.loads(json.dumps(source_case, ensure_ascii=False))
        review = by_id.get(case["id"])
        if review is None:
            approved.append(case)
            continue
        if review.get("decision") != "approved" or not review.get("reviewer") or not review.get("reviewed_at"):
            raise ValueError(f"Hidden case is not human-approved: {case['id']}")
        request_reviews = {
            str(item.get("request_id")): item for item in review.get("request_reviews") or []
        }
        for request in case.get("expected", {}).get("atomic_requests") or []:
            item = request_reviews.get(request["request_id"])
            if not item or item.get("decision") != "approved":
                raise ValueError(f"Request is not approved: {case['id']}/{request['request_id']}")
            if (
                request.get("request_kind") == "structured"
                and not case.get("fault_injection")
                and not (request.get("gold_audit") or {}).get("status_matches")
            ):
                raise ValueError(
                    f"Structured annotation disagrees with the adapter: {case['id']}/{request['request_id']}"
                )
            if request.get("request_kind") == "rag" and not case.get(
                "fault_injection"
            ):
                selected = set(item.get("selected_parent_section_ids") or [])
                candidates = [
                    value
                    for value in request.get("evidence_candidates") or []
                    if value.get("parent_section_id") in selected
                ]
                if not selected or len(candidates) != len(selected):
                    raise ValueError(f"RAG evidence selection is invalid: {case['id']}/{request['request_id']}")
                request["expected_evidence"] = {
                    "document_ids": sorted({value["document_id"] for value in candidates if value.get("document_id")}),
                    "parent_section_ids": sorted(selected),
                    "chunk_ids": sorted({chunk for value in candidates for chunk in value.get("chunk_ids") or []}),
                    "source_pages": sorted({page for value in candidates for page in value.get("source_pages") or []}),
                    "relevance_grade": max(int(value.get("relevance_grade") or 1) for value in candidates),
                    "evidence_excerpts": [
                        value.get("evidence_excerpt") or "" for value in candidates
                    ],
                    "source_bindings": [
                        {
                            "document_id": value.get("document_id"),
                            "parent_section_id": value.get("parent_section_id"),
                            "chunk_ids": list(value.get("chunk_ids") or []),
                            "source_pages": list(value.get("source_pages") or []),
                            "relevance_grade": int(
                                value.get("relevance_grade") or 1
                            ),
                        }
                        for value in candidates
                    ],
                }
            request["gold_audit"] = {
                **request.get("gold_audit", {}),
                "annotation_state": "human_approved",
                "reviewer": review["reviewer"],
                "reviewed_at": review["reviewed_at"],
            }
        case["annotation"] = {
            **case.get("annotation", {}),
            "state": "human_approved",
            "reviewer": review["reviewer"],
            "reviewed_at": review["reviewed_at"],
        }
        approved.append(case)
    return approved


def apply_hidden_review(
    hidden: list[dict[str, Any]], review_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return apply_review(hidden, review_rows, require_every_case=True)


def legacy_compatibility_report(root: Path = ROOT) -> dict[str, Any]:
    manifest = _load(root / "data/eval/final_holdout/manifest.json")
    deterministic = _load(root / "data/eval/final_holdout/deterministic_tool_cases.json")
    retrieval = _load(root / "data/eval/final_holdout/retrieval_cases.json")
    answers = _load(root / "data/eval/final_holdout/generated_answer_cases.json")
    production = _load(root / "data/eval/final_holdout/production_cases.json")
    legacy_files = {
        "deterministic": root / "data/eval/final_holdout/deterministic_tool_cases.json",
        "retrieval": root / "data/eval/final_holdout/retrieval_cases.json",
        "answers": root / "data/eval/final_holdout/generated_answer_cases.json",
        "production": root / "data/eval/final_holdout/production_cases.json",
    }
    actual_hashes = {
        name: stable_json_hash(_load(path)) for name, path in legacy_files.items()
    }
    declared_hashes = manifest.get("dataset_hashes") or {}
    retrieval_current = [case for case in retrieval if case.get("cohort") != "general"]
    answer_current = [case for case in answers if case.get("cohort") != "general"]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "commit": _commit(root),
        "legacy_bundle_commit": manifest.get("git_commit"),
        "legacy_bundle_preserved": actual_hashes == declared_hashes,
        "legacy_hashes": {
            "declared": declared_hashes,
            "actual": actual_hashes,
            "match": actual_hashes == declared_hashes,
        },
        "metric_policy": "report_separately_do_not_merge_with_single_cohort_v2",
        "suites": {
            "deterministic": {"regression": len(deterministic), "deferred_multi_cohort": 0},
            "retrieval": {"regression": len(retrieval_current), "deferred_multi_cohort": len(retrieval) - len(retrieval_current)},
            "answers": {"regression": len(answer_current), "deferred_multi_cohort": len(answers) - len(answer_current)},
            "production": {"regression": len(production), "deferred_multi_cohort": 0},
        },
    }
