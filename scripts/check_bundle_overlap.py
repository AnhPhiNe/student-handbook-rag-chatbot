"""Screen a held-out bundle's questions for near-duplicates of an earlier bundle.

Compares every authored query in the bundle (deterministic and retrieval-only authoring)
with every query in the reference bundle's four case files, after folding case and Vietnamese diacritics, and
lists pairs whose token-sequence similarity reaches the threshold. A low score does not
prove independence: short table questions ("GPA 2,9 là loại gì?") differ only in values.

    python -m scripts.check_bundle_overlap --bundle official_v2 --reference official_v1
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.text import fold_text  # noqa: E402

CASE_FILES = ("deterministic_tool_cases.json", "generated_answer_cases.json",
              "retrieval_cases.json", "production_cases.json")
AUTHORING_FILES = ("deterministic_authoring.yaml", "retrieval_authoring.yaml")


def tokens(text: str) -> list[str]:
    return fold_text(text).split()


def reference_queries(bundle: Path) -> list[tuple[str, str]]:
    queries = []
    for name in CASE_FILES:
        path = bundle / name
        if path.exists():
            queries += [(name, case.get("query") or "") for case in json.loads(path.read_text(encoding="utf-8"))]
    return queries


def closest(query: str, references: list[tuple[str, str]]) -> tuple[float, str, str]:
    words = tokens(query)
    return max((difflib.SequenceMatcher(None, words, tokens(ref)).ratio(), source, ref)
               for source, ref in references)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bundle", default="official_v2")
    parser.add_argument("--reference", default="official_v1")
    parser.add_argument("--threshold", type=float, default=0.7)
    args = parser.parse_args()

    bundle = ROOT / "data/eval" / args.bundle
    queries = []
    for name in AUTHORING_FILES:
        if (bundle / name).exists():
            queries += [case["query"] for case in yaml.safe_load((bundle / name).read_text(encoding="utf-8"))["cases"]]
    references = reference_queries(ROOT / "data/eval" / args.reference)
    flagged = []
    for query in queries:
        score, source, ref = closest(query, references)
        if score >= args.threshold:
            flagged.append((score, query, source, ref))
    for score, query, source, ref in sorted(flagged, reverse=True):
        print(f"{score:.2f}  {query}\n      ~ [{source}] {ref}")
    print(f"{len(flagged)} of {len(queries)} questions at or above {args.threshold} "
          f"against {len(references)} {args.reference} queries.")


if __name__ == "__main__":
    main()
