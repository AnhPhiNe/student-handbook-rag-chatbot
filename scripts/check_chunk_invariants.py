"""Invariants every search-chunk build must hold, checked against the parents' raw lines.

    python -m scripts.check_chunk_invariants [--chunks data/processed/chunks/child_parent_chunks.json]

The checks read the handbook lines themselves, not the chunker's segments, so a
mistake in how the chunker reads the structure of a page shows up here:

  coverage       every in-scope line of an article is in a chunk
  boundary       every chunk line starts and ends where a sentence or a marked
                 line does; never inside a sentence or a word
  own_heading    no chunk repeats its own "Điều N." heading or is only a title
                 printed in capitals (the context header carries them)
  table_residue  no chunk keeps a short line the page prints just above a table
                 (a column header such as "TT")
  lead_in        a marked line introduced by a line ending in ":" is in a chunk
                 only after that line
  heading_drop   a line dropped as the article heading is part of the stored
                 title, or is on the reviewed list in configs/structure_chunking.yaml

Exempt: lines of out-of-scope articles, clauses and points
(configs/corpus_scope.yaml), table rows (the structured registry holds them) and
the article's heading lines. The one deliberate partial line is the lead-in a
long clause repeats in its later groups: a suffix of the lead-in that starts at a
sentence or clause boundary, first line of a ``clause_part`` chunk only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_child_parent_index import (  # noqa: E402
    INDEXABLE_CONTENT_TYPES,
    _clean_block_text,
    _strip_docstore_preamble,
)
from scripts.structure_chunking import (  # noqa: E402
    apply_scope,
    article_units,
    heading_line_count,
)

_MARKED = re.compile(r"^(?:\d{1,2}\.\s+\S|\d{1,2}\.\d{1,2}\.\s+\S|[IVX]{1,4}\.\s+\S|[a-zđ]\)|[-−–•+*])", re.IGNORECASE)
_SECTION = re.compile(r"^[A-ZĐ]\.\s+\S")  # case matters: "B. Đối tượng …"
_SENTENCE_END = tuple(".;:!?")
_COLUMN_HEADER_MAX = 12


def _marked(line: str) -> bool:
    return bool(_MARKED.match(line) or _SECTION.match(line))


def _norm(text: str) -> str:
    return " ".join(text.split())


def _is_column_header(line: str, next_line: str | None) -> bool:
    return (next_line is not None and next_line.startswith("|") and len(line) <= _COLUMN_HEADER_MAX
            and not line.endswith(_SENTENCE_END) and not _marked(line))


def _lines_of(units) -> set[str]:
    return {line for u in units for s in [*u.lead, *(p for i in u.items for p in i.parts)] for line in s.lines}


class ParentText:
    """An article's in-scope lines joined as the chunks join them, with its structural positions."""

    def __init__(self, parent: dict[str, Any], scope: dict[str, Any]):
        metadata = parent.get("metadata") or {}
        raw = [_clean_block_text(line) for line in _strip_docstore_preamble(str(parent.get("content") or "")).splitlines()]
        raw = [line for line in raw if line]
        skip = heading_line_count(raw, metadata)
        # A dropped heading line must be part of the stored heading; any other is listed
        # for review, so this check does not share the chunker's heading rule.
        stored = _norm(f"{metadata.get('article') or ''} {metadata.get('title') or ''}").casefold()
        self.unconfirmed_heading = [line for line in raw[:skip] if _norm(line).casefold() not in stored]
        units = article_units(parent)
        kept, _ = apply_scope(str(parent["_id"]), units, scope)
        excluded = _lines_of(units) - _lines_of(kept)
        self.text = ""
        self.starts: set[int] = {0}  # where a marked line, or a line after a gap, begins
        self.lead_in_starts: dict[int, str] = {}  # marked line start -> the line ending in ":" before it
        self.lines: list[str] = []
        self.column_headers: list[str] = []
        gap, previous = True, ""
        for index, line in enumerate(raw):
            next_line = raw[index + 1] if index + 1 < len(raw) else None
            if index < skip or line.startswith("|") or line in excluded:
                gap = True
                continue
            if _is_column_header(line, next_line):
                self.column_headers.append(line)
                gap = True
                continue
            position = len(self.text) + (1 if self.text else 0)
            if gap or _marked(line):
                self.starts.add(position)
                if not gap and _marked(line) and previous.endswith(":"):
                    self.lead_in_starts[position] = _norm(previous)
            self.text = f"{self.text} {line}" if self.text else line
            self.lines.append(_norm(line))
            gap, previous = False, line

    def _start_ok(self, i: int) -> bool:
        return i in self.starts or self.text[:i].rstrip().endswith(_SENTENCE_END)

    def _end_ok(self, j: int, line: str) -> bool:
        return j == len(self.text) or (j + 1) in self.starts or line.endswith(_SENTENCE_END)

    def locate(self, line: str, *, after: int = 0, carried: bool = False) -> tuple[str | None, int | None]:
        """(problem or None, start offset) for one chunk line.

        A chunk's lines follow the article's order, so the occurrence after the
        previous line is tried first: an article can print the same line twice
        ("a) Không đang là sinh viên …" under two clauses).
        """
        found = [m.start() for m in re.finditer(re.escape(line), self.text)]
        found = [i for i in found if i >= after] + [i for i in found if i < after]
        if not found:
            return "not verbatim in the article", None
        for i in found:
            j = i + len(line)
            start = self._start_ok(i) or (carried and self.text[:i].rstrip().endswith(",") and line[:1].isupper())
            if start and self._end_ok(j, line):
                return None, i
        i = found[0]
        where = "starts" if not self._start_ok(i) else "ends"
        return f"{where} inside a sentence", i


def check(chunks: list[dict[str, Any]], parents: list[dict[str, Any]], scope: dict[str, Any],
          config: dict[str, Any] | None = None) -> dict[str, list]:
    excluded_parents = {r["id"] for r in scope.get("exclude_parents") or []}
    by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        if (chunk.get("metadata") or {}).get("chunk_granularity") in {"section_heading", "table_description"}:
            continue
        by_parent[str(chunk["metadata"]["parent_section_id"])].append(chunk)
    from scripts.structure_chunking import load_config

    reviewed = {(r["parent"], r["line"]) for r in (config or load_config()).get("reviewed_heading_tails") or []}
    problems: dict[str, list] = {k: [] for k in ("coverage", "boundary", "own_heading", "table_residue", "lead_in",
                                                 "heading_drop")}
    for parent in parents:
        metadata = parent.get("metadata") or {}
        parent_id = str(parent.get("_id"))
        if (metadata.get("content_type") or metadata.get("chunk_type")) not in INDEXABLE_CONTENT_TYPES:
            continue
        if parent_id in excluded_parents:
            continue
        text = ParentText(parent, scope)
        problems["heading_drop"] += [{"parent": parent_id, "line": line} for line in text.unconfirmed_heading
                                     if (parent_id, line) not in reviewed]
        own = by_parent.get(parent_id, [])
        bodies = [_norm(c["content"]) for c in own]
        for line in text.lines:
            if any(line in body for body in bodies):
                continue
            pieces = [p for p in re.split(r"(?<=[.;:!?])\s+", line) if p]
            if not all(any(p in body for body in bodies) for p in pieces):
                problems["coverage"].append({"parent": parent_id, "line": line[:120]})
        article = str(metadata.get("article") or "").strip()
        for chunk in own:
            chunk_lines = [_norm(x) for x in chunk["content"].split("\n") if x.strip() and not x.startswith("|")]
            if article.startswith("Điều") and chunk_lines and chunk_lines[0].startswith(article):
                problems["own_heading"].append({"chunk": chunk["_id"], "text": chunk_lines[0][:120]})
            elif len(chunk_lines) == 1 and chunk_lines[0].isupper():
                problems["own_heading"].append({"chunk": chunk["_id"], "text": chunk_lines[0][:120]})  # a title in capitals
            for header in text.column_headers:
                if any(x == header or x.endswith(f" {header}") for x in chunk_lines):
                    problems["table_residue"].append({"chunk": chunk["_id"], "residue": header})
            carried_ok = chunk["metadata"].get("chunk_granularity") == "clause_part"
            cursor = 0
            for index, line in enumerate(chunk_lines):
                problem, start = text.locate(line, after=cursor, carried=carried_ok and index == 0)
                cursor = start + len(line) if start is not None else cursor
                if problem:
                    problems["boundary"].append({"chunk": chunk["_id"], "problem": problem,
                                                 "head": line[:60], "tail": line[-60:]})
                elif start in text.lead_in_starts and text.lead_in_starts[start] not in " ".join(chunk_lines[:index]):
                    problems["lead_in"].append({"chunk": chunk["_id"], "head": line[:80]})
    return problems


def main() -> None:
    from scripts.structure_chunking import load_scope

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--chunks", default="data/processed/chunks/child_parent_chunks.json")
    parser.add_argument("--parents", default="data/processed/chunks/all_docstore_items.json")
    args = parser.parse_args()
    chunks = json.loads(Path(args.chunks).read_text(encoding="utf-8"))
    parents = json.loads(Path(args.parents).read_text(encoding="utf-8"))
    problems = check(chunks, parents, load_scope())
    print(json.dumps({k: len(v) for k, v in problems.items()}))
    for name, rows in problems.items():
        for row in rows[:15]:
            print(name, json.dumps(row, ensure_ascii=False))
    raise SystemExit(1 if any(problems.values()) else 0)


if __name__ == "__main__":
    main()
