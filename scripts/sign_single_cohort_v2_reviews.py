"""Convert reviewed AI proposals into human-signed review inputs.

This command is intentionally fail-closed: it requires an explicit commit,
accepts only proposals with no rejected request, and records the human reviewer
and approval basis. The resulting files can be consumed by the gold audit
application command.
"""

from __future__ import annotations

import argparse
import json
import subprocess
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


def _head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _signed_rows(
    rows: list[dict[str, Any]],
    *,
    reviewer: str,
    reviewed_at: str,
    commit: str,
) -> list[dict[str, Any]]:
    signed: list[dict[str, Any]] = []
    for source_row in rows:
        if source_row.get("decision") != "ai_recommended_approved":
            raise ValueError(f"Case was not recommended: {source_row.get('case_id')}")
        row = json.loads(json.dumps(source_row, ensure_ascii=False))
        for request in row.get("request_reviews") or []:
            if request.get("decision") != "ai_recommended_approved":
                raise ValueError(
                    "Request was not recommended: "
                    f"{row.get('case_id')}/{request.get('request_id')}"
                )
            request["decision"] = "approved"
        row.update(
            {
                "decision": "approved",
                "reviewer": reviewer,
                "reviewed_at": reviewed_at,
                "approval_commit": commit,
                "approval_basis": "project owner confirmed both review proposals",
            }
        )
        signed.append(row)
    return signed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmed-commit", required=True)
    parser.add_argument("--reviewer", required=True)
    args = parser.parse_args()

    head = _head()
    if not head.startswith(args.confirmed_commit) or len(args.confirmed_commit) < 8:
        raise SystemExit(
            f"Confirmed commit {args.confirmed_commit!r} does not match HEAD {head}"
        )
    report = _load(BUNDLE / "ai_review_report.json")
    if report.get("exceptions") or report.get("decision_counts") != {
        "ai_recommended_approved": 135
    }:
        raise SystemExit("AI evidence audit is incomplete or has exceptions")

    reviewed_at = datetime.now(UTC).isoformat()
    for split in ("dev", "hidden"):
        rows = _load(BUNDLE / f"{split}_review_proposal.json")
        signed = _signed_rows(
            rows,
            reviewer=args.reviewer,
            reviewed_at=reviewed_at,
            commit=head,
        )
        _write(BUNDLE / f"{split}_review_signed.json", signed)
    print(
        json.dumps(
            {
                "commit": head,
                "reviewer": args.reviewer,
                "reviewed_at": reviewed_at,
                "dev": 75,
                "hidden": 60,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
