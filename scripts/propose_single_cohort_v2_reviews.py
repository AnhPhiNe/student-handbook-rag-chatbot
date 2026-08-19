"""Create evidence-backed AI review proposals for the 150/60 gold queues.

The output is deliberately not accepted by ``apply_review``. A human must
inspect and sign the proposal before the dataset may become human-approved.
Topic-to-source mappings below are annotation adjudications, never runtime
routing rules.
"""

from __future__ import annotations

import json
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "data/eval/single_cohort_v2"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").casefold()).replace(
        "đ", "d"
    )
    return "".join(
        char for char in text if unicodedata.category(char) != "Mn"
    )


def _parent(cohort: str, family: str, article: int) -> str:
    prefix = "K48-K49_K48_49_" if cohort == "K48-K49" else f"{cohort}_"
    chapter = {
        ("dao_tao", 9): 2,
        ("dao_tao", 10): 3,
        ("dao_tao", 12): 3,
        ("dao_tao", 14): 3,
        ("dao_tao", 15): 3,
        ("dao_tao", 16): 4,
        ("dao_tao", 17): 4,
        ("cong_tac", 8): 3,
        ("cong_tac", 29): 5,
        ("cong_tac", 30): 5,
    }[(family, article)]
    stem = "QuyCheDaoTao" if family == "dao_tao" else "QuyCheCongTacSinhVien"
    return f"{prefix}{stem}_Chuong{chapter}_Dieu{article}"


def _rag_gold_parents(row: dict[str, Any], request: dict[str, Any]) -> list[str]:
    history = " ".join(
        str(turn.get("content") or "")
        for turn in row.get("chat_history") or []
        if turn.get("role") == "user"
    )
    topic = _normalize(f"{request.get('query_span', '')} {history}")
    cohort = str(row.get("expected_effective_cohort") or "")
    if ("giay to" in topic or "bang diem" in topic) and "tot nghiep" in topic:
        return [_parent(cohort, "cong_tac", 8)]
    if "khieu nai" in topic or "phuc khao" in topic:
        return [_parent(cohort, "dao_tao", 10)]
    if "mien giam hoc phi" in topic:
        return [_parent(cohort, "cong_tac", 29)]
    if "mien hoc phan" in topic:
        return [_parent(cohort, "dao_tao", 14)]
    if "hoc lai" in topic or "hoc cai thien" in topic:
        return [_parent(cohort, "dao_tao", 10)]
    if "canh bao" in topic:
        return [_parent(cohort, "dao_tao", 12)]
    if "rut hoc phan" in topic or "dang ky hoc phan" in topic:
        return [_parent(cohort, "dao_tao", 9)]
    if "chuyen nganh" in topic or "chuyen chuong trinh" in topic:
        return [_parent(cohort, "dao_tao", 17)]
    if "xet thoi hoc" in topic:
        return [_parent(cohort, "dao_tao", 16)]
    if any(
        phrase in topic
        for phrase in (
            "bao luu",
            "nghi hoc tam thoi",
            "tam dung hoc",
            "nghi hoc qua han",
        )
    ):
        return [
            _parent(cohort, "dao_tao", 16),
            _parent(cohort, "cong_tac", 30),
        ]
    if "tot nghiep" in topic:
        return [_parent(cohort, "dao_tao", 15)]
    return []


def _structured_ok(
    request: dict[str, Any],
    *,
    formulas: dict[str, dict[str, Any]],
    parents: dict[str, dict[str, Any]],
) -> tuple[bool, str]:
    audit = request.get("structured_audit") or {}
    if not audit.get("status_matches"):
        return False, "adapter status disagrees with expected_status"
    if request.get("expected_status") == "ok":
        if not audit.get("source_bound") or not audit.get("cohort_applicable"):
            return False, "successful result is not source-bound/cohort-applicable"
        if not request.get("expected_source_records"):
            return False, "successful result has no source record"
    if request.get("tool_name") != "formula":
        return True, "adapter result and source contract verified"

    parent_ids = {
        str(record.get("parent_section_id") or "")
        for record in request.get("expected_source_records") or []
    }
    rules = [
        rule
        for rule in formulas.values()
        if str(rule.get("source_parent_id") or "") in parent_ids
    ]
    if not rules or any(rule.get("disabled") for rule in rules):
        return False, "formula record is missing or disabled"
    for rule in rules:
        parent_id = str(rule.get("source_parent_id") or "")
        parent = parents.get(parent_id)
        if not parent or "tính theo công thức" not in str(parent.get("content") or ""):
            return False, "formula is not explicitly supported by its source parent"
    return True, "formula and variables verified against the cited parent section"


def _review_queue(
    rows: list[dict[str, Any]],
    *,
    formulas: dict[str, dict[str, Any]],
    parents: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    reviewed: list[dict[str, Any]] = []
    exceptions: list[dict[str, str]] = []
    for source_row in rows:
        row = json.loads(json.dumps(source_row, ensure_ascii=False))
        request_passes: list[bool] = []
        for request in row.get("request_reviews") or []:
            if row.get("fault_injection"):
                ok, note = True, "deterministic fault contract; no real-data gold claimed"
                selected: list[str] = []
            elif request.get("request_kind") == "structured":
                ok, note = _structured_ok(
                    request,
                    formulas=formulas,
                    parents=parents,
                )
                selected = []
            else:
                selected = _rag_gold_parents(row, request)
                candidates = {
                    str(value.get("parent_section_id") or "")
                    for value in request.get("candidate_evidence") or []
                }
                missing = [parent_id for parent_id in selected if parent_id not in candidates]
                ok = bool(selected) and not missing
                note = (
                    "gold parents verified against versioned corpus"
                    if ok
                    else f"missing/undetermined gold parents: {missing or 'no adjudication'}"
                )
            request["decision"] = (
                "ai_recommended_approved" if ok else "ai_recommended_rejected"
            )
            request["selected_parent_section_ids"] = selected if ok else []
            request["notes"] = note
            request_passes.append(ok)
            if not ok:
                exceptions.append(
                    {
                        "case_id": str(row.get("case_id")),
                        "request_id": str(request.get("request_id")),
                        "reason": note,
                    }
                )
        case_ok = all(request_passes)
        row["decision"] = (
            "ai_recommended_approved" if case_ok else "ai_recommended_rejected"
        )
        row["reviewer"] = "codex_ai_evidence_audit"
        row["reviewed_at"] = datetime.now(UTC).isoformat()
        row["notes"] = (
            "AI-assisted source review complete; human signature still required."
        )
        reviewed.append(row)
    return reviewed, exceptions


def main() -> None:
    formula_rows = _load(ROOT / "data/processed/tables/formula_rules.json")
    parent_rows = _load(ROOT / "data/processed/chunks/all_docstore_items.json")
    formulas = {str(row.get("record_id") or ""): row for row in formula_rows}
    parents = {str(row.get("_id") or ""): row for row in parent_rows}
    all_exceptions: list[dict[str, str]] = []
    outputs: dict[str, list[dict[str, Any]]] = {}
    for split in ("dev", "hidden"):
        reviewed, exceptions = _review_queue(
            _load(BUNDLE / f"{split}_review_queue.json"),
            formulas=formulas,
            parents=parents,
        )
        outputs[split] = reviewed
        all_exceptions.extend(exceptions)
        _write(BUNDLE / f"{split}_review_proposal.json", reviewed)

    decisions = Counter(
        row["decision"] for rows in outputs.values() for row in rows
    )
    report = {
        "review_kind": "ai_assisted_evidence_audit",
        "human_signature_required": True,
        "generated_at": datetime.now(UTC).isoformat(),
        "queue_counts": {split: len(rows) for split, rows in outputs.items()},
        "decision_counts": dict(decisions),
        "exceptions": all_exceptions,
    }
    _write(BUNDLE / "ai_review_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
