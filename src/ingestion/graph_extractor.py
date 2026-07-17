import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_INPUT_FILE = "data/processed/chunks/all_docstore_items.json"
DEFAULT_OUTPUT_FILE = "data/processed/graphs/document_edges.json"
DEFAULT_REPORT_FILE = "data/processed/graphs/document_edges_report.json"
RELATION = "LIEN_QUAN_TOI"

ARTICLE_PATTERN = re.compile(r"(?:Điều|Dieu)\s+(\d+)", re.IGNORECASE)
CLAUSE_PATTERN = re.compile(r"(?:khoản|khoan)\s+(\d+[a-zA-Z]?)", re.IGNORECASE)
POINT_PATTERN = re.compile(r"(?:điểm|diem)\s+([a-zA-ZđĐ])", re.IGNORECASE)
WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class SectionRecord:
    section_id: str
    cohort: str
    document_id: str
    document_key: str
    document_title: str
    article_number: int


@dataclass(frozen=True)
class Reference:
    article_number: int
    reference_text: str
    reason: str
    clause: str | None = None
    point: str | None = None


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _cohort(item: dict[str, Any]) -> str:
    metadata = _metadata(item)
    return str(item.get("cohort") or metadata.get("cohort") or "")


def _document_id(item: dict[str, Any]) -> str:
    metadata = _metadata(item)
    return str(item.get("document_id") or metadata.get("document_id") or "")


def _document_title(item: dict[str, Any]) -> str:
    return str(_metadata(item).get("document_title") or "")


def _document_key(item: dict[str, Any]) -> str:
    # document_id is the whole handbook in current data. document_title is the
    # finer regulation/procedure boundary, so it prevents Điều N collisions.
    return _document_title(item) or _document_id(item)


def _article_number_from_text(text: str) -> int | None:
    match = ARTICLE_PATTERN.search(text or "")
    if not match:
        return None
    return int(match.group(1))


def article_number_for_item(item: dict[str, Any]) -> int | None:
    metadata = _metadata(item)
    article_number = _article_number_from_text(str(metadata.get("article") or ""))
    if article_number is not None:
        return article_number

    section_id = str(item.get("_id") or "")
    match = re.search(r"_Dieu(\d+)(?:_|$)", section_id)
    if match:
        return int(match.group(1))

    return _article_number_from_text(str(item.get("content") or ""))


def _clean_text(text: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", text or "").strip()


def _reason_for_match(text: str, start: int, end: int) -> str:
    left_candidates = [text.rfind(mark, 0, start) for mark in (".", ";", "\n")]
    left = max(left_candidates)
    left = 0 if left == -1 else left + 1

    right_candidates = [text.find(mark, end) for mark in (".", ";", "\n")]
    right_candidates = [idx for idx in right_candidates if idx != -1]
    right = min(right_candidates) if right_candidates else len(text)

    reason = _clean_text(text[left:right])
    if len(reason) > 280:
        reason = reason[:277].rstrip() + "..."
    return reason


def _nearest_match(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    matches = list(pattern.finditer(text))
    return matches[-1] if matches else None


def _reference_for_article_match(text: str, match: re.Match[str]) -> Reference:
    prefix_start = max(0, match.start() - 80)
    prefix = text[prefix_start : match.start()]
    clause_match = _nearest_match(CLAUSE_PATTERN, prefix)
    point_match = _nearest_match(POINT_PATTERN, prefix)

    reference_start = match.start()
    clause = None
    point = None
    if clause_match:
        clause = clause_match.group(1)
        reference_start = min(reference_start, prefix_start + clause_match.start())
    if point_match:
        point = point_match.group(1).lower()
        reference_start = min(reference_start, prefix_start + point_match.start())

    reference_text = _clean_text(text[reference_start : match.end()])
    reason = _reason_for_match(text, match.start(), match.end())
    return Reference(
        article_number=int(match.group(1)),
        reference_text=reference_text,
        reason=reason,
        clause=clause,
        point=point,
    )


def extract_references(content: str) -> list[Reference]:
    return [_reference_for_article_match(content, match) for match in ARTICLE_PATTERN.finditer(content or "")]


def build_section_index(
    docstore_items: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str, int], list[SectionRecord]], set[str], list[dict[str, Any]]]:
    index: dict[tuple[str, str, int], list[SectionRecord]] = defaultdict(list)
    parent_ids: set[str] = set()
    skipped: list[dict[str, Any]] = []

    for item in docstore_items:
        section_id = str(item.get("_id") or "")
        if not section_id:
            skipped.append({"issue": "missing_section_id"})
            continue
        parent_ids.add(section_id)

        cohort = _cohort(item)
        document_id = _document_id(item)
        document_key = _document_key(item)
        article_number = article_number_for_item(item)
        if not cohort or not document_key or article_number is None:
            skipped.append(
                {
                    "issue": "missing_index_fields",
                    "section_id": section_id,
                    "cohort": cohort,
                    "document_id": document_id,
                    "document_key": document_key,
                    "article_number": article_number,
                }
            )
            continue

        index[(cohort, document_key, article_number)].append(
            SectionRecord(
                section_id=section_id,
                cohort=cohort,
                document_id=document_id,
                document_key=document_key,
                document_title=_document_title(item),
                article_number=article_number,
            )
        )

    return index, parent_ids, skipped


def _resolve_target(
    index: dict[tuple[str, str, int], list[SectionRecord]],
    source: SectionRecord,
    reference: Reference,
) -> tuple[SectionRecord | None, str | None]:
    candidates = index.get((source.cohort, source.document_key, reference.article_number), [])
    if not candidates:
        return None, "unresolved_target"
    if len(candidates) > 1:
        return None, "ambiguous_target"
    return candidates[0], None


def _edge_from_reference(source: SectionRecord, target: SectionRecord, reference: Reference) -> dict[str, Any]:
    return {
        "source": source.section_id,
        "target": target.section_id,
        "relation": RELATION,
        "reason": reference.reason,
        "method": "rule",
        "confidence": 1.0,
        "cohort": source.cohort,
        "document_id": source.document_id,
        "document_title": source.document_title,
        "reference_text": reference.reference_text,
        "reference_article": reference.article_number,
        "reference_clause": reference.clause,
        "reference_point": reference.point,
    }


def extract_rule_edges(docstore_items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    index, parent_ids, index_skips = build_section_index(docstore_items)
    source_by_id = {record.section_id: record for records in index.values() for record in records}
    edges_by_key: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    skipped: list[dict[str, Any]] = list(index_skips)

    for item in docstore_items:
        source_id = str(item.get("_id") or "")
        source = source_by_id.get(source_id)
        if not source:
            continue

        for reference in extract_references(str(item.get("content") or "")):
            target, issue = _resolve_target(index, source, reference)
            if issue:
                skipped.append(
                    {
                        "issue": issue,
                        "source": source_id,
                        "cohort": source.cohort,
                        "document_id": source.document_id,
                        "document_title": source.document_title,
                        "reference_article": reference.article_number,
                        "reference_text": reference.reference_text,
                    }
                )
                continue
            if not target or target.section_id == source.section_id:
                skipped.append(
                    {
                        "issue": "self_reference",
                        "source": source_id,
                        "reference_article": reference.article_number,
                        "reference_text": reference.reference_text,
                    }
                )
                continue

            key = (source.cohort, source.document_id, source.section_id, target.section_id, RELATION)
            if key in edges_by_key:
                skipped.append(
                    {
                        "issue": "duplicate_edge",
                        "source": source.section_id,
                        "target": target.section_id,
                        "reference_text": reference.reference_text,
                    }
                )
                continue
            edges_by_key[key] = _edge_from_reference(source, target, reference)

    edges = sorted(edges_by_key.values(), key=lambda edge: (edge["cohort"], edge["source"], edge["target"]))
    validation = validate_edges(edges, parent_ids)
    report = {
        "status": "ok" if not validation["missing_nodes"] else "invalid",
        "total_docstore_items": len(docstore_items),
        "total_edges": len(edges),
        "total_skipped": len(skipped),
        "skip_counts": dict(Counter(item["issue"] for item in skipped)),
        "coverage": _coverage_by_cohort(edges, docstore_items),
        "validation": validation,
        "skipped": skipped,
    }
    return edges, report


def _coverage_by_cohort(edges: list[dict[str, Any]], docstore_items: list[dict[str, Any]]) -> dict[str, Any]:
    parent_ids_by_cohort: dict[str, set[str]] = defaultdict(set)
    for item in docstore_items:
        section_id = str(item.get("_id") or "")
        cohort = _cohort(item)
        if section_id and cohort:
            parent_ids_by_cohort[cohort].add(section_id)

    graph_nodes_by_cohort: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        cohort = str(edge.get("cohort") or "")
        graph_nodes_by_cohort[cohort].add(str(edge.get("source")))
        graph_nodes_by_cohort[cohort].add(str(edge.get("target")))

    coverage = {}
    for cohort, parent_ids in sorted(parent_ids_by_cohort.items()):
        graph_nodes = graph_nodes_by_cohort.get(cohort, set())
        coverage[cohort] = {
            "parent_sections": len(parent_ids),
            "graph_nodes": len(graph_nodes),
            "coverage_pct": round((len(graph_nodes) / len(parent_ids)) * 100, 2) if parent_ids else 0.0,
        }
    return coverage


def validate_edges(edges: list[dict[str, Any]], parent_ids: set[str]) -> dict[str, Any]:
    missing_nodes = sorted(
        {
            str(node_id)
            for edge in edges
            for node_id in (edge.get("source"), edge.get("target"))
            if node_id not in parent_ids
        }
    )
    cross_cohort_edges = [
        edge
        for edge in edges
        if str(edge.get("source", "")).split("_", 1)[0] != str(edge.get("target", "")).split("_", 1)[0]
    ]
    return {
        "missing_nodes": missing_nodes,
        "graph_nodes_missing_in_docstore": len(missing_nodes),
        "cross_cohort_edges": len(cross_cohort_edges),
    }


def load_json(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array in {path}")
    return data


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build directed document graph edges with rule-based extraction.")
    parser.add_argument("--input-file", default=DEFAULT_INPUT_FILE)
    parser.add_argument("--output-file", default=DEFAULT_OUTPUT_FILE)
    parser.add_argument("--report-file", default=DEFAULT_REPORT_FILE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args(argv)
    input_path = Path(args.input_file)
    output_path = Path(args.output_file)
    report_path = Path(args.report_file)

    if not input_path.exists():
        raise FileNotFoundError(f"Không tìm thấy docstore file: {input_path}")

    docstore_items = load_json(input_path)
    edges, report = extract_rule_edges(docstore_items)
    if report["validation"]["graph_nodes_missing_in_docstore"]:
        write_json(report_path, report)
        raise RuntimeError("Graph validation failed: some edge nodes are missing from docstore.")

    write_json(output_path, edges)
    write_json(report_path, report)

    print(f"Loaded docstore items: {len(docstore_items)}")
    print(f"Extracted rule edges: {len(edges)}")
    print(f"Skipped references: {report['total_skipped']}")
    print(f"Graph nodes missing in docstore: {report['validation']['graph_nodes_missing_in_docstore']}")
    print(f"Wrote graph edges to: {output_path}")
    print(f"Wrote extraction report to: {report_path}")


if __name__ == "__main__":
    main()
