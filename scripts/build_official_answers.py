"""Compile source-backed answer drafts offline; never generate model answers."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import yaml

from scripts.build_official_deterministic import compile_task, records

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "data/eval/official_v1"
COHORTS = ("K48-K49", "K50", "K51")

FIELD_LABELS = {
    "certificate": "Chứng chỉ", "equivalent_level_3": "Bậc 3", "equivalent_level_4": "Bậc 4",
    "scholarship_level": "Loại học bổng", "label": "Loại học bổng", "multiplier": "Hệ số",
    "formula": "Công thức", "formula_text": "Công thức", "tuition_basis": "Căn cứ học phí",
    "academic_score_range": "Điểm học tập", "conduct_score_condition": "Điểm rèn luyện",
    "academic_classification": "Xếp loại học tập", "conduct_classification_condition": "Xếp loại rèn luyện",
    "unit_name": "Đơn vị", "program_name": "Ngành", "faculty_name": "Khoa",
    "office": "Địa điểm", "phone": "Điện thoại", "email": "Email", "website": "Website",
    "status": "Kết quả",
}


def answer_meaning(spec, task):
    """Project requested outputs, not internal resolver fields, into reference prose."""
    if spec.get("answer_meaning"):
        return spec["answer_meaning"]
    fields = task.get("expected_resolved_fields") or task["expected_evidence_fields"]
    if task.get("expected_evidence_rows"):
        fields = task["expected_evidence_rows"]
    rows = fields if isinstance(fields, list) else [fields]
    requested = spec.get("answer_fields")
    if requested is None and spec.get("table", [None])[0] in {"academic_classification", "conduct_classification"}:
        requested = ["Xếp loại"]
    projected = []
    for row in rows:
        if requested:
            row = {key: row[key] for key in requested}
        row = {key: value for key, value in row.items() if key not in {"rule_id", "cohort", "table_id", "input_requirements"}}
        assert row, "Empty requested answer meaning"
        projected.append("; ".join(f"{FIELD_LABELS.get(key, key)}: {value}" for key, value in row.items()))
    meaning = ". ".join(projected)
    subject = {"academic_classification": "Học tập", "conduct_classification": "Rèn luyện"}.get(spec.get("table", [None])[0])
    return f"{subject}: {meaning}" if subject else meaning


def build():
    definitions = yaml.safe_load((BUNDLE / "answer_authoring.yaml").read_text(encoding="utf-8"))
    parents = json.loads((ROOT / "data/processed/chunks/all_docstore_items.json").read_text(encoding="utf-8"))
    cases = []
    for group in definitions["policy_groups"]:
        assert len(group["cases"]) == 5
        for offset, (query, fact, anchor) in enumerate(group["cases"]):
            index = len(cases) + 1
            cohort = COHORTS[(index - 1) % 3]
            suffix = group.get("source_by_cohort", {}).get(cohort, group["source"])
            matches = [p for p in parents if p["cohort"] == cohort and p["_id"].endswith(suffix)]
            assert len(matches) == 1, (index, cohort, suffix)
            parent = matches[0]
            assert anchor in " ".join(parent["content"].split()), (index, anchor)
            assert query.strip() and fact.strip()
            meta = parent["metadata"]
            citation = {
                "parent_section_id": parent["_id"], "grade": 2, "cohort": cohort,
                "document_id": parent["document_id"], "content_type": "regulation_text",
                "source_section": meta["title"], "source_pages": meta["source_pages"],
            }
            style = "stress" if offset == 4 else "realistic"
            cases.append({
                "id": f"official_ans_{index:03d}", "suite": "answers",
                "query": query, "cohort": cohort, "history": [], "topic": group["topic"],
                "case_type": "regulation_true_rag", "expected_path": "regulation_rag",
                "expected_intent": "regulation_query", "expected_strategy": "hybrid_graph_retrieval",
                "expected_content_types": ["regulation_text"],
                "expected_answer_behavior": "direct_answer", "answerability": "answerable",
                "question_style": style, "eval_split": style,
                "tags": ["official_v1", "citation_required", style],
                "ground_truth": fact, "required_facts": [fact], "forbidden_claims": [],
                "relevance_judgments": [citation], "expected_citations": [citation],
                "gold_evidence": [{
                    "source_id": parent["_id"], "cohort": cohort, "anchor": anchor,
                    "content": parent["content"],
                    "content_sha256": hashlib.sha256(parent["content"].encode()).hexdigest(),
                }],
                "review_status": "ai_reviewed_pending_owner_approval",
                "review_method": "AI-assisted; not independent human review",
                "frozen": False, "independent_holdout": False,
                "na_assertions": {"fact_lock": "N/A: final-answer quality, not resolver execution"},
            })
    catalogs = records()
    for definition in definitions.get("additional_cases", []):
        index = len(cases) + 1
        cohort = COHORTS[(index - 1) % 3]
        facts = list(definition.get("facts", []))
        evidence, citations, structured, modes, units = [], [], [], [], []
        specs = definition.get("tasks", [] if definition.get("behavior") else [definition])
        for spec in specs:
            task, sources = compile_task(spec, cohort, catalogs)
            target = spec.get("cohort", cohort)
            modes.append(task["mode"])
            if "policy" in spec:
                assert spec.get("fact"), (index, "Missing authored policy fact")
                fact = spec["fact"]
                source = sources[0]
                parent = next(p for p in parents if p["_id"] == source["source_id"])
                meta = parent["metadata"]
                citation = {"parent_section_id": parent["_id"], "grade": 2,
                            "cohort": target, "document_id": parent["document_id"],
                            "content_type": "regulation_text", "source_section": meta["title"],
                            "source_pages": meta["source_pages"]}
                citations.append(citation)
                evidence.append({**source, "content": parent["content"]})
            else:
                fact = answer_meaning(spec, task)
                if spec.get("formula") == "gpa_weighted_average":
                    fact += "; ai là điểm học phần, ni là số tín chỉ; không lấy trung bình đều nếu tín chỉ khác nhau."
                for source in sources:
                    record = source.get("table", source.get("record", {}))
                    provenance = record.get("source_provenance", {})
                    source_id = (record.get("record_id") or provenance.get("record_id") or record.get("table_id")
                                 or record.get("rule_id") or record.get("program_id")
                                 or record.get("service_id"))
                    if source["catalog"] == "tables" and record.get("source_parent_id") and record.get("table_subtype"):
                        source_id = f"{record['source_parent_id']}_{record['table_subtype']}"
                    assert source_id, (index, record.keys())
                    catalog_name = {"tables": "structured_tables_registry"}.get(source["catalog"], source["catalog"])
                    structured.append({"source_id": source_id, "catalog": catalog_name,
                                       "cohort": target})
                    evidence.append({**source, "requested_cohort": target})
            scoped = f"[{target}] {fact}"
            facts.append(scoped)
            units.append({"cohort": target, "required_meaning": scoped, "mode": task["mode"]})
        behavior = definition.get("behavior")
        path = ("clarify" if behavior in {"clarify", "partial_clarification"}
                else "out_of_domain" if behavior == "out_of_domain"
                else "mixed" if set(modes) == {"rag", "structured"}
                else "structured" if "structured" in modes else "regulation_rag")
        kind = ("clarification" if path == "clarify" else "out_of_domain" if path == "out_of_domain"
                else "unanswerable" if behavior == "unanswerable" else "mixed_answer" if path == "mixed"
                else "structured_answer" if path == "structured" else "regulation_true_rag")
        style = "stress" if definition.get("stress") else "realistic"
        cases.append({
            "id": f"official_ans_{index:03d}", "suite": "answers", "query": definition["query"],
            "cohort": cohort, "history": [], "topic": "khac", "case_type": kind,
            "expected_path": path, "expected_answer_behavior": (
                "clarify_or_scope" if path == "clarify" else "abstain" if behavior else "direct_answer"),
            "answerability": "unanswerable" if behavior in {"unanswerable", "out_of_domain"} else "answerable",
            "question_style": style, "eval_split": style, "tags": ["official_v1", style],
            "ground_truth": "\n".join(facts), "required_facts": facts, "forbidden_claims": [],
            "relevance_judgments": citations, "expected_citations": citations,
            "expected_structured_sources": structured, "gold_evidence": evidence,
            "answer_units": units, "review_status": "ai_reviewed_pending_owner_approval",
            "review_method": "AI-assisted; not independent human review",
            "frozen": False, "independent_holdout": False,
            "na_assertions": {"fact_lock": "N/A: final-answer quality, not resolver execution"},
        })
    for case in cases:
        case["generation_model"] = "gemini-3.1-flash-lite"
        case["judge_model"] = "openai/gpt-oss-120b"
        targets = list(dict.fromkeys(u["cohort"] for u in case.get("answer_units", [])))
        case["requested_cohorts"] = targets or [case["cohort"]]
        if len(targets) > 1:
            case["allocation_cohort"] = case["cohort"]
            case["cohort"] = "general"
        case["cohort_sensitivity"] = "multi_cohort_risk" if len(targets) > 1 else "single_cohort"
        case["question_specificity"] = "specific"
        case.setdefault("expected_intent", "regulation_query")
        case.setdefault("expected_strategy", "deterministic_lookup" if case["expected_path"] == "structured" else "hybrid_graph_retrieval")
        case["lexical_fact_check_applicable"] = False
        case["evaluation_notes"] = (
            "Chấm tương đương ngữ nghĩa, không khớp nguyên văn gold hay mã nội bộ. "
            "Phải trả lời mọi ý được hỏi; một ý cần hỏi thêm không thay thế các ý có đủ dữ kiện. "
            "Với nhiều khóa/thực thể, mỗi kết quả phải gắn đúng đối tượng. Không bắt ghi tên khóa "
            "trong câu trả lời chỉ hỏi một khóa. Không bắt liệt kê toàn bảng hoặc khoảng điểm "
            "khi câu hỏi chỉ cần nhãn xếp loại. Chấp nhận số/thời gian tương đương và số điện thoại "
            "hợp lệ bất kỳ trong các số liên hệ của đúng đơn vị, trừ khi câu hỏi yêu cầu tất cả. "
            "Đường xử lý chỉ là metadata mô tả, không phải tiêu chí chất lượng đáp án."
        )
        modes = [u["mode"] for u in case.get("answer_units", [])]
        features = []
        if len(modes) > 1:
            features.append("multiple_requests")
            features.append("regulation_structured" if len(set(modes)) > 1 else "regulation_regulation" if modes[0] == "rag" else "structured_structured")
        if len(modes) >= 3:
            features.append("three_requests")
        if len(targets) > 1:
            features.append("multi_cohort")
        if case["expected_path"] == "clarify" and case.get("expected_structured_sources"):
            features.append("partial_clarification")
        case["coverage_features"] = features
    assert len(cases) == 150
    return cases


if __name__ == "__main__":
    assert not (BUNDLE / "manifest.json").exists(), "Do not overwrite a frozen bundle"
    cases = build()
    (BUNDLE / "generated_answer_cases.json").write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Compiled {len(cases)}/150 answer drafts; no model calls or freeze.")
    print(dict(Counter(c["question_style"] for c in cases)))
