"""Keep the identifiers in an answer exactly as the evidence gives them.

Emails, links, phone numbers, document codes and room numbers are useless with
a single wrong character, and the composer never needs to rephrase them; the
prompt already asks for them to be copied verbatim. The composer still slips
now and then: over 768 saved answers, 1 of 200 identifiers was wrong
("khotienganh@hcmue.edu.vn" for "khoatienganh@hcmue.edu.vn", 2026-09-28).

An identifier found verbatim in the evidence (or the question) is kept. One
that is not is replaced when exactly one identifier of the same kind in the
evidence is within a small edit distance; otherwise it is kept and logged.
Numbers in running text are not checked: the composer legitimately rewrites
them ("01 tuần" as "7 ngày"), and the table values that matter most are
already fixed by the fact lock.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("student_handbook_rag.generation.verbatim_identifiers")


@dataclass(frozen=True)
class _Kind:
    pattern: re.Pattern[str]
    max_distance: int
    normalize: Callable[[str], str]


def _lower(value: str) -> str:
    return value.lower()


def _link(value: str) -> str:
    return re.sub(r"^https?://", "", value.lower()).rstrip("/")


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value.lower())


# Checked in this order; a span claimed by an earlier kind (the domain of an
# email) is not read again as a later one.
KINDS: dict[str, _Kind] = {
    "email": _Kind(re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), 2, _lower),
    "link": _Kind(
        re.compile(r"(?:https?://)?(?:[\w-]+\.)+(?:vn|com|edu|org|net|gov)(?:/[^\s)\]`*\"'<>]*[^\s)\]`*\"'<>.,;:])?"),
        2,
        _link,
    ),
    "phone": _Kind(re.compile(r"(?:\(0\d{2,3}\)\s?|\b0\d{2,3}[\s.]?)\d{3,4}[\s.]?\d{3,4}\b"), 1, _digits),
    "doc_code": _Kind(
        re.compile(r"\b\d{1,4}/\d{4}/[A-ZĐ][A-ZĐa-z0-9-]*[A-ZĐa-z0-9]|\b\d{1,4}/[A-ZĐ]{2,}(?:-[A-ZĐ]+)*"),
        1,
        _lower,
    ),
    "room": _Kind(re.compile(r"\bP\.\s?\d{2,4}\b"), 1, _compact),
}


def _edit_distance(a: str, b: str, limit: int) -> int:
    """Typing edits between a and b: insert, delete, replace, or swap two
    neighbouring characters, each counting one (so "38352002" is one edit from
    "38352020"). Returns limit + 1 at once when the lengths already differ by
    more than limit.
    """
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    rows = [list(range(len(b) + 1))]
    for i in range(1, len(a) + 1):
        row = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            row[j] = min(rows[-1][j] + 1, row[j - 1] + 1, rows[-1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                row[j] = min(row[j], rows[-2][j - 2] + 1)
        rows.append(row)
    return rows[-1][-1]


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _evidence_text(text: str) -> str:
    """The text of an evidence packet; JSON is decoded so escaped letters (Đ) match."""
    try:
        return "\n".join(_strings(json.loads(text)))
    except (TypeError, ValueError):
        return text


def _spans(text: str) -> Iterator[tuple[str, re.Match[str]]]:
    """Every identifier in the text, with the kind that claims it first."""
    claimed: list[tuple[int, int]] = []
    for kind, spec in KINDS.items():
        for match in spec.pattern.finditer(text):
            start, end = match.span()
            if any(start < other_end and other_start < end for other_start, other_end in claimed):
                continue
            claimed.append((start, end))
            yield kind, match


class IdentifierCorrector:
    """Correct the identifiers of one answer against its evidence and question."""

    def __init__(self, *evidence_texts: str) -> None:
        # Per kind: identifiers corrected, and identifiers left as written with
        # no single near match in the evidence (for tracing; no values kept).
        self.counts: Counter[str] = Counter()
        self._known: dict[str, dict[str, str]] = {kind: {} for kind in KINDS}
        self._text = "\n".join(_evidence_text(text) for text in evidence_texts if text)
        for kind, match in _spans(self._text):
            value = KINDS[kind].normalize(match.group(0))
            if value:
                self._known[kind].setdefault(value, match.group(0))

    def _is_known(self, kind: str, value: str) -> bool:
        if value in self._known[kind]:
            return True
        # A phone number may be split differently in the evidence.
        return kind == "phone" and value in _digits(self._text)

    def fix(self, text: str) -> str:
        """Return the text with each unknown identifier replaced by its unique near match."""
        replacements: list[tuple[int, int, str]] = []
        for kind, match in _spans(text):
            spec = KINDS[kind]
            value = spec.normalize(match.group(0))
            if not value or self._is_known(kind, value):
                continue
            near = [
                original
                for known, original in self._known[kind].items()
                if _edit_distance(value, known, spec.max_distance) <= spec.max_distance
            ]
            if len(near) == 1:
                replacements.append((match.start(), match.end(), near[0]))
                self.counts[f"identifier_corrected:{kind}"] += 1
                logger.warning("answer_identifier_corrected", extra={"kind": kind})
            else:
                self.counts[f"identifier_not_in_evidence:{kind}"] += 1
                logger.warning(
                    "answer_identifier_not_in_evidence",
                    extra={"kind": kind, "candidates": len(near)},
                )
        for start, end, replacement in sorted(replacements, reverse=True):
            text = text[:start] + replacement + text[end:]
        return text
