from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.common.console import configure_utf8_stdio


REQUIRED_ARTIFACTS = [
    ("configs/answer_generation.yaml", "file"),
    ("data/processed/tables/scoring_tables.json", "file"),
    ("data/processed/tables/formula_rules.json", "file"),
    ("data/processed/entities/entity_registry.json", "file"),
    ("data/processed/entities/query_expansion_rules.json", "file"),
    ("data/vectorstore/chroma", "dir"),
]


def exists(path: Path, kind: str) -> bool:
    return path.is_dir() if kind == "dir" else path.is_file()


def main() -> None:
    configure_utf8_stdio()

    parser = argparse.ArgumentParser(description="Check deploy-time local artifacts.")
    parser.add_argument("--warn-only", action="store_true", help="Print missing artifacts without failing.")
    args = parser.parse_args()

    missing: list[str] = []
    for raw_path, kind in REQUIRED_ARTIFACTS:
        path = Path(raw_path)
        ok = exists(path, kind)
        status = "OK" if ok else "MISSING"
        print(f"{status}: {raw_path}")
        if not ok:
            missing.append(raw_path)

    if missing and not args.warn_only:
        print("\nMissing deploy artifacts:")
        for item in missing:
            print(f"- {item}")
        sys.exit(1)


if __name__ == "__main__":
    main()
