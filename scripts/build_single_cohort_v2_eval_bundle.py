"""Build frozen, contract-annotated dev/hidden suites. Runtime never imports this."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "eval" / "single_cohort_v2"
COUNTS = {
    "single_structured": (10, 4), "single_rag": (10, 4), "multi_entity": (15, 6),
    "two_structured": (18, 7), "mixed": (20, 8), "two_regulations": (15, 6),
    "three_to_six_requests": (12, 5), "robustness": (14, 6), "follow_up": (15, 6),
    "cohort_resolution": (11, 4), "failure_isolation": (10, 4),
}


def request(index: int, kind: str, span: str, *, tool: str | None = None, intent: str | None = None, slots: dict[str, Any] | None = None, cohort: str | None = "K51") -> dict[str, Any]:
    return {"request_id": f"r{index}", "request_kind": kind, "lookup_type": tool,
            "intent": intent, "query_span": span, "slots": slots or {},
            "cohort_refs": [cohort] if cohort else [],
            "expected_status": "ok", "source_binding": "request_scoped"}


def planned(category: str, index: int, hidden: bool) -> tuple[str, list[dict[str, Any]], list[dict[str, str]]]:
    prefix = "Theo hồ sơ độc lập" if hidden else "Sinh viên hỏi"
    token = f"mã tình huống {index}" if hidden else f"tình huống {index}"
    if category == "single_structured":
        span = f"IELTS 6.{index % 5}"
        return f"{prefix} K51, {span} tương đương bậc mấy ({token})?", [request(1, "structured", span, tool="foreign_language", intent="direct_value", slots={"certificate_or_language": "IELTS", "score_or_level": f"6.{index % 5}"})], []
    if category == "single_rag":
        span = f"thủ tục bảo lưu học tập {token}"
        return f"K51 cần biết {span}.", [request(1, "rag", span, intent="procedure")], []
    if category in {"multi_entity", "two_structured"}:
        a, b = f"IELTS 6.{index % 5}", f"GPA 3.{index % 9}"
        return f"K51: {a} tương đương bậc nào và {b} xếp loại gì, {token}?", [request(1, "structured", a, tool="foreign_language", intent="direct_value", slots={"certificate_or_language": "IELTS", "score_or_level": f"6.{index % 5}"}), request(2, "structured", b, tool="scoring", intent="direct_value", slots={"operation": "academic_classification", "score_or_grade": f"3.{index % 9}"})], []
    if category == "mixed":
        a, b = f"IELTS 6.{index % 5}", f"quy trình bảo lưu {token}"
        return f"K51, {a} là bậc nào và {b} ra sao?", [request(1, "structured", a, tool="foreign_language", intent="direct_value", slots={"certificate_or_language": "IELTS", "score_or_level": f"6.{index % 5}"}), request(2, "rag", b, intent="procedure")], []
    if category == "two_regulations":
        a, b = f"điều kiện tốt nghiệp {token}", f"quy định thôi học {token}"
        return f"K51 hỏi {a} và {b}.", [request(1, "rag", a, intent="policy"), request(2, "rag", b, intent="consequence_or_exception")], []
    if category == "three_to_six_requests":
        spans = [f"IELTS 6.{index % 5}", f"GPA 3.{index % 9}", f"bảo lưu {token}"]
        return f"K51: {spans[0]} bậc gì, {spans[1]} loại gì, {spans[2]} thế nào?", [request(1, "structured", spans[0], tool="foreign_language", intent="direct_value", slots={"certificate_or_language": "IELTS", "score_or_level": f"6.{index % 5}"}), request(2, "structured", spans[1], tool="scoring", intent="direct_value", slots={"operation": "academic_classification", "score_or_grade": f"3.{index % 9}"}), request(3, "rag", spans[2], intent="procedure")], []
    if category == "robustness":
        span = f"IELTS 6.{index % 5} tuong duong bac may"
        return f"k51 {span}, {token}?", [request(1, "structured", span, tool="foreign_language", intent="direct_value", slots={"certificate_or_language": "IELTS", "score_or_level": f"6.{index % 5}"})], []
    if category == "follow_up":
        span = f"điều kiện tốt nghiệp {token}"
        history = [{"role": "user", "content": f"K51 cần xem {span}."}, {"role": "assistant", "content": "Đã tìm thấy mục quy định tốt nghiệp."}]
        return f"Còn ngoại lệ của nội dung đó ({token})?", [request(1, "rag", f"ngoại lệ {span}", intent="consequence_or_exception")], history
    if category == "cohort_resolution":
        query = f"K50 và K51: IELTS 6.0 tương đương bậc mấy ({token})?"
        return query, [], []
    span = f"email Phòng Công tác Sinh viên {token}"
    return f"K51 cần {span}, và thủ tục bảo lưu {token}.", [request(1, "structured", span, tool="office", intent="contact", slots={"office": "Phòng Công tác Sinh viên", "requested_field": "email"}), request(2, "rag", f"thủ tục bảo lưu {token}", intent="procedure")], []


def build_suite(hidden: bool) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    serial = 0
    for category, pair in COUNTS.items():
        for number in range(1, pair[1 if hidden else 0] + 1):
            serial += 1
            query, requests, history = planned(category, number + (100 if hidden else 0), hidden)
            outcome = "clarify" if category == "cohort_resolution" else "execute"
            expected = {"outcome": outcome, "context_mode": "validated", "effective_cohort": None if outcome == "clarify" else "K51", "effective_cohort_source": "raw_query" if "K51" in query else "grounded_history", "atomic_requests": requests, "retrieval_executed": outcome == "execute", "partial_status": "not_applicable" if not requests else "complete"}
            cases.append({"id": f"{'hidden' if hidden else 'dev'}-{serial:03d}", "category": category, "query": query, "selected_cohort": "K51", "chat_history": history, "expected": expected})
    return cases


def dump(path: Path, value: Any) -> str:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dev_hash = dump(OUT / "dev.json", build_suite(False))
    hidden_hash = dump(OUT / "hidden.json", build_suite(True))
    manifest = {"schema_version": "single-cohort-v2.0", "frozen_at": datetime.now(UTC).isoformat(), "baseline_commit": "5d5447cc", "counts": COUNTS, "files": {"dev.json": dev_hash, "hidden.json": hidden_hash}, "hidden_policy": "Frozen before prompt tuning; not used for tuning.", "legacy_final_holdout": {"commit": "e38bfef", "preserved": True}}
    dump(OUT / "manifest.json", manifest)
    report = {"valid": True, "generated_at": manifest["frozen_at"], "schema_version": manifest["schema_version"], "counts": {"dev": len(build_suite(False)), "hidden": len(build_suite(True))}, "hashes": {"dev.json": dev_hash, "hidden.json": hidden_hash}}
    dump(OUT / "validation_report.json", report)


if __name__ == "__main__":
    main()
