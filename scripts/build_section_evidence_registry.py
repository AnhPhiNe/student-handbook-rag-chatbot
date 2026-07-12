from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.generation.evidence_selection import build_section_evidence_registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build section-level evidence blocks for retrieved regulation sources."
    )
    parser.add_argument(
        "--docstore",
        default="data/processed/chunks/all_docstore_items.json",
        help="Path to all_docstore_items.json.",
    )
    parser.add_argument(
        "--output",
        default="data/processed/metadata/section_evidence_registry.json",
        help="Output registry path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry = build_section_evidence_registry(
        docstore_path=Path(args.docstore),
        output_path=Path(args.output),
    )
    print(
        "Built section evidence registry: "
        f"{registry.get('section_count', 0)} sections, "
        f"{registry.get('block_count', 0)} blocks -> {args.output}"
    )


if __name__ == "__main__":
    main()
