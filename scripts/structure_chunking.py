"""Structure-aware hierarchical contextual chunking of handbook articles.

A search chunk is one khoản (numbered clause) with all of its points: the unit a
handbook rule is written in. The earlier builder (build_child_parent_index.py)
made one chunk per line marker, so a lettered point lost the sentence saying what
it is a condition of ("2. Sinh viên bị buộc thôi học trong các trường hợp sau:" in
one chunk, "a) Bị cảnh báo học tập 03 lần liên tiếp" in another). Parents are not
changed; retrieval still returns the whole article (small-to-big).

Markers differ between handbooks (K48-K49 Điều 5 uses "−" where K50 numbers its
clauses), so levels are read from the order markers appear in each article, not
from a fixed list: the first marker type in an article is the clause level and
the first other type inside a clause is the point level; deeper markers, table
rows and wrapped lines stay with the point above them.

Out-of-scope articles, clauses and points (configs/corpus_scope.yaml) get no chunk.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_child_parent_index import (  # noqa: E402
    INDEXABLE_CONTENT_TYPES,
    _base_metadata,
    _chunk_type_for_content_type,
    _clean_block_text,
    _looks_like_section_heading,
    _make_heading_chunk,
    _split_long_text,
    _strip_docstore_preamble,
    match_structured_table_block,
)

CONFIG_PATH = Path("configs/structure_chunking.yaml")
SCOPE_PATH = Path("configs/corpus_scope.yaml")
HEADER_MODES = ("article", "document_article", "document_chapter_article")
UNIT_MODES = ("clause", "point")

_MARKERS = (
    ("number", re.compile(r"^(\d{1,2})\.\s+(?=\S)")),
    ("roman", re.compile(r"^([IVX]{1,4})\.\s+(?=\S)")),
    ("letter", re.compile(r"^([a-zđ])\)\s*", re.IGNORECASE)),
    ("bullet", re.compile(r"^([-−–•+*])\s*")),
)


@dataclass
class Segment:
    """One marked line and the wrapped lines that continue it."""

    kind: str  # number | roman | letter | bullet:<char> | table | text
    marker: str | None
    lines: list[str]

    @property
    def text(self) -> str:
        if self.kind == "table":
            return "\n".join(self.lines)
        return " ".join(self.lines)


@dataclass
class Item:
    marker: str | None
    parts: list[Segment]

    @property
    def text(self) -> str:
        return "\n".join(part.text for part in self.parts)


@dataclass
class Unit:
    """A clause: its lead-in segment and the points under it."""

    marker: str | None
    lead: list[Segment]
    items: list[Item] = field(default_factory=list)

    @property
    def lead_text(self) -> str:
        return "\n".join(part.text for part in self.lead)

    def text(self, items: list[Item] | None = None) -> str:
        chosen = self.items if items is None else items
        return "\n".join(x for x in [self.lead_text, *(i.text for i in chosen)] if x)


def _segment_kind(line: str) -> tuple[str, str | None]:
    if line.startswith("|"):
        return "table", None
    for kind, pattern in _MARKERS:
        match = pattern.match(line)
        if match:
            marker = match.group(1)
            return (f"bullet:{marker}" if kind == "bullet" else kind), marker.lower()
    return "text", None


def split_segments(body: str) -> list[Segment]:
    segments: list[Segment] = []
    for raw in body.splitlines():
        line = _clean_block_text(raw)
        if not line:
            continue
        kind, marker = _segment_kind(line)
        if kind == "text" and segments and segments[-1].kind != "table":
            segments[-1].lines.append(line)  # a line wrapped by the PDF layout
        elif kind == "table" and segments and segments[-1].kind == "table":
            segments[-1].lines.append(line)
        else:
            segments.append(Segment(kind, marker, [line]))
    return segments


def build_units(segments: list[Segment]) -> list[Unit]:
    marked = [s.kind for s in segments if s.kind not in {"text", "table"}]
    top = marked[0] if marked else None
    units: list[Unit] = []
    current: Unit | None = None
    item_kind: str | None = None
    for segment in segments:
        if top is not None and segment.kind == top:
            current = Unit(segment.marker, [segment])
            units.append(current)
            item_kind = None
            continue
        if current is None:  # article text before the first clause
            current = Unit(None, [segment])
            units.append(current)
            continue
        if segment.kind not in {"text", "table"} and (item_kind is None or segment.kind == item_kind):
            item_kind = segment.kind
            current.items.append(Item(segment.marker, [segment]))
        elif current.items:
            current.items[-1].parts.append(segment)
        else:
            current.lead.append(segment)
    return units


def article_units(parent: dict[str, Any]) -> list[Unit]:
    metadata = parent.get("metadata") or {}
    body = _strip_docstore_preamble(str(parent.get("content") or ""))
    lines = body.splitlines()
    first = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first is not None and _looks_like_section_heading(_clean_block_text(lines[first]), metadata):
        lines = lines[first + 1:]  # the "Điều N. Title" line; the context header carries it
    return build_units(split_segments("\n".join(lines)))


# --- configuration -----------------------------------------------------------

def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_scope(path: Path = SCOPE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def short_document_name(title: str, config: dict[str, Any]) -> str:
    for rule in config.get("document_short_names") or []:
        if title.startswith(rule["prefix"]):
            return rule["short"]
    raise ValueError(f"No short name for document title: {title!r}")


def context_header(metadata: dict[str, Any], config: dict[str, Any], mode: str) -> str:
    article = str(metadata.get("article") or "").strip().rstrip(".")
    title = str(metadata.get("title") or "").strip()
    heading = f"{article}. {title}" if article and title else (article or title)
    if mode == "article":
        return heading
    short = short_document_name(str(metadata.get("document_title") or ""), config)
    if mode == "document_chapter_article" and metadata.get("chapter"):
        return f"{short} › {metadata['chapter']} › {heading}"
    return f"{short} › {heading}"


def _matches(rule: dict[str, Any], unit: Unit) -> bool:
    if "unit" in rule and str(rule["unit"]).lower() != str(unit.marker or "").lower():
        return False
    prefix = rule.get("lead_prefix")
    if prefix:
        lead = re.sub(r"^\S+\s*", "", unit.lead[0].text, count=1) if unit.marker else unit.lead[0].text
        if not lead.startswith(prefix):
            return False
    return True


def apply_scope(parent_id: str, units: list[Unit], scope: dict[str, Any]) -> tuple[list[Unit], list[str]]:
    """Drop excluded clauses and points; return what is kept and what was dropped."""
    dropped: list[str] = []
    rules = [r for r in scope.get("exclude_units") or [] if r["parent"] == parent_id]
    kept: list[Unit] = []
    for unit in units:
        unit_rules = [r for r in rules if _matches(r, unit)]
        if any("items" not in r for r in unit_rules):
            dropped.append(f"unit {unit.marker}")
            continue
        drop_items = {str(m).lower() for r in unit_rules for m in r.get("items", [])}
        if drop_items:
            remaining = [i for i in unit.items if str(i.marker or "").lower() not in drop_items]
            dropped += [f"unit {unit.marker} item {i.marker}" for i in unit.items if i not in remaining]
            unit = Unit(unit.marker, unit.lead, remaining)
        kept.append(unit)
    matched = {id(r) for r in rules for u in units if _matches(r, u)}
    unused = [r for r in rules if id(r) not in matched]
    if unused:
        raise ValueError(f"{parent_id}: scope rules match no clause: {unused}")
    return kept, dropped


# --- chunk building ----------------------------------------------------------

def _drop_structured_rows(unit: Unit, parent: dict[str, Any], tables: list[dict[str, Any]] | None) -> None:
    """Remove table rows the structured registry already holds (as the old builder did)."""
    if tables is None:
        return
    metadata = parent.get("metadata") or {}

    def keep(segment: Segment) -> Segment | None:
        if segment.kind != "table":
            return segment
        rows = []
        for row in segment.lines:
            block = {"text": row, "cohort": metadata.get("cohort"), "source_pages": metadata.get("source_pages") or [],
                     "parent_section_id": parent.get("_id")}
            if match_structured_table_block(block, tables)["status"] not in {"excluded_as_structured", "ignored_non_content"}:
                rows.append(row)
        return Segment("table", None, rows) if rows else None

    unit.lead = [s for s in (keep(s) for s in unit.lead) if s]
    for item in unit.items:
        item.parts = [s for s in (keep(s) for s in item.parts) if s]


def _split_oversized(items: list[Item], target: int) -> list[Item]:
    """Break a point longer than the target into pieces that each repeat its first line."""
    out: list[Item] = []
    for item in items:
        if len(item.text) <= target or len(item.parts) < 2:
            out.append(item)
            continue
        head, rest = item.parts[0], item.parts[1:]
        piece: list[Segment] = []
        for part in rest:
            if piece and len(head.text) + sum(len(x.text) for x in piece) + len(part.text) > target:
                out.append(Item(item.marker, [head, *piece]))
                piece = []
            piece.append(part)
        out.append(Item(item.marker, [head, *piece]))
    return out


def _group_items(unit: Unit, target: int) -> list[list[Item]]:
    groups: list[list[Item]] = [[]]
    lead = len(unit.lead_text)
    for item in _split_oversized(unit.items, target):
        size = lead + sum(len(i.text) for i in groups[-1]) + len(item.text)
        if groups[-1] and size > target:
            groups.append([])
        groups[-1].append(item)
    return groups


def unit_texts(unit: Unit, config: dict[str, Any], mode: str) -> list[tuple[str, str, list[str]]]:
    """(granularity, text, point markers) for every chunk one clause becomes."""
    markers = [str(i.marker) for i in unit.items if i.marker]
    if mode == "point" and unit.items:
        return [("point", unit.text([i]), [str(i.marker)] if i.marker else []) for i in unit.items]
    whole = unit.text()
    if len(whole) <= int(config["max_unit_chars"]):
        return [("clause" if unit.marker else "article", whole, markers)]
    if unit.items:
        return [("clause_part", unit.text(group), [str(i.marker) for i in group if i.marker])
                for group in _group_items(unit, int(config["group_target_chars"]))]
    return [("clause_part", part, []) for part in _split_long_text(whole, int(config["paragraph_chars"]))]


def build_structure_chunks(
    parents: list[dict[str, Any]],
    *,
    config: dict[str, Any],
    scope: dict[str, Any] | None = None,
    header_mode: str | None = None,
    unit_mode: str = "clause",
    structured_tables: list[dict[str, Any]] | None = None,
    report: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    scope = scope or {}
    header_mode = header_mode or config.get("header", "document_article")
    if header_mode not in HEADER_MODES or unit_mode not in UNIT_MODES:
        raise ValueError(f"Unknown header or unit mode: {header_mode}, {unit_mode}")
    excluded_parents = {r["id"] for r in scope.get("exclude_parents") or []}
    known = {str(p.get("_id")) for p in parents}
    unknown = sorted((excluded_parents | {r["parent"] for r in scope.get("exclude_units") or []}) - known)
    if unknown:
        raise ValueError(f"Scope names unknown parents: {unknown}")
    chunks: list[dict[str, Any]] = []
    for parent in parents:
        metadata = parent.get("metadata") or {}
        parent_id = str(metadata.get("parent_section_id") or parent.get("_id") or "")
        content_type = metadata.get("content_type") or metadata.get("chunk_type")
        if not parent_id or content_type not in INDEXABLE_CONTENT_TYPES:
            continue
        if parent_id in excluded_parents:
            if report is not None:
                report.setdefault("excluded_parents", []).append(parent_id)
            continue
        units, dropped = apply_scope(parent_id, article_units(parent), scope)
        if dropped and report is not None:
            report.setdefault("excluded_units", {})[parent_id] = dropped
        base = _base_metadata(parent, parent_id)
        header = context_header(metadata, config, header_mode)
        short = short_document_name(str(metadata.get("document_title") or ""), config)
        heading = _make_heading_chunk(parent, base)
        heading["metadata"].update(context_header=header, document_short=short)
        heading["embedding_text"] = heading["content"]  # already names the section and document
        chunks.append(heading)
        seen: set[str] = set()
        for unit_index, unit in enumerate(units):
            _drop_structured_rows(unit, parent, structured_tables)
            for part_index, (granularity, text, points) in enumerate(unit_texts(unit, config, unit_mode)):
                text = text.strip()
                key = re.sub(r"\s+", " ", text).lower()
                if len(text) < 24 or key in seen:
                    continue
                seen.add(key)
                chunk_id = f"cp_{parent_id}_u{unit_index:02d}_{part_index:02d}"
                path = " › ".join(x for x in [
                    str(metadata.get("article") or "").rstrip("."),
                    f"khoản {unit.marker}" if unit.marker else "",
                    f"điểm {', '.join(points)}" if points and granularity != "clause" else "",
                ] if x)
                chunks.append({
                    "_id": chunk_id,
                    "chunk_id": chunk_id,
                    "content": text,
                    "embedding_text": f"{header}\n{text}",
                    "metadata": {
                        **base,
                        "chunk_id": chunk_id,
                        "chunk_type": _chunk_type_for_content_type(str(base.get("content_type") or content_type)),
                        "content_type": base.get("content_type") or content_type,
                        "chunk_granularity": granularity,
                        "clause_marker": unit.marker,
                        "clause": unit.marker,
                        "points": points,
                        "path": path,
                        "context_header": header,
                        "document_short": short,
                    },
                })
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--docstore", default="data/processed/chunks/all_docstore_items.json")
    parser.add_argument("--registry", default="data/processed/tables/structured_tables_registry.json")
    parser.add_argument("--header", choices=HEADER_MODES)
    parser.add_argument("--unit", choices=UNIT_MODES, default="clause")
    parser.add_argument("--no-scope", action="store_true", help="Ignore configs/corpus_scope.yaml.")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    parents = json.loads(Path(args.docstore).read_text(encoding="utf-8"))
    tables = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    report: dict[str, Any] = {}
    chunks = build_structure_chunks(parents, config=load_config(), scope={} if args.no_scope else load_scope(),
                                    header_mode=args.header, unit_mode=args.unit,
                                    structured_tables=tables, report=report)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(chunks)} chunks -> {out}")
    print("granularity:", dict(Counter(c["metadata"]["chunk_granularity"] for c in chunks)))
    print("excluded parents:", len(report.get("excluded_parents", [])),
          "| articles with excluded clauses:", len(report.get("excluded_units", {})))


if __name__ == "__main__":
    main()
