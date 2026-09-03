from __future__ import annotations

# ruff: noqa: E402

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.common.console import configure_utf8_stdio
from src.ingestion.pdf_loader import HANDBOOK_HEADER_PATTERN


REQUIRED_ARTIFACTS = [
    ("constraints-runtime.txt", "file"),
    ("configs/ai_router.yaml", "file"),
    ("configs/answer_generation.yaml", "file"),
    ("configs/hcmue_slang_dictionary.yaml", "file"),
    ("configs/office_aliases.yaml", "file"),
    ("configs/structured_lookup_registry.yaml", "file"),
    ("data/processed/tables/scoring_tables.json", "file"),
    ("data/processed/tables/formula_rules.json", "file"),
    ("data/processed/tables/structured_tables_registry.json", "file"),
    ("data/processed/tables/foreign_language_equivalency_table.json", "file"),
    ("data/processed/directories/student_service_directory.json", "file"),
    ("data/processed/directories/student_office_profiles.json", "file"),
    ("data/processed/directories/student_faculty_profiles.json", "file"),
    ("data/processed/directories/program_directory.json", "file"),
    ("data/processed/graphs/document_edges.json", "file"),
    ("data/processed/amendments/amendments.json", "file"),
    ("data/processed/chunks/all_docstore_items.json", "file"),
    ("data/processed/chunks/child_parent_chunks.json", "file"),
    ("data/processed/metadata/build_manifest.json", "file"),
]

CONTENT_FIELDS = {"content", "document", "raw_text", "text"}
BUILD_MANIFEST_PATH = Path("data/processed/metadata/build_manifest.json")


def find_repeated_handbook_header(value: object) -> str | None:
    """Return a leaked PDF header found inside a content-bearing JSON field."""

    stack: list[tuple[str | None, object]] = [(None, value)]
    while stack:
        field, current = stack.pop()
        if isinstance(current, dict):
            stack.extend((str(key), item) for key, item in current.items())
        elif isinstance(current, list):
            stack.extend((field, item) for item in current)
        elif isinstance(current, str) and field in CONTENT_FIELDS:
            for line in current.splitlines():
                candidate = line.strip()
                if HANDBOOK_HEADER_PATTERN.fullmatch(candidate):
                    return candidate
    return None


def validate_artifact(path: Path, kind: str) -> str | None:
    if kind == "dir":
        if not path.is_dir():
            return "missing directory"
        if not any(path.iterdir()):
            return "empty directory"
        return None

    if not path.is_file():
        return "missing file"
    if path.stat().st_size == 0:
        return "empty file"
    if path.suffix.lower() == ".json":
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return f"invalid JSON: {exc}"
        if parsed == [] or parsed == {}:
            return "JSON artifact must not be [] or {}"
        leaked_header = find_repeated_handbook_header(parsed)
        if leaked_header:
            return f"repeated PDF header leaked into content: {leaked_header}"
    return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_build_manifest(path: Path = BUILD_MANIFEST_PATH) -> list[str]:
    """Return artifact identity mismatches declared by a build manifest."""

    if not path.is_file():
        return [f"missing build manifest: {path}"]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid build manifest JSON: {exc}"]

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        return ["build manifest does not declare artifacts"]

    errors: list[str] = []
    for name, record in artifacts.items():
        if not isinstance(record, dict):
            errors.append(f"{name}: artifact record is not an object")
            continue
        raw_path = str(record.get("path") or "").strip()
        if not raw_path:
            errors.append(f"{name}: missing path")
            continue
        artifact_path = Path(raw_path.replace("\\", "/"))
        if not artifact_path.is_file():
            errors.append(f"{name}: missing artifact {artifact_path}")
            continue

        expected_sha = str(record.get("sha256") or "").strip().lower()
        actual_sha = _sha256_file(artifact_path)
        if not expected_sha:
            errors.append(f"{name}: missing sha256")
        elif expected_sha != actual_sha:
            errors.append(
                f"{name}: sha256 mismatch "
                f"(manifest={expected_sha}, actual={actual_sha})"
            )

        expected_count = record.get("count")
        if expected_count is None or artifact_path.suffix.lower() != ".json":
            continue
        try:
            value = json.loads(artifact_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(value, list) and int(expected_count) != len(value):
            errors.append(
                f"{name}: count mismatch "
                f"(manifest={expected_count}, actual={len(value)})"
            )
    return errors


def main() -> None:
    configure_utf8_stdio()

    parser = argparse.ArgumentParser(description="Check deploy-time local artifacts.")
    parser.add_argument("--warn-only", action="store_true", help="Print missing artifacts without failing.")
    args = parser.parse_args()

    failures: list[tuple[str, str]] = []
    for raw_path, kind in REQUIRED_ARTIFACTS:
        path = Path(raw_path)
        error = validate_artifact(path, kind)
        status = "OK" if error is None else ("WARN" if args.warn_only else "FAIL")
        print(f"{status}: {raw_path}" + (f" ({error})" if error else ""))
        if error is not None:
            failures.append((raw_path, error))

    for error in validate_build_manifest():
        status = "WARN" if args.warn_only else "FAIL"
        print(f"{status}: build_manifest ({error})")
        failures.append(("build_manifest", error))

    if failures and args.warn_only:
        print(
            "\nArtifact audit completed in warn-only mode. "
            "This is expected in GitHub CI when deploy-time data/processed artifacts are not committed."
        )

    if failures and not args.warn_only:
        print("\nInvalid deploy artifacts:")
        for item, error in failures:
            print(f"- {item}: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
