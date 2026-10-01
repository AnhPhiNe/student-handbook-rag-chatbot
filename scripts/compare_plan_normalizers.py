"""Compare two `normalize_query_plan` versions on the same planner replies.

`normalize_query_plan` is a pure function of the planner's reply, so one planner
call per case feeds both versions: the comparison is paired and carries no
planner variance. Written for the follow-up patch (a single-task follow-up
retrieves with the standalone query) against the `official_v2` conversation
cases, which are development data, not the official_v4 hold-out.

    python -m scripts.compare_plan_normalizers --other ../student_handbook_rag_v4_frozen
"""
import argparse
import importlib
import json
import re
import subprocess
import sys
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data/eval/official_v2/generated_answer_cases.json"


@contextmanager
def _normalizer_at(revision: str):
    """Import another revision's query_plan as a sibling module, so its relative imports resolve.

    Only `normalize_query_plan` differs between the revisions compared here; the
    modules it imports are identical, so they come from this checkout.
    """
    source = subprocess.check_output(["git", "show", f"{revision}:src/retrieval/core/query_plan.py"],
                                     cwd=ROOT, text=True, encoding="utf-8")
    path = ROOT / "src/retrieval/core/_query_plan_other.py"
    path.write_text(source, encoding="utf-8")
    try:
        module = importlib.import_module("src.retrieval.core._query_plan_other")
        yield module.normalize_query_plan
    finally:
        sys.modules.pop("src.retrieval.core._query_plan_other", None)
        path.unlink(missing_ok=True)


def _fold(text: Any) -> str:
    folded = unicodedata.normalize("NFD", str(text or "").casefold().replace("đ", "d"))
    return " ".join(re.findall(r"\w+", "".join(c for c in folded if unicodedata.category(c) != "Mn")))


def _scope_terms(history: list[dict[str, str]]) -> list[str]:
    """Scoping phrases a follow-up must not drop, taken from what the student said."""

    said = _fold(" ".join(turn.get("content", "") for turn in history if turn.get("role") == "user"))
    candidates = ["vua lam vua hoc", "chinh quy", "lien thong", "cao dang", "k48", "k49", "k50", "k51",
                  "cap bang thu nhat", "trung cap", "sau dai hoc", "ngoai tru", "noi tru", "khuyet tat",
                  "dan toc thieu so", "su pham"]
    return [term for term in candidates if term in said]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--other", required=True, help="Revision to compare against, e.g. the pre-patch commit.")
    parser.add_argument("--out", type=Path, default=ROOT / "data/eval/reports/plan_normalizer_compare")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    from src.common.env_loader import load_project_env
    load_project_env()
    import src.retrieval.core.ai_router as ai_router
    from src.retrieval.core.query_plan import normalize_query_plan as patched

    captured: list[tuple[Any, dict[str, Any]]] = []
    real = ai_router.normalize_query_plan

    def spy(parsed: Any, **kwargs: Any):
        captured.append((parsed, kwargs))
        return real(parsed, **kwargs)

    ai_router.normalize_query_plan = spy
    router = ai_router.AIRouter.from_config()
    cases = [case for case in json.loads(CASES.read_text(encoding="utf-8")) if case.get("history")]
    cases = cases[: args.limit] if args.limit else cases

    rows = []
    with _normalizer_at(args.other) as frozen:
      for case in cases:
          captured.clear()
          error = None
          try:
              router.plan(case["query"], cohort=case.get("cohort"), chat_history=case["history"])
          except Exception as exc:  # noqa: BLE001 - recorded per case
              error = type(exc).__name__
          if error or not captured:
              rows.append({"id": case["id"], "error": error or "no_planner_payload"})
              continue
          parsed, kwargs = captured[0]
          plan_frozen, _ = frozen(parsed, **kwargs)
          plan_patched, _ = patched(parsed, **kwargs)
          wanted = _scope_terms(case["history"])

          def held(plan):
              tasks = (plan or {}).get("tasks") or []
              text = _fold(" ".join(str(task.get("question") or "") for task in tasks))
              return [term for term in wanted if term in text]

          rows.append({
              "id": case["id"], "query": case["query"],
              "context_mode": (parsed or {}).get("context_mode"),
              "standalone_query": (parsed or {}).get("standalone_query"),
              "tasks": len((plan_patched or {}).get("tasks") or []),
              "scope_terms": wanted,
              "frozen_kept": held(plan_frozen), "patched_kept": held(plan_patched),
              "frozen_questions": [t.get("question") for t in (plan_frozen or {}).get("tasks") or []],
              "patched_questions": [t.get("question") for t in (plan_patched or {}).get("tasks") or []],
          })

    scored = [r for r in rows if "error" not in r and r["scope_terms"]]
    gained = [r["id"] for r in scored if len(r["patched_kept"]) > len(r["frozen_kept"])]
    lost = [r["id"] for r in scored if len(r["patched_kept"]) < len(r["frozen_kept"])]
    changed = [r["id"] for r in rows if "error" not in r and r["frozen_questions"] != r["patched_questions"]]
    summary = {
        "cases": len(rows), "errors": sorted({r["error"] for r in rows if "error" in r}),
        "with_scope_terms": len(scored),
        "questions_changed_by_the_patch": len(changed),
        "scope_terms_gained": gained, "scope_terms_lost": lost,
        "frozen_scope_terms_kept": sum(len(r["frozen_kept"]) for r in scored),
        "patched_scope_terms_kept": sum(len(r["patched_kept"]) for r in scored),
        "scope_terms_wanted": sum(len(r["scope_terms"]) for r in scored),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "plan_normalizer_compare.json").write_text(
        json.dumps({"summary": summary, "cases": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
