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
UNIT_MODES = ("clause", "point")

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


_INLINE_ITEM = re.compile(r"(?<=[;:])\s+(?=[–−]\s)")
_SENTENCE_END = (".", ";", ":", "!", "?")


def _is_column_header(line: str, next_line: str | None) -> bool:
    """A short line printed just above a table ("TT") heads one of its columns."""
    return (next_line is not None and next_line.startswith("|") and len(line) <= 12
            and not line.endswith(_SENTENCE_END) and _segment_kind(line)[0] == "text")


def _opens_list(line: str, previous: str) -> bool:
    """A new sentence ending in ":" after a finished one introduces what follows ("Xếp loại đánh giá đề tài:")."""
    return line.endswith(":") and line[:1].isupper() and previous.endswith(_SENTENCE_END)


def split_segments(body: str) -> list[Segment]:
    lines: list[str] = []
    for raw in body.splitlines():
        line = _clean_block_text(raw)
        # A list the PDF ran into one line: "…; – Mồ côi cha…; – Cả cha và mẹ…".
        lines += [part for part in _INLINE_ITEM.split(line) if part] if line else []
    segments: list[Segment] = []
    for index, line in enumerate(lines):
        if _is_column_header(line, lines[index + 1] if index + 1 < len(lines) else None):
            segments.append(Segment("table", None, [line]))
            continue
        kind, marker = _segment_kind(line)
        if kind == "text" and segments and segments[-1].kind != "table" and not _opens_list(line, lines[index - 1]):
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
    last: Segment | None = None
    in_sublist = False
    for index, segment in enumerate(segments):
        following = segments[index + 1] if index + 1 < len(segments) else None
        # A lead-in between two runs of points heads the second run: "… (điểm tối
        # đa là 10)." / "Xếp loại đánh giá đề tài:" / "a) Hội đồng …".
        if (segment.kind == "text" and segment.text.endswith(":") and current is not None and current.items
                and following is not None and following.kind == item_kind and following.kind != top):
            current = Unit(None, [segment])
            units.append(current)
            item_kind, last, in_sublist = None, segment, False
            continue
        # A point ending in ":" opens a list that may reuse the clause marker
        # ("e) …, cụ thể (chọn 01 trong các sản phẩm):" then "– Bài báo …;").
        # Those lines belong to the point while the list goes on with ";".
        if (top is not None and segment.kind == top and current is not None and current.items and last is not None
                and last.kind != "table"
                and (last.text.endswith(":") and last in current.items[-1].parts
                     or in_sublist and last.text.endswith(";"))):
            current.items[-1].parts.append(segment)
            last, in_sublist = segment, True
            continue
        in_sublist = False
        last = segment
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


def heading_line_count(lines: list[str], metadata: dict[str, Any]) -> int:
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
    # The stored title can stop where the page wrapped it ("…, Hội Sinh viên" then
    # "Việt Nam Trường"; "…hỗ trợ chi phí" then "HỌC TẬP"): a short unpunctuated
    # line before the first marked line is the rest of the heading.
    if len(lines) > count + 1:
        tail, following = lines[count], lines[count + 1]
        if (len(tail) <= 40 and not tail.endswith(_SENTENCE_END) and _segment_kind(tail)[0] == "text"
                and _segment_kind(following)[0] not in {"text", "table"} and (count or tail.isupper())):
            count += 1
    return count


def article_units(parent: dict[str, Any]) -> list[Unit]:
    metadata = parent.get("metadata") or {}
    body = _strip_docstore_preamble(str(parent.get("content") or ""))
    lines = [line for line in (_clean_block_text(raw) for raw in body.splitlines()) if line]
    lines = lines[heading_line_count(lines, metadata):]  # the context header carries the heading
    return _attach_list_to_lead_in(build_units(split_segments("\n".join(lines))))


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
        carried = _carried_lead(unit.lead_text, int(config["max_lead_chars"]))
        groups = _group_items(Unit(unit.marker, [Segment("text", None, [carried])], unit.items),
                              int(config["group_target_chars"]))
        out = []
        for index, group in enumerate(groups):
            # The first group keeps the whole opening; later ones repeat only the
            # sentence that introduces the list.
            lead = unit.lead_text if index == 0 else carried
            text = "\n".join(x for x in [lead, *(i.text for i in group)] if x)
            out.append(("clause_part", text, [str(i.marker) for i in group if i.marker]))
        return out
    return [("clause_part", part, []) for part in _split_at_sentences(whole, int(config["paragraph_chars"]))]


def _split_at_sentences(text: str, target: int) -> list[str]:
    """Pack whole lines, then whole sentences, into parts near the target size.

    A part ends only where a line or a sentence does; a sentence longer than the
    target stays whole rather than being cut.
    """
    pieces = [s for line in text.split("\n") for s in re.split(r"(?<=[.;!?])\s+(?=\S)", line) if s]
    parts: list[str] = []
    for piece in pieces:
        if parts and len(parts[-1]) + 1 + len(piece) <= target:
            parts[-1] = f"{parts[-1]} {piece}"
        else:
            parts.append(piece)
    return parts


def _carried_lead(lead: str, limit: int) -> str:
    """The lead-in repeated in each group of a long list: whole if short, else its last sentence.

    A notice opens with its title and legal bases before "…, cụ thể như sau:";
    only that last sentence says what the list is.
    """
    if len(lead) <= limit:
        return lead
    flat = " ".join(lead.split())
    sentences = [s for s in re.split(r"(?<=[.;])\s+", flat) if s]
    if sentences and len(sentences[-1]) <= limit:
        return sentences[-1]
    # "Thực hiện Nghị định …, Thông tư … của Bộ …, Bộ Tài chính về việc …, Trường
    # thông báo …, cụ thể như sau:": the main clause starts at the last comma
    # followed by a capital letter; the clauses before it name the legal bases.
    starts = [m.end() for m in re.finditer(r",\s+", flat) if flat[m.end()].isupper() and len(flat) - m.end() <= limit]
    if starts:
        return flat[starts[-1]:]
    clauses = [m.end() for m in re.finditer(r"[,;]\s+", flat) if len(flat) - m.end() <= limit]
    return flat[clauses[0]:] if clauses else flat[-limit:]


def build_structure_chunks(
    parents: list[dict[str, Any]],
    *,
    config: dict[str, Any],
    scope: dict[str, Any] | None = None,
    header_mode: str | None = None,
    unit_mode: str = "clause",
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
            if drop_table_parents and parent_id in drop_table_parents:
                unit.lead = [s for s in unit.lead if s.kind != "table"]
                for item in unit.items:
                    item.parts = [s for s in item.parts if s.kind != "table"]
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
    parser.add_argument("--unit", choices=UNIT_MODES, default="clause")
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
