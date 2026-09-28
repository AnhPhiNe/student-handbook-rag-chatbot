"""Measure the handbook texts without articles on their development questions.

Runs the runtime answer pipeline on data/eval/development/supplementary_questions.yaml
and checks three things per case:

  route      every planner task goes to RAG (these texts have no structured tool)
  retrieved  the gold parent is among the answer's citations or task evidence
  facts      the answer states every must_include fact (case-insensitive)

Development data, not a hold-out. The collections are the ones named in .env
(the pipeline reloads .env over the environment), and the report records them.

    python -m scripts.eval_supplementary_questions
"""
import argparse
import json
import os
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.common.env_loader import load_project_env
from src.evaluation.answers import generate_answers
from src.evaluation.shared import citation_parent_id

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data/eval/development/supplementary_questions.yaml"
REPORTS = ROOT / "data/eval/reports"


def fold(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", str(text)).casefold().split())


def evidence_parent_ids(record: dict) -> set[str]:
    ids = {citation_parent_id(citation) for citation in record.get("citations") or []}
    for task in record.get("task_results") or []:
        ids.update(citation_parent_id(item) for item in task.get("evidence") or [] if isinstance(item, dict))
    return ids - {""}


def check(case: dict, record: dict) -> dict:
    tasks = (record.get("query_plan") or {}).get("tasks") or []
    answer = fold(record.get("answer") or "")
    missing = [fact for fact in case["must_include"] if fold(fact) not in answer]
    return {
        "id": case["id"],
        "cohort": case["cohort"],
        "query": case["query"],
        "status": record.get("status"),
        "routes": [task.get("mode") for task in tasks],
        "route_ok": bool(tasks) and all(task.get("mode") == "rag" for task in tasks),
        "retrieved_ok": case["gold_parent"] in evidence_parent_ids(record),
        "missing_facts": missing,
        "facts_ok": not missing,
        "answer": record.get("answer") or "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, help="Report directory (default: a new timestamped one)")
    args = parser.parse_args()
    load_project_env()
    collections = {key: os.environ.get(key) for key in ("QDRANT_COLLECTION_NAME", "MONGODB_PARENT_COLLECTION")}

    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out or REPORTS / f"supplementary_questions_{stamp}"
    run = generate_answers(cases, cache_path=out / "answer_cache.json", resume=True,
                           checkpoint_context=collections)
    records = {row["id"]: row for row in run["cases"]}
    results = [check(case, records[case["id"]]) for case in cases if case["id"] in records]
    summary = {key: sum(row[key] for row in results) for key in ("route_ok", "retrieved_ok", "facts_ok")}
    summary["n"] = len(results)
    summary["collections"] = collections
    (out / "results.json").write_text(
        json.dumps({"summary": summary, "cases": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for row in results:
        marks = "".join("." if row[key] else "x" for key in ("route_ok", "retrieved_ok", "facts_ok"))
        note = f" missing={row['missing_facts']}" if row["missing_facts"] else ""
        print(f"{row['id']} {row['cohort']:8} {marks} routes={row['routes']}{note}")
    print(f"route {summary['route_ok']}/{summary['n']}  retrieved {summary['retrieved_ok']}/{summary['n']}  "
          f"facts {summary['facts_ok']}/{summary['n']}  -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
