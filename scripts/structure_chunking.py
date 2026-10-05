"""Structure-aware hierarchical contextual chunking of handbook articles.

A search chunk is one khoản (numbered clause) with all of its points: the unit a
handbook rule is written in. The earlier builder (build_child_parent_index.py)
made one chunk per line marker, so a lettered point lost the sentence saying what
it is a condition of ("2. Sinh viên bị buộc thôi học trong các trường hợp sau:" in
one chunk, "a) Bị cảnh báo học tập 03 lần liên tiếp" in another). Parents are not
changed; retrieval still returns the whole article (small-to-big). A khoản is
never split, however long: the longest is about 1,300 tokens, well inside the
embedding model's 8,192, and splitting long khoản helped no measured question
(2026-10-05, docs/DESIGN_DECISIONS.md).

Markers differ between handbooks (K48-K49 Điều 5 uses "−" where K50 numbers its
clauses), so levels are read from the order markers appear in each article, not
from a fixed list: the first marker type in an article is the clause level and
the first other type inside a clause is the point level; deeper markers, table
rows and wrapped lines stay with the point above them.

Out-of-scope articles, clauses and points (configs/corpus_scope.yaml) get no chunk.
"""
from __future__ import annotations

import argparse
import hashlib
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
    _strip_docstore_preamble,
    match_structured_table_block,
)

CONFIG_PATH = Path("configs/structure_chunking.yaml")
SCOPE_PATH = Path("configs/corpus_scope.yaml")
HEADER_MODES = ("article", "document_article", "document_chapter_article")

_MARKERS = (
    ("number", re.compile(r"^(\d{1,2})\.\s+(?=\S)")),
    ("subnumber", re.compile(r"^(\d{1,2}\.\d{1,2})\.\s+(?=\S)")),  # "1.2. Sinh viên …", not "2.00 trở lên"
    ("roman", re.compile(r"^([IVX]{1,4})\.\s+(?=\S)")),
    ("section", re.compile(r"^([A-ZĐ])\.\s+(?=\S)")),  # "B. Đối tượng sinh viên được xét theo thứ tự ưu tiên"
    ("letter", re.compile(r"^([a-zđ])\)\s*", re.IGNORECASE)),
    ("bullet", re.compile(r"^([-−–•+*])\s*")),
)


@dataclass
class Segment:
    """One marked line and the wrapped lines that continue it."""

    kind: str  # number | subnumber | roman | section | letter | bullet:<char> | table | text
    marker: str | None
    lines: list[str]
    nested: bool = False  # a marked line a layout fix puts under the point above it
    opens_group: bool = False  # a lead-in a layout fix says starts a new group of points

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
            return (f"bullet:{marker}" if kind == "bullet" else kind), (marker if kind == "section" else marker.lower())
    return "text", None


LAYOUT_FIXES_PATH = Path("configs/layout_fixes.yaml")
FIX_KINDS = {"heading_tail", "table_header", "label_of_next", "split_items", "nested_list", "starts_group"}
_LAYOUT_FIXES: dict[str, list[dict[str, Any]]] | None = None


def load_layout_fixes(path: Path = PROJECT_ROOT / LAYOUT_FIXES_PATH) -> dict[str, list[dict[str, Any]]]:
    """The reviewed layout fixes (configs/layout_fixes.yaml) by parent id."""
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for fix in (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("fixes") or []:
        if fix["fix"] not in FIX_KINDS or not (fix.get("line") or fix.get("line_prefix")):
            raise ValueError(f"Malformed layout fix: {fix}")
        by_parent.setdefault(fix["parent"], []).append(fix)
    return by_parent


def _fixes_for(parent_id: str) -> list[dict[str, Any]]:
    global _LAYOUT_FIXES
    if _LAYOUT_FIXES is None:
        _LAYOUT_FIXES = load_layout_fixes()
    return _LAYOUT_FIXES.get(parent_id, [])


def _matches_fix(line: str, fix: dict[str, Any]) -> bool:
    return line == fix.get("line") or bool(fix.get("line_prefix")) and line.startswith(fix["line_prefix"])


def _fix_for(line: str, fixes: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((fix for fix in fixes if _matches_fix(line, fix)), None)


def split_segments(body: str, fixes: list[dict[str, Any]] | None = None) -> list[Segment]:
    """Join the lines the PDF wrapped; start a segment at each marked line or table."""
    fixes = fixes or []
    lines: list[str] = []
    for raw in body.splitlines():
        line = _clean_block_text(raw)
        fix = _fix_for(line, fixes) if line else None
        if fix and fix["fix"] == "split_items":
            lines += [x for x in re.split(rf"(?<=[;:])\s+(?={re.escape(fix['before'])})", line) if x]
        elif line:
            lines.append(line)
    segments: list[Segment] = []
    label: list[str] = []
    nested = 0
    for line in lines:
        fix = _fix_for(line, fixes)
        action = fix["fix"] if fix else None
        if action == "label_of_next":
            label.append(line)
            continue
        if action == "table_header":
            segments.append(Segment("table", None, [line]))
            continue
        kind, marker = _segment_kind(line)
        if label:
            segments.append(Segment(kind, marker, [*label, line]))
            label = []
        elif action == "starts_group":
            segments.append(Segment("text", None, [line], opens_group=True))
        elif kind == "text" and segments and segments[-1].kind != "table":
            segments[-1].lines.append(line)  # a line wrapped by the PDF layout
        elif kind == "table" and segments and segments[-1].kind == "table":
            segments[-1].lines.append(line)
        else:
            segments.append(Segment(kind, marker, [line], nested=nested > 0 and kind != "table"))
            nested -= 1 if segments[-1].nested else 0
        if action == "nested_list":
            nested = int(fix["lines"])
    return segments


def build_units(segments: list[Segment]) -> list[Unit]:
    marked = [s.kind for s in segments if s.kind not in {"text", "table"}]
    top = marked[0] if marked else None
    units: list[Unit] = []
    current: Unit | None = None
    item_kind: str | None = None
    for segment in segments:
        if segment.nested and current is not None and current.items:
            current.items[-1].parts.append(segment)
            continue
        if segment.opens_group and current is not None:
            current = Unit(None, [segment])
            units.append(current)
            item_kind = None
            continue
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


def heading_line_count(lines: list[str], metadata: dict[str, Any], tails: tuple[str, ...] = ()) -> int:
    """How many of the first non-empty lines print the "Điều N. Title" heading.

    A long title wraps: "Điều 17. Chuyển ngành, …, chuyển cơ sở đào tạo," then
    "chuyển hình thức học" (54 articles on 2026-10-05).
    """
    article = " ".join(str(metadata.get("article") or "").split())
    title = " ".join(str(metadata.get("title") or "").split())
    # The raw title too: _looks_like_section_heading cleans "Hiệu trưởng" away as a signature line.
    variants = {f"{article.rstrip('.')}. {title}", title} if article else {title}
    count = next((n for n in (1, 2, 3) if len(lines) >= n and (
        " ".join(lines[:n]) in variants or _looks_like_section_heading(" ".join(lines[:n]), metadata))), 0)
    if not count and title:
        # A part printed in capitals, "CÁC MẪU ĐƠN VÀ BIỂU MẪU", stored as "Các mẫu đơn và biểu mẫu";
        # the page may print only the start of the stored title.
        printed = [n for n in (1, 2, 3) if len(lines) >= n and len(" ".join(lines[:n])) >= 10
                   and title.casefold().startswith(" ".join(lines[:n]).casefold())]
        count = max(printed, default=0)
    while count < len(lines) and lines[count] in tails:  # reviewed heading_tail fixes
        count += 1
    return count


def article_units(parent: dict[str, Any]) -> list[Unit]:
    metadata = parent.get("metadata") or {}
    body = _strip_docstore_preamble(str(parent.get("content") or ""))
    lines = [line for line in (_clean_block_text(raw) for raw in body.splitlines()) if line]
    fixes = _fixes_for(str(parent.get("_id")))
    unused = [fix for fix in fixes if not any(_matches_fix(line, fix) for line in lines)]
    if unused:
        raise ValueError(f"{parent.get('_id')}: layout fixes match no line: {unused}")
    tails = tuple(f["line"] for f in fixes if f["fix"] == "heading_tail")
    lines = lines[heading_line_count(lines, metadata, tails):]  # the context header carries the heading
    return _attach_list_to_lead_in(build_units(split_segments("\n".join(lines), fixes)))


def _attach_list_to_lead_in(units: list[Unit]) -> list[Unit]:
    """An article opening with an unnumbered sentence ending in ":" lists what follows.

    "Tài chính cho hoạt động NCKH của SV gồm các nguồn sau:" followed by "1. …",
    "2. …" is one list, not a lead-in and separate clauses: without this the
    sources lose what they are sources of (20 articles, 79 items, 2026-10-05).
    """
    if len(units) < 2 or units[0].marker is not None or units[0].items:
        return units
    if not units[0].lead_text.rstrip().endswith(":"):
        return units
    items = [Item(u.marker, [*u.lead, *(part for item in u.items for part in item.parts)]) for u in units[1:]]
    return [Unit(None, units[0].lead, items)]


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


def unit_chunk(unit: Unit) -> tuple[str, str, list[str]]:
    """(granularity, text, point markers): a khoản, or an article without khoản, is one chunk."""
    return "clause" if unit.marker else "article", unit.text(), [str(i.marker) for i in unit.items if i.marker]


def build_structure_chunks(
    parents: list[dict[str, Any]],
    *,
    config: dict[str, Any],
    scope: dict[str, Any] | None = None,
    header_mode: str | None = None,
    structured_tables: list[dict[str, Any]] | None = None,
    drop_table_parents: set[str] | None = None,
    report: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Search chunks for every indexable parent.

    ``drop_table_parents`` names parents whose tables were separated by the
    reviewed table regions: their table rows live in the structured registry and
    the table-search handles, never in narrative chunks.
    """
    scope = scope or {}
    header_mode = header_mode or config.get("header", "document_article")
    if header_mode not in HEADER_MODES:
        raise ValueError(f"Unknown header mode: {header_mode}")
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
        # A heading_tail fix holds the end of a title the stored title cuts short
        # ("…, Hội Sinh viên" + "Việt Nam Trường"); both heading texts get it back.
        tail = " ".join(f["line"].lower() if f["line"].isupper() else f["line"]
                        for f in _fixes_for(parent_id) if f["fix"] == "heading_tail")
        header = " ".join(x for x in [context_header(metadata, config, header_mode), tail] if x)
        short = short_document_name(str(metadata.get("document_title") or ""), config)
        heading = _make_heading_chunk(parent, base)
        # The old anchor was the first two PDF lines, cut mid-sentence ("…cảnh báo học tập nếu vi");
        # the clause chunks hold the text, so the heading chunk names the article only.
        heading_lines = [x for x in heading["content"].split("\n") if not x.startswith("Summary anchor:")]
        article_label = str(metadata.get("article") or "").strip()
        if article_label.startswith("Điều"):
            heading_lines[0] = f"Section heading: {article_label.rstrip('.')}. {metadata.get('title') or ''}".rstrip()
        if tail:
            heading_lines[0] = f"{heading_lines[0]} {tail}"
        heading["content"] = "\n".join(heading_lines)
        heading["metadata"].update(context_header=header, document_short=short)
        heading["embedding_text"] = heading["content"]  # already names the section and document
        chunks.append(heading)
        seen: set[str] = set()
        for unit_index, unit in enumerate(units):
            if drop_table_parents and parent_id in drop_table_parents:
                unit.lead = [s for s in unit.lead if s.kind != "table"]
                for item in unit.items:
                    item.parts = [s for s in item.parts if s.kind != "table"]
            _drop_structured_rows(unit, parent, structured_tables)
            granularity, text, points = unit_chunk(unit)
            text = text.strip()
            key = re.sub(r"\s+", " ", text).lower()
            if len(text) < 24 or key in seen:
                continue
            seen.add(key)
            chunk_id = f"cp_{parent_id}_u{unit_index:02d}_00"
            named = [m for m in points if m[0].isalnum()]  # "–" and "•" items have no name to cite
            path = " › ".join(x for x in [
                str(metadata.get("article") or "").rstrip("."),
                f"khoản {unit.marker}" if unit.marker and unit.marker[0].isalnum() else "",
                f"điểm {', '.join(named)}" if named and granularity != "clause" else "",
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


def _without_build_id(record: dict[str, Any]) -> dict[str, Any]:
    clean = {k: v for k, v in record.items() if k != "build_id"}
    clean["metadata"] = {k: v for k, v in (record.get("metadata") or {}).items() if k != "build_id"}
    return clean


def publish_artifacts(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Replace data/processed children with structure chunks; local files only.

    Parents are the published full parents (the documents MongoDB holds), so no
    text a student is cited changes. Run scripts.build_artifact_manifest next to
    stamp one build id and write the manifest.
    """
    from scripts.build_child_parent_index import validate_child_parent_chunks
    from scripts.build_parent_child_artifacts import POLICY, REGIONS, artifact_digest

    parent_path = root / "data/processed/chunks/all_docstore_items.json"
    child_path = root / "data/processed/chunks/child_parent_chunks.json"
    audit_path = root / "data/processed/metadata/structured_table_embedding_audit.json"
    registry_path = root / "data/processed/tables/structured_tables_registry.json"
    parents = [_without_build_id(p) for p in json.loads(parent_path.read_text(encoding="utf-8"))]
    reviewed = {e["parent_id"] for e in json.loads(REGIONS.read_text(encoding="utf-8"))["parents"]}
    report: dict[str, Any] = {}
    chunks = build_structure_chunks(parents, config=load_config(root / CONFIG_PATH),
                                    scope=load_scope(root / SCOPE_PATH),
                                    drop_table_parents=reviewed, report=report)
    for chunk in chunks:
        chunk["metadata"].update(table_separation_policy=POLICY, corpus_role="narrative_child")
    validate_child_parent_chunks(chunks, parents)
    leftover = [c["_id"] for c in chunks if re.search(r"^\|", c["content"], re.MULTILINE)]
    if leftover:
        raise ValueError(f"Table rows left in narrative chunks: {leftover[:5]}")
    from scripts.check_chunk_invariants import check

    problems = {k: v for k, v in check(chunks, parents, load_scope(root / SCOPE_PATH)).items() if v}
    if problems:
        raise ValueError(f"Chunk invariants fail: { {k: v[:3] for k, v in problems.items()} }")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    separation = audit["separation"]
    if separation["artifact_content_sha256"]["parent_docstore"] != artifact_digest(parents):
        raise ValueError("Parents differ from the separated build; rebuild the separation first")
    separation["child_count"] = len(chunks)
    separation["artifact_content_sha256"]["child_chunks"] = artifact_digest(chunks)
    separation["child_builder"] = "structure_chunking"
    child_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit.update(child_count=len(chunks), child_output_path=str(child_path),
                 structured_registry_sha256=hashlib.sha256(registry_path.read_bytes()).hexdigest())
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"chunks": len(chunks), **{k: len(v) for k, v in report.items()},
            "granularity": dict(Counter(c["metadata"]["chunk_granularity"] for c in chunks))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--docstore", default="data/processed/chunks/all_docstore_items.json")
    parser.add_argument("--registry", default="data/processed/tables/structured_tables_registry.json")
    parser.add_argument("--header", choices=HEADER_MODES)
    parser.add_argument("--no-scope", action="store_true", help="Ignore configs/corpus_scope.yaml.")
    parser.add_argument("--output", help="Write a chunk file for comparison only.")
    parser.add_argument("--publish-artifacts", action="store_true",
                        help="Replace data/processed children (local files); then run scripts.build_artifact_manifest.")
    args = parser.parse_args()
    if args.publish_artifacts:
        print(json.dumps(publish_artifacts(), ensure_ascii=False))
        return
    if not args.output:
        parser.error("--output is required unless --publish-artifacts is given")
    parents = json.loads(Path(args.docstore).read_text(encoding="utf-8"))
    tables = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    report: dict[str, Any] = {}
    chunks = build_structure_chunks(parents, config=load_config(), scope={} if args.no_scope else load_scope(),
                                    header_mode=args.header,
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
