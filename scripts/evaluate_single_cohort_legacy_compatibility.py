"""Run the frozen legacy suites under the single-cohort compatibility policy."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.env_loader import load_project_env  # noqa: E402
from src.evaluation.artifact_fingerprint import (  # noqa: E402
    release_artifact_fingerprint,
)
from src.evaluation.dataset import (  # noqa: E402
    DATASET_FILES,
    load_json,
    validate_bundle,
)
from src.evaluation.gates import evaluate_gates  # noqa: E402
from src.evaluation.single_cohort_gold import (  # noqa: E402
    legacy_compatibility_report,
)
from src.evaluation.suites import (  # noqa: E402
    evaluate_deterministic,
    evaluate_production,
    evaluate_retrieval,
    generate_answers,
    judge_answers,
)
from src.generation.answer_pipeline import AnswerPipeline  # noqa: E402


LEGACY_DIR = ROOT / "data/eval/final_holdout"


def _commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _complete_and_gated(
    report: Mapping[str, Any], *, suite: str, expected_n: int
) -> dict[str, Any]:
    actual_n = int((report.get("summary") or {}).get("n") or 0)
    gates = evaluate_gates(suite, dict(report.get("summary") or {}))
    return {
        "expected_n": expected_n,
        "actual_n": actual_n,
        "complete": actual_n == expected_n,
        "gates": gates,
        "passed": actual_n == expected_n and bool(gates.get("passed")),
    }


def _rejection_compatibility(cases: list[dict[str, Any]]) -> dict[str, Any]:
    pipeline = AnswerPipeline()
    rows = []
    for case in cases:
        try:
            result = pipeline._run_retrieval(
                str(case.get("query") or case.get("question") or ""),
                cohort=None,
                chat_history=case.get("chat_history") or [],
            )
            provider_failure = bool(result.get("infrastructure_error"))
            passed = bool(
                not provider_failure
                and result.get("retrieval_executed") is False
                and result.get("retrieval_query") is None
                and not result.get("retrieved_items")
                and (
                    result.get("needs_clarification")
                    or result.get("out_of_domain")
                )
            )
            rows.append(
                {
                    "id": case.get("id"),
                    "passed": passed,
                    "provider_failure": provider_failure,
                    "route": (result.get("router_decision") or {}).get("route"),
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "id": case.get("id"),
                    "passed": False,
                    "provider_failure": True,
                    "error_type": type(exc).__name__,
                }
            )
    return {
        "summary": {
            "n": len(rows),
            "pass_rate": (
                sum(bool(row["passed"]) for row in rows) / len(rows)
                if rows
                else 0.0
            ),
            "provider_failures": sum(
                bool(row.get("provider_failure")) for row in rows
            ),
        },
        "cases": rows,
    }


def main() -> None:
    load_project_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--backend", choices=("qdrant", "chroma"), default="qdrant")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    validation = validate_bundle(
        LEGACY_DIR,
        ROOT / "data/processed/chunks/all_docstore_items.json",
        require_frozen=True,
    )
    if not validation["valid"]:
        raise SystemExit("Frozen legacy bundle is invalid: " + "; ".join(validation["errors"]))
    deterministic = load_json(LEGACY_DIR / DATASET_FILES["deterministic"])
    retrieval = load_json(LEGACY_DIR / DATASET_FILES["retrieval"])
    answers = load_json(LEGACY_DIR / DATASET_FILES["answers"])
    production = load_json(LEGACY_DIR / DATASET_FILES["production"])
    retrieval_current = [case for case in retrieval if case.get("cohort") != "general"]
    retrieval_deferred = [case for case in retrieval if case.get("cohort") == "general"]
    answers_current = [case for case in answers if case.get("cohort") != "general"]
    answers_deferred = [case for case in answers if case.get("cohort") == "general"]

    args.work_dir.mkdir(parents=True, exist_ok=True)
    deterministic_report = evaluate_deterministic(deterministic)
    retrieval_report = evaluate_retrieval(
        retrieval_current,
        backend=args.backend,
        mode="vector_primary_graph_supplement",
        scope="end_to_end",
    )
    answer_cache = args.work_dir / "answer_cache.json"
    generation_report = generate_answers(
        answers_current,
        cache_path=answer_cache,
        resume=args.resume,
    )
    judge_report = judge_answers(
        answers_current,
        load_json(answer_cache),
        checkpoint_path=args.work_dir / "judge_checkpoint.json",
        resume=args.resume,
    )
    rejection_report = _rejection_compatibility(
        retrieval_deferred + answers_deferred
    )
    production_report = evaluate_production(
        production,
        base_url=args.base_url,
    )

    checks = {
        "legacy_hashes": legacy_compatibility_report(ROOT)[
            "legacy_bundle_preserved"
        ],
        "deterministic_120": _complete_and_gated(
            deterministic_report, suite="deterministic", expected_n=120
        ),
        "retrieval_136": _complete_and_gated(
            retrieval_report, suite="retrieval", expected_n=136
        ),
        "generation_85": {
            "expected_n": 85,
            "actual_n": int((generation_report.get("summary") or {}).get("n") or 0),
        },
        "judge_85": _complete_and_gated(
            judge_report, suite="judge", expected_n=85
        ),
        "general_rejection_59": {
            **rejection_report["summary"],
            "passed": bool(
                rejection_report["summary"]["n"] == 59
                and rejection_report["summary"]["pass_rate"] == 1.0
                and rejection_report["summary"]["provider_failures"] == 0
            ),
        },
        "production_60": _complete_and_gated(
            production_report, suite="production", expected_n=60
        ),
    }
    checks["generation_85"]["passed"] = bool(
        checks["generation_85"]["actual_n"] == 85
    )
    passed = bool(
        checks["legacy_hashes"]
        and all(
            value.get("passed")
            for key, value in checks.items()
            if key != "legacy_hashes"
        )
    )
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "commit": _commit(),
        "artifact_fingerprint": release_artifact_fingerprint(ROOT),
        "provider": "live",
        "metric_policy": "separate_from_single_cohort_v2",
        "checks": checks,
        "passed": passed,
        "reports": {
            "deterministic": deterministic_report,
            "retrieval": retrieval_report,
            "generation": generation_report,
            "judge": judge_report,
            "general_rejection": rejection_report,
            "production": production_report,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"passed": passed, "checks": checks}, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
