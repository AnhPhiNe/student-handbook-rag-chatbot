from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.env_loader import load_project_env
from src.retrieval.core.ai_router import AIRouter, ROUTER_PROMPT_VERSION
from src.retrieval.core.slang_normalizer import SlangNormalizer


DEFAULT_DATASET = Path("data/eval/router_semantic_v2_cases.json")
DEFAULT_OUTPUT = Path("data/eval/router_semantic_v2_results.json")
EVALUATOR_VERSION = "single-cohort-v2-1"
COMPLETED_OUTCOMES = {"passed", "semantic_failure", "validation_failure"}
PROVIDER_FALLBACKS = {"capacity", "router_error_to_clarify"}


def _normalize(value: Any) -> str:
    text = str(value or "").lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = re.sub(r"[^a-z0-9+.,]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _matches_expected_request(
    actual: dict[str, Any],
    expected: dict[str, Any],
    *,
    normalizer: SlangNormalizer,
) -> list[str]:
    errors = []
    for field in ("request_kind", "lookup_type", "intent"):
        if field in expected and actual.get(field) != expected.get(field):
            errors.append(
                f"{field}: expected={expected.get(field)!r} actual={actual.get(field)!r}"
            )

    normalized_span = _normalize(actual.get("query_span"))
    for value in expected.get("span_contains") or []:
        expected_forms = {
            _normalize(value),
            _normalize(normalizer.replace_for_router(str(value))),
        }
        cohort_forms = {_normalize(item) for item in actual.get("cohort_refs") or []}
        if not any(
            form and (form in normalized_span or form in cohort_forms)
            for form in expected_forms
        ):
            errors.append(f"query_span missing {value!r}")

    actual_slots = actual.get("slots") or {}
    for slot_name, value in (expected.get("slots") or {}).items():
        actual_value = actual_slots.get(slot_name)
        if not _values_equivalent(actual_value, value):
            errors.append(
                f"slot {slot_name}: expected={value!r} actual={actual_value!r}"
            )

    expected_cohorts = expected.get("cohort_refs")
    if expected_cohorts is not None and actual.get("cohort_refs") != expected_cohorts:
        errors.append(
            f"cohort_refs: expected={expected_cohorts!r} actual={actual.get('cohort_refs')!r}"
        )
    return errors


def _values_equivalent(actual: Any, expected: Any) -> bool:
    if actual == expected:
        return True
    try:
        return float(actual) == float(expected)
    except (TypeError, ValueError):
        return _normalize(actual) == _normalize(expected)


def _assess_decision(
    case: dict[str, Any],
    *,
    router_query: str,
    decision: dict[str, Any],
    normalizer: SlangNormalizer,
) -> dict[str, Any]:
    errors = []
    expected_outcome = case.get("expected_outcome") or (
        "clarify" if str(case.get("category") or "").startswith("multi_cohort") else "execute"
    )
    validation_errors = decision.get("router_validation_errors") or []
    if validation_errors:
        errors.append(f"router_validation_errors={validation_errors!r}")
    fallback = decision.get("router_fallback")
    if fallback:
        errors.append(f"router_fallback={fallback}")

    actual_outcome = decision.get("outcome") or (
        "execute" if decision.get("route") in {"structured", "rag"} else decision.get("route")
    )
    if actual_outcome != expected_outcome:
        errors.append(
            f"outcome: expected={expected_outcome!r} actual={actual_outcome!r}"
        )
    actual_requests = decision.get("lookup_requests") or []
    if expected_outcome != "execute":
        if actual_requests:
            errors.append("non_execute_outcome_has_requests")
        expected_requests = []
    else:
        expected_requests = case.get("expected_requests") or []
    if len(actual_requests) != len(expected_requests):
        errors.append(
            f"request_count: expected={len(expected_requests)} actual={len(actual_requests)}"
        )
    for index, expected in enumerate(expected_requests):
        if index >= len(actual_requests):
            break
        request_errors = _matches_expected_request(
            actual_requests[index],
            expected,
            normalizer=normalizer,
        )
        errors.extend(f"request:{index}:{error}" for error in request_errors)

    if fallback in PROVIDER_FALLBACKS:
        outcome = "provider_failure"
    elif validation_errors or fallback:
        outcome = "validation_failure"
    elif errors:
        outcome = "semantic_failure"
    else:
        outcome = "passed"

    return {
        "id": case.get("id"),
        "category": case.get("category"),
        "query": case.get("query"),
        "router_query": router_query,
        "evaluator_version": EVALUATOR_VERSION,
        "router_prompt_version": ROUTER_PROMPT_VERSION,
        "outcome": outcome,
        "passed": outcome == "passed",
        "errors": errors,
        "decision": decision,
    }


def _evaluate_case(
    router: AIRouter,
    normalizer: SlangNormalizer,
    case: dict[str, Any],
) -> dict[str, Any]:
    # The planner must receive immutable user text. Slang/alias expansion belongs
    # to typed request execution, not to router grounding.
    router_query = str(case["query"])
    try:
        decision = router.route(
            router_query,
            cohort=case.get("cohort"),
            chat_history=case.get("chat_history") or [],
        )
    except Exception as exc:
        return {
            "id": case.get("id"),
            "category": case.get("category"),
            "query": case.get("query"),
            "router_query": router_query,
            "evaluator_version": EVALUATOR_VERSION,
            "router_prompt_version": ROUTER_PROMPT_VERSION,
            "outcome": "provider_failure",
            "passed": False,
            "errors": [f"router_exception={type(exc).__name__}: {exc}"],
            "decision": None,
        }
    return _assess_decision(
        case,
        router_query=router_query,
        decision=decision,
        normalizer=normalizer,
    )


def _retry_after_seconds(result: dict[str, Any], attempt: int) -> float:
    decision = result.get("decision") or {}
    retry_after = decision.get("router_retry_after_seconds")
    if retry_after is not None:
        return max(0.0, float(retry_after))
    return min(30.0, float(2 ** max(0, attempt - 1)))


def _evaluate_case_with_retries(
    router: AIRouter,
    normalizer: SlangNormalizer,
    case: dict[str, Any],
    *,
    max_attempts: int,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    last_result: dict[str, Any] | None = None
    for attempt in range(1, max(1, max_attempts) + 1):
        last_result = _evaluate_case(router, normalizer, case)
        last_result["evaluation_attempts"] = attempt
        if last_result["outcome"] != "provider_failure":
            return last_result
        if attempt < max_attempts:
            sleep_fn(_retry_after_seconds(last_result, attempt))
    assert last_result is not None
    return last_result


def _build_summary(
    cases: list[dict[str, Any]],
    results_by_id: dict[str, dict[str, Any]],
    *,
    run_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    results = [
        results_by_id[str(case.get("id"))]
        for case in cases
        if str(case.get("id")) in results_by_id
    ]
    counts = {
        outcome: sum(1 for result in results if result.get("outcome") == outcome)
        for outcome in (
            "passed",
            "semantic_failure",
            "validation_failure",
            "provider_failure",
        )
    }
    completed = sum(counts[outcome] for outcome in COMPLETED_OUTCOMES)
    return {
        "total": len(cases),
        "evaluated": len(results),
        "completed": completed,
        "passed": counts["passed"],
        "semantic_failed": counts["semantic_failure"],
        "validation_failed": counts["validation_failure"],
        "provider_failed": counts["provider_failure"],
        "failed": len(results) - counts["passed"],
        "pass_rate": counts["passed"] / completed if completed else 0.0,
        "run_metadata": run_metadata or {},
        "results": results,
    }


def _write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _load_resume_results(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(result.get("id")): result
        for result in payload.get("results") or []
        if result.get("id") is not None
    }


def run_evaluation(
    router: AIRouter,
    normalizer: SlangNormalizer,
    cases: list[dict[str, Any]],
    *,
    output_path: Path,
    resume: bool,
    max_attempts: int,
    inter_case_delay: float = 0.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    run_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prior_results = _load_resume_results(output_path) if resume else {}
    results_by_id: dict[str, dict[str, Any]] = {}
    for case in cases:
        case_id = str(case.get("id"))
        result = prior_results.get(case_id)
        if not result or result.get("outcome") not in COMPLETED_OUTCOMES:
            continue
        decision = result.get("decision")
        if isinstance(decision, dict) and result.get("router_prompt_version") != ROUTER_PROMPT_VERSION:
            continue
        if result.get("evaluator_version") != EVALUATOR_VERSION and isinstance(
            decision, dict
        ):
            router_query = str(case["query"])
            result = _assess_decision(
                case,
                router_query=router_query,
                decision=decision,
                normalizer=normalizer,
            )
        results_by_id[case_id] = result
    pending_cases = [
        case for case in cases if str(case.get("id")) not in results_by_id
    ]
    for index, case in enumerate(pending_cases):
        result = _evaluate_case_with_retries(
            router,
            normalizer,
            case,
            max_attempts=max_attempts,
            sleep_fn=sleep_fn,
        )
        results_by_id[str(case.get("id"))] = result
        _write_summary(
            output_path,
            _build_summary(cases, results_by_id, run_metadata=run_metadata),
        )
        if inter_case_delay > 0 and index < len(pending_cases) - 1:
            sleep_fn(inter_case_delay)
    summary = _build_summary(cases, results_by_id, run_metadata=run_metadata)
    _write_summary(output_path, summary)
    return summary


def _file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _run_metadata(dataset_path: Path, router: AIRouter) -> dict[str, Any]:
    config_paths = (
        ROOT / "configs" / "ai_router.yaml",
        ROOT / "configs" / "structured_lookup_registry.yaml",
    )
    return {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_sha": _git_sha(),
        "model": router.model_name,
        "router_prompt_version": ROUTER_PROMPT_VERSION,
        "dataset_path": str(dataset_path),
        "dataset_sha256": _file_sha256(dataset_path),
        "config_sha256": {
            str(path.relative_to(ROOT)): _file_sha256(path)
            for path in config_paths
            if path.exists()
        },
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="Live semantic-request evaluation for the AI Router."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=6)
    parser.add_argument("--inter-case-delay", type=float, default=0.0)
    parser.add_argument(
        "--minimum-cases",
        type=int,
        default=0,
        help="Fail fast when the dataset is smaller than the required release suite.",
    )
    args = parser.parse_args()

    load_project_env()
    cases = json.loads(args.dataset.read_text(encoding="utf-8"))
    if len(cases) < max(0, args.minimum_cases):
        print(
            f"Dataset has {len(cases)} cases; requires at least {args.minimum_cases}.",
            file=sys.stderr,
        )
        return 2
    if args.limit is not None:
        cases = cases[: max(0, args.limit)]

    router = AIRouter.from_config()
    normalizer = SlangNormalizer()
    summary = run_evaluation(
        router,
        normalizer,
        cases,
        output_path=args.output,
        resume=args.resume,
        max_attempts=args.max_attempts,
        inter_case_delay=max(0.0, args.inter_case_delay),
        run_metadata=_run_metadata(args.dataset, router),
    )
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "total",
                    "completed",
                    "passed",
                    "semantic_failed",
                    "validation_failed",
                    "provider_failed",
                    "pass_rate",
                )
            },
            ensure_ascii=False,
        )
    )
    for result in summary["results"]:
        if not result["passed"]:
            print(
                f"{result['outcome'].upper()} {result['id']}: "
                f"{'; '.join(result['errors'])}"
            )
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
