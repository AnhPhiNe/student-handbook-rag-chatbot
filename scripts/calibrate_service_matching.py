"""Calibrate student-service matching thresholds on labeled development cases.

Scores every case once with the runtime scoring functions, then replays the
runtime decision (`_select_confident_candidates`) over a threshold grid. The
choice rule is fixed before looking at results: fewest wrong units on the dev
split, then most correct answers, then the more cautious setting (larger
margin, then higher confidence). The chosen setting is checked on the test
split. A wrong unit is the only real error; asking to clarify is safe.

    python -m scripts.calibrate_service_matching --embedding local \
        --v1-report data/eval/reports/official_v1_deterministic_<stamp>
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from scripts.prepare_official_eval import ROOT

CASES = ROOT / "data/eval/development/service_matching_cases.yaml"
CONFIDENCES = [round(0.40 + 0.02 * i, 2) for i in range(29)]  # 0.40 .. 0.96
MARGINS = [round(0.02 * i, 2) for i in range(11)]  # 0.00 .. 0.20


def split_of(case_id: str) -> str:
    """Stable 70/30 split by id hash, the same for every embedding."""
    return "test" if int(hashlib.sha256(case_id.encode()).hexdigest(), 16) % 10 >= 7 else "dev"


def v1_cases(report: Path) -> list[dict]:
    """The planner's service slot and gold unit for each official_v1 service task."""
    rows = json.loads((report / "deterministic.json").read_text(encoding="utf-8"))["cases"]
    out = []
    for case in rows:
        gold = {task.get("expected_resolved_fields", task.get("expected_evidence_fields", {})).get("unit_name")
                for outcome in case["accepted_outcomes"] for task in outcome.get("required_tasks", [])
                if task.get("lookup_type") == "student_service"} - {None}
        for task in (case.get("query_plan") or {}).get("tasks", []):
            service = (task.get("slots") or {}).get("service")
            if task.get("lookup_type") == "student_service" and gold and service:
                out.append({"id": f"v1_{case['id'][-3:]}", "service": service, "expect": "one_of" if len(gold) > 1 else "unit",
                            "units": sorted(gold), "cohort": (task.get("cohorts") or [case["cohort"]])[0]})
    return out


def score_cases(cases: list[dict], directory: list[dict], model) -> list[dict]:
    """Record every candidate's lexical and semantic score once per case."""
    from src.common.cohort import is_validated_source_applicable, normalize_cohort
    from src.retrieval.core.office_lookup import _lexical_candidate_score, _semantic_candidate_scores

    scored = []
    for case in cases:
        cohort = normalize_cohort(case["cohort"])
        records = [r for r in directory if is_validated_source_applicable(r, cohort)]
        semantic = _semantic_candidate_scores(case["service"], records, model)
        candidates = [{"record": r, "lexical": _lexical_candidate_score(case["service"], r), "semantic": s}
                      for r, s in zip(records, semantic, strict=True)]
        scored.append({**case, "candidates": candidates})
    return scored


def rank(candidates: list[dict]) -> list[dict]:
    """The runtime confidence formula and best-per-entity ranking."""
    from src.retrieval.core.office_lookup import _entity_key

    best: dict[str, dict] = {}
    for c in candidates:
        lex, sem = c["lexical"], c["semantic"]
        confidence = 1.0 if lex >= 0.98 else max(lex, 0.65 * lex + 0.35 * sem, 0.85 * sem)
        item = {"record": c["record"], "confidence": confidence, "lexical_score": lex, "semantic_score": sem}
        key = _entity_key(c["record"])
        if key not in best or confidence > best[key]["confidence"]:
            best[key] = item
    return sorted(best.values(), key=lambda item: item["confidence"], reverse=True)


def outcome(case: dict, ranked: list[dict], min_confidence: float, margin: float) -> str:
    """correct / wrong / clarify / miss for one case under one setting."""
    from src.retrieval.core.office_lookup import _select_confident_candidates

    kept, ambiguity, _ = _select_confident_candidates(
        candidate_text=case["service"], ranked=ranked, require_confident_match=True,
        min_confidence=min_confidence, ambiguity_margin=margin)
    if ambiguity is not None:
        return "correct" if case["expect"] in {"one_of", "none"} else "clarify"
    if kept is None:
        return "correct" if case["expect"] == "none" else "miss"
    unit = kept[0]["record"].get("unit_name")
    if case["expect"] == "none":
        return "wrong"
    return "correct" if unit in case["units"] else "wrong"


def tally(scored: list[dict], rankings: dict, conf: float, margin: float) -> dict:
    counts = {"correct": 0, "wrong": 0, "clarify": 0, "miss": 0}
    for case in scored:
        counts[outcome(case, rankings[case["id"]], conf, margin)] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedding", choices=("none", "local"), required=True,
                        help="none: lexical only; local: the configured retrieval embedding model.")
    parser.add_argument("--v1-report", help="official_v1 deterministic report whose planner slots to add.")
    args = parser.parse_args()

    from src.common.io import load_yaml
    spec = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    cases = [{**c, "cohort": spec["cohort"]} for c in spec["cases"]]
    if args.v1_report:
        cases += v1_cases(ROOT / args.v1_report)
    model_name = None
    model = None
    if args.embedding == "local":
        from src.retrieval.core.embedding_model import load_embedding_model
        model_name = load_yaml(ROOT / "configs/retrieval.yaml")["embedding"]["model_name"]
        model = load_embedding_model(model_name)
    directory_path = ROOT / "data/processed/directories/student_service_directory.json"
    directory = json.loads(directory_path.read_text(encoding="utf-8"))
    scored = score_cases(cases, directory, model)
    rankings = {case["id"]: rank(case["candidates"]) for case in scored}
    parts = {name: [c for c in scored if split_of(c["id"]) == name] for name in ("dev", "test")}

    grid = [{"min_confidence": t, "ambiguity_margin": m, **tally(parts["dev"], rankings, t, m)}
            for t in CONFIDENCES for m in MARGINS]
    chosen = min(grid, key=lambda g: (g["wrong"], -g["correct"], -g["ambiguity_margin"], -g["min_confidence"]))
    registry = load_yaml(ROOT / "configs/structured_lookup_registry.yaml")
    current = registry["tools"]["student_service"]["matching"]
    settings = {"current": (float(current["min_confidence"]), float(current["ambiguity_margin"])),
                "chosen": (chosen["min_confidence"], chosen["ambiguity_margin"])}
    summary = {name: {split: tally(parts[split], rankings, *setting) | {"n": len(parts[split])}
                      for split in ("dev", "test")}
               for name, setting in settings.items()}
    per_case = []
    for case in scored:
        ranked = rankings[case["id"]]
        per_case.append({
            "id": case["id"], "split": split_of(case["id"]), "service": case["service"], "expect": case["expect"],
            "units": case.get("units", []),
            "top": [{"unit": r["record"].get("unit_name"), "confidence": round(r["confidence"], 3),
                     "lexical": round(r["lexical_score"], 3), "semantic": round(r["semantic_score"], 3)}
                    for r in ranked[:3]],
            "current": outcome(case, ranked, *settings["current"]),
            "chosen": outcome(case, ranked, *settings["chosen"]),
        })
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "embedding": args.embedding,
              "embedding_model": model_name, "cases": str(CASES.relative_to(ROOT).as_posix()),
              "v1_report": args.v1_report, "n": len(scored),
              "rule": "dev: fewest wrong, then most correct, then larger margin, then higher confidence",
              "settings": {k: {"min_confidence": v[0], "ambiguity_margin": v[1]} for k, v in settings.items()},
              "summary": summary, "grid_dev": grid, "cases_detail": per_case}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "data/eval/reports" / f"service_matching_calibration_{args.embedding}_{stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Output: {out}")
    print(json.dumps({"settings": report["settings"], "summary": summary}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
