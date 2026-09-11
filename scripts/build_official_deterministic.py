"""Compile hand-authored selectors into source-backed V9 evaluator contracts.

Offline only. Does not import Planner, resolver or Composer. Gold comes from
source catalogs, not old evaluation questions or model responses.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "data/eval/official_v1"
COHORTS = ("K48-K49", "K50", "K51")
CONTRACT = "query-plan-grounded-outcome-v9"
# Size and balance checks used when an authoring file declares no `settings.expected`.
V1_EXPECTED = {"cases": 135, "per_cohort": 45, "styles": {"realistic": 108, "stress": 27}}
V1_OVERLAP_POLICY = "Historical overlap screening not performed by owner decision. No independent holdout claim."
# Optional per-case authoring fields copied onto the compiled case for slicing and provenance.
CASE_METADATA_FIELDS = ("slice", "stress_type", "author", "reviewer")
PATHS = {
    "tables": "data/processed/tables/structured_tables_registry.json",
    "formula": "data/processed/tables/formula_rules.json",
    "office": "data/processed/directories/student_office_profiles.json",
    "faculty": "data/processed/directories/student_faculty_profiles.json",
    "program": "data/processed/directories/program_directory.json",
    "service": "data/processed/directories/student_service_directory.json",
    "parents": "data/processed/chunks/all_docstore_items.json",
}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def one(items):
    assert len(items) == 1, f"Expected unique authoring source, got {len(items)}"
    return items[0]


def records():
    return {key: read(ROOT / path) for key, path in PATHS.items()}


def applicable(record, cohort):
    return record.get("cohort") == cohort or (
        record.get("applicability_validated") is True
        and cohort in record.get("applicable_cohorts", [])
    )


def rows(table):
    value = table["rows"]
    return value if isinstance(value, list) else [value]


def input_alternatives(value):
    """Accept equivalent decimal spelling without altering the evaluated input."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        spellings = [format(value, ".15g"), format(value, ".2f")]
        return [value, *dict.fromkeys(s for text in spellings for s in (text, text.replace(".", ",")))]
    return [value]


def compile_task(spec, cohort, catalogs):
    if spec.get("directory_group"):
        compiled = [compile_task(unit, cohort, catalogs) for unit in spec["directory_group"]]
        tasks = [task for task, _ in compiled]
        assert len({task["lookup_type"] for task in tasks}) == 1
        assert all(task["lookup_type"] in {"office", "faculty", "student_service"}
                   and task["cohorts"] == [cohort] for task in tasks)
        return {"mode": "structured", "lookup_type": tasks[0]["lookup_type"],
                "cohorts": [cohort], "fact_lock_applicable": False,
                "expected_evidence_rows": [task["expected_evidence_fields"] for task in tasks]}, [
                    item for _, evidence in compiled for item in evidence]
    if spec.get("execution_units"):
        units, evidence = [], []
        for unit in spec["execution_units"]:
            task, source = compile_task(unit, cohort, catalogs)
            units.append(task)
            evidence.extend(source)
        assert len({u["lookup_type"] for u in units}) == 1
        return {"mode": "structured", "lookup_type": units[0]["lookup_type"],
                "cohorts": [c for u in units for c in u["cohorts"]],
                "execution_units": units, "fact_lock_applicable": False}, evidence
    if spec.get("clarify_task"):
        return {"mode": "clarify", "cohorts": [cohort]}, []
    if spec.get("cohorts"):
        assert "policy" in spec, "Grouped structured fact-lock needs explicit per-cohort execution gold"
        evidence = []
        for target in spec["cohorts"]:
            single = {k: v for k, v in spec.items() if k != "cohorts"}
            _, source = compile_task(single, target, catalogs)
            evidence.extend(source)
        return {"mode": "rag", "cohorts": spec["cohorts"]}, evidence
    cohort = spec.get("cohort", cohort)
    assert cohort in COHORTS
    if "policy" in spec:
        suffix, quote = spec["policy"]
        parent = one([p for p in catalogs["parents"] if p["cohort"] == cohort and p["_id"].endswith(suffix)])
        assert quote in " ".join(parent["content"].split()), (parent["_id"], quote)
        return {"mode": "rag", "cohorts": [cohort]}, [{
            "catalog": "parents", "source_id": parent["_id"], "cohort": cohort,
            "quote": quote, "content_sha256": hashlib.sha256(parent["content"].encode()).hexdigest(),
        }]

    task = {"mode": "structured", "cohorts": [cohort], "fact_lock_applicable": False}
    gold = []
    fields = None
    selected = []
    lock = False
    if "uncertain_course" in spec:
        assert cohort == "K51" and spec["uncertain_course"] == 4.6
        selected = [t for t in catalogs["tables"] if t["cohort"] == cohort
                    and t["table_subtype"] in {"grade_scale", "pass_fail_ungraded"}]
        assert len(selected) == 3
        chosen = []
        fields = {"table_id": selected[0]["table_id"]}
        task.update(lookup_type="scoring", slot_value_alternatives={"operation": ["pass_threshold"]})
    elif "table" in spec:
        subtype, row_index, operation, *scope = spec["table"]
        candidates = [t for t in catalogs["tables"] if t["cohort"] == cohort and t["table_subtype"] == subtype]
        if subtype == "grade_scale" and cohort == "K51":
            assert scope, "K51 grade scale requires explicit applicability"
            candidates = [t for t in candidates if t["table_id"].endswith(scope[0])]
        table = one(candidates)
        selected = [table]
        operations = [operation]
        if subtype == "pass_fail_ungraded":
            # Both labels are valid ways to ask for the source-defined
            # pass/fail threshold; keep the authored operation first.
            operations.append("pass_threshold")
        task.update(lookup_type="scoring", required_slot_keys=["operation"],
                    slot_value_alternatives={"operation": list(dict.fromkeys(operations))})
        if scope:
            task["slot_value_alternatives"]["course_scope"] = scope
        chosen = rows(table) if row_index == "all" else [rows(table)[row_index]]
        if spec.get("output_rows"):
            chosen = [rows(table)[i] for i in spec["output_rows"]]
        fields = chosen[0] if row_index != "all" else {"table_id": table["table_id"]}
        lock = row_index != "all"
    elif "foreign" in spec:
        certificate, field = spec["foreign"]
        table = one([t for t in catalogs["tables"] if t["table_type"] == "foreign_language" and applicable(t, cohort)])
        selected = [table]
        chosen = rows(table) if certificate == "all" else [one([r for r in rows(table) if r["certificate"] == certificate])]
        task["lookup_type"] = "foreign_language"
        if certificate == "all":
            fields = {"table_id": table["table_id"]}
        else:
            task["required_slot_keys"] = ["certificate_or_language"]
            fields = {"certificate": certificate}
            for key in (["equivalent_level_3", "equivalent_level_4"] if field == "both" else [field]):
                fields[key] = chosen[0][key]
            lock = True
    elif "duration" in spec:
        mode, row_index = spec["duration"]
        table = one([t for t in catalogs["tables"] if t["cohort"] == cohort and t["table_id"].endswith("study_duration_" + mode)])
        selected = [table]
        chosen = rows(table) if row_index == "all" else [rows(table)[row_index]]
        fields = chosen[0] if row_index != "all" else {"table_id": table["table_id"]}
        # Rules for bridging are contextual policy, not a direct output here.
        fields = {k: v for k, v in fields.items() if k != "Quy tắc đối với sinh viên liên thông"}
        task.update(lookup_type="study_duration", required_slot_keys=["training_mode"],
                    slot_value_alternatives={"training_mode": [mode]})
        lock = row_index != "all"
    elif "scholarship" in spec:
        subtype, row_index = spec["scholarship"]
        selected = [t for t in catalogs["tables"] if t["cohort"] == cohort and t["table_subtype"] in (
            ["scholarship_amount", "scholarship_classification"] if subtype == "both" else [subtype])]
        assert selected
        task["lookup_type"] = "scholarship_classification"
        if subtype != "both":
            task["slot_value_alternatives"] = {"aspect": ["amount" if subtype == "scholarship_amount" else "classification"]}
        if row_index == "all":
            chosen = [r for t in selected for r in rows(t)]
            fields = {"table_id": selected[0]["table_id"]}
        elif row_index == "giỏi":
            chosen = [r for r in rows(one(selected)) if r.get("scholarship_level", r.get("label")) == "Giỏi"]
            fields = {"scholarship_level": "Giỏi"}
            lock = len(chosen) == 1
        else:
            chosen = [rows(one(selected))[row_index]]
            fields = chosen[0]
            lock = True
    else:
        kind = next(k for k in ("formula", "office", "faculty", "program", "service") if k in spec)
        pool = [r for r in catalogs[kind] if r["cohort"] == cohort]
        task["lookup_type"] = "student_service" if kind == "service" else kind
        if kind == "formula":
            record = one([r for r in pool if r["rule_id"] == spec[kind]])
            fields = {k: record[k] for k in ("rule_id", "formula_text")}
            task["slot_value_alternatives"] = {"formula_type": [spec[kind]]}
        elif kind == "program":
            record = one([r for r in pool if r["program_name"] == spec[kind]])
            fields = {k: record[k] for k in ("program_name", "faculty_name", "cohort")}
            task["slot_value_alternatives"] = {"requested_field": ["faculty", "all"]}
        else:
            entity, field = spec[kind]
            record = one([r for r in pool if (entity in r["service"] if kind == "service" else r["unit_name"] == entity)])
            fields = {"unit_name": record["unit_name"], "cohort": cohort}
            keys = ["email", "office"] if field == "all" else ([] if field == "unit_name" else [field])
            for key in keys:
                value = record.get(key) or "; ".join(record.get(key + "s", []))
                assert value, (cohort, entity, key)
                fields[key] = value
            expected_field = "unit" if field == "unit_name" else field
            task["slot_value_alternatives"] = {"requested_field": [expected_field, "all"]}
            if field == "all":
                task["slot_value_alternatives"]["requested_field"].append(keys)
        gold.append({"catalog": kind, "record": record})
        task["fact_lock_reason"] = "N/A: formula definition or directory record, not a resolved scalar table lookup."

    if selected:
        task["expected_source_ids"] = [t["table_id"] for t in selected]
        gold.extend({"catalog": "tables", "table": t, "selected_rows": chosen} for t in selected)
        task["fact_lock_reason"] = (
            "Explicit input or named row; one applicable table and one row; no semantic guessing."
            if lock else "N/A: whole table, multiple rows, or multiple applicable tables requested."
        )
        if not lock and chosen:
            task["expected_evidence_rows"] = [
                {k: v for k, v in r.items() if k != "input_requirements"}
                for r in chosen
            ]
    task["expected_evidence_fields"] = copy.deepcopy(fields)
    if "input_slots" in spec:
        task.setdefault("slot_value_alternatives", {}).update(
            {key: input_alternatives(value) for key, value in spec["input_slots"].items()}
        )
    task["fact_lock_applicable"] = lock
    if lock:
        task.update(resolved_result_required=True, expected_resolved_fields=copy.deepcopy(fields))
        if spec.get("resolved_output_fields"):
            # Keep full source evidence for review, but require only the outputs
            # actually requested. A narrow question need not repeat every column.
            task["expected_resolved_fields"] = {
                key: copy.deepcopy(fields[key]) for key in spec["resolved_output_fields"]
            }
        if spec.get("table", [None])[0] == "pass_fail_ungraded":
            # Preserve the source-defined public status label.
            task["expected_resolved_fields"] = {"status": "Đạt" if spec["table"][1] == 0 else "Chưa đạt"}
    return task, gold


def build(bundle: Path = BUNDLE):
    """Compile `<bundle>/deterministic_authoring.yaml` into V9 case contracts.

    Optional `settings` in the authoring file name the id prefix, the holdout claim and
    the expected size and balance. Optional per-case fields: `selected_cohort` (the cohort
    picked in the UI; otherwise cohorts rotate in file order), `history` (earlier turns as
    role/content items) and the metadata in CASE_METADATA_FIELDS.
    """
    authoring = yaml.safe_load((bundle / "deterministic_authoring.yaml").read_text(encoding="utf-8"))
    definitions = authoring["cases"]
    settings = authoring.get("settings") or {}
    expected = settings.get("expected", V1_EXPECTED)
    assert len(definitions) == expected["cases"], len(definitions)
    catalogs = records()
    result = []
    for index, definition in enumerate(definitions, 1):
        cohort = definition.get("selected_cohort") or COHORTS[(index - 1) % 3]
        tasks, gold = [], []
        state = "clarify" if "clarify" in definition else "out_of_domain" if definition.get("out_of_domain") else "answer"
        if state == "answer":
            for spec in definition.get("tasks", [definition]):
                task, evidence = compile_task(spec, cohort, catalogs)
                tasks.append(task)
                gold.extend(evidence)
        modes = sorted({t["mode"] for t in tasks})
        outcome = {"name": "source-grounded-contract", "state": state, "allowed_modes": modes,
                   "task_count": {"min": len(tasks), "max": len(tasks)}, "required_tasks": tasks}
        if definition.get("partial_clarification"):
            outcome["state"] = "clarify"
        if state == "clarify":
            outcome.update(allowed_modes=["clarify", "structured"], task_count={"min": 1, "max": 1})
        if "structured" in modes:
            outcome["structured_evidence"] = "required"
        # Retrieval quality belongs to the retrieval suite. Here only routing is asserted.
        style = "stress" if definition.get("stress") else "realistic"
        case = {
            "id": f"{settings.get('id_prefix', 'official_det')}_{index:03d}", "suite": "deterministic",
            "query": definition["query"], "cohort": cohort, "history": definition.get("history", []),
            "tags": [bundle.name, definition["category"], style], "category": definition["category"],
            "topic": "khac", "question_style": style, "eval_split": style,
            "coverage_features": definition.get("coverage_features", []),
            "expected_intent": "query_plan", "expected_strategy": "query_plan_execution",
            "expected_path": state if state != "answer" else "mixed" if len(modes) > 1 else "regulation_rag" if modes == ["rag"] else "structured",
            "contract_version": CONTRACT, "accepted_outcomes": [outcome],
            "bind_execution_to_plan": True,
            "gold_evidence": gold, "author_review_state": "ai_reviewed_pending_owner_approval",
            "query_origin": f"{bundle.name}_hand_authored", "frozen": False,
            "independent_holdout": bool(settings.get("independent_holdout", False)),
            "overlap_policy": settings.get("overlap_policy", V1_OVERLAP_POLICY),
            "na_assertions": {"final_answer": "N/A: no Composer execution in this suite",
                              "retrieval_quality": "N/A: measured in separate retrieval suite"},
        }
        if "uncertain_course" in definition:
            case["accepted_outcomes"].append({
                "name": "ask-course-type", "state": "clarify",
                "allowed_modes": ["clarify", "structured"],
                "task_count": {"min": 1, "max": 1}, "required_tasks": [],
            })
            case["gold_rationale"] = (
                "K51, 4.6 without course type: ask for course type or retain all applicable tables "
                "for a conditional answer. Do not require one resolved_result or invent course scope."
            )
        if definition.get("allow_safe_clarification"):
            primary_task = tasks[0]
            case["accepted_outcomes"].append({
                "name": "safe-clarification",
                "state": "clarify",
                "allowed_modes": ["clarify", "structured"],
                "task_count": {"min": 1, "max": 1},
                "clarification_question_required": True,
                # The answer may safely abstain, but the Planner must still
                # identify the intended capability and cohort.
                "required_tasks": [{
                    "mode": "clarify",
                    "lookup_type": primary_task.get("lookup_type"),
                    "cohorts": primary_task["cohorts"],
                    "fact_lock_applicable": False,
                }],
            })
        for variant_index, specs in enumerate(definition.get("alternative_tasks", []), 1):
            alternative_tasks = []
            for spec in specs:
                task, evidence = compile_task(spec, cohort, catalogs)
                alternative_tasks.append(task)
                for item in evidence:
                    if item not in gold:
                        gold.append(item)
            alternative_modes = sorted({task["mode"] for task in alternative_tasks})
            alternative = {
                "name": f"equivalent-decomposition-{variant_index}", "state": "answer",
                "allowed_modes": alternative_modes,
                "task_count": {"min": len(alternative_tasks), "max": len(alternative_tasks)},
                "required_tasks": alternative_tasks,
            }
            if "structured" in alternative_modes:
                alternative["structured_evidence"] = "required"
            case["accepted_outcomes"].append(alternative)
        if state != "answer":
            case["gold_rationale"] = definition.get("clarify", "Outside the student-handbook assistant domain; do not fabricate an answer from handbook sources.")
        targets = {c for t in tasks for c in t.get("cohorts", [])}
        case["cohort_sensitivity"] = "multi_cohort_risk" if len(targets) > 1 else "single_cohort"
        case["question_specificity"] = "ambiguous" if state == "clarify" else "specific"
        case["expected_answer_behavior"] = "clarify_or_scope" if state == "clarify" else "abstain" if state == "out_of_domain" else "direct_answer"
        case.update({key: definition[key] for key in CASE_METADATA_FIELDS if key in definition})
        result.append(case)
    if expected.get("per_cohort"):
        assert Counter(c["cohort"] for c in result) == dict.fromkeys(COHORTS, expected["per_cohort"])
    if expected.get("styles"):
        assert Counter(c["question_style"] for c in result) == expected["styles"]
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", default=BUNDLE.name, help="Folder under data/eval, e.g. official_v2.")
    bundle = ROOT / "data/eval" / parser.parse_args().bundle
    if (bundle / "deterministic_manifest.json").exists():
        raise RuntimeError("Deterministic suite already frozen; refusing to rebuild")
    cases = build(bundle)
    target = bundle / "deterministic_tool_cases.json"
    target.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Compiled {len(cases)} source-backed contracts; no inference executed.")
