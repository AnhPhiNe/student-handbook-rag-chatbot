"""Propose deterministic gold corrections without mutating the frozen bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.single_cohort_v2 import (  # noqa: E402
    BUNDLE_DIR,
    derive_cohort_source,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_proposal(bundle: Path = BUNDLE_DIR) -> dict[str, Any]:
    corrections: list[dict[str, Any]] = []
    files: dict[str, str] = {}
    for split in ("dev", "hidden"):
        path = bundle / f"{split}.json"
        files[path.name] = _sha(path)
        for case in _load(path):
            expected = case.get("expected") or {}
            current = str(expected.get("effective_cohort_source") or "")
            derived = derive_cohort_source(case)
            if current == derived:
                continue
            corrections.append(
                {
                    "split": split,
                    "case_id": case.get("id"),
                    "query": case.get("query"),
                    "selected_cohort": case.get("selected_cohort"),
                    "context_mode": expected.get("context_mode"),
                    "effective_cohort": expected.get("effective_cohort"),
                    "current_source": current,
                    "proposed_source": derived,
                    "reason": "cohort_authority_precedence",
                    "human_approved": False,
                }
            )
    return {
        "proposal_version": "single-cohort-gold-contract-correction-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_hashes": files,
        "rule": [
            "explicit cohort in raw query",
            "selected cohort",
            "grounded cohort in history",
            "otherwise unresolved",
        ],
        "correction_counts": {
            split: sum(item["split"] == split for item in corrections)
            for split in ("dev", "hidden")
        },
        "corrections": corrections,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, default=BUNDLE_DIR)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proposal = build_proposal(args.bundle)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(proposal, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(proposal["correction_counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
