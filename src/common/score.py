"""Parse a single score without discarding an explicitly supplied scale."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from typing import Any


@dataclass(frozen=True)
class Score:
    value: Decimal
    scale: Decimal | None = None


_SCORE_PATTERN = re.compile(
    r"\s*([+-]?\d+(?:[,.]\d+)?)\s*(?:/\s*(\d+(?:[,.]\d+)?))?\s*"
)


def parse_score(value: Any) -> Score | None:
    """Return a score and optional denominator; reject prose and booleans."""

    if isinstance(value, bool):
        return None
    match = _SCORE_PATTERN.fullmatch(str(value))
    if not match:
        return None
    try:
        score = Decimal(match.group(1).replace(",", "."))
        scale = (
            Decimal(match.group(2).replace(",", "."))
            if match.group(2) is not None else None
        )
    except InvalidOperation:
        return None
    return Score(score, scale) if scale is None or scale > 0 else None


def grounded_score(value: Any, span: Any, source_text: str) -> Score | None:
    """Verify a numeric operand and retain its complete source denominator.

    A literal span may end before ``/4`` or start at its denominator. Match
    complete numeric expressions in the source, not independent digit tokens.
    Conflicting occurrences of the same abbreviated span stay unresolved.
    """

    supplied = parse_score(value)
    if supplied is None:
        return None
    source = " ".join(unicodedata.normalize("NFC", str(source_text)).casefold().split())
    spans = span if isinstance(span, list) else [span]
    # Do not interpret cohort identifiers or a fraction's denominator as scores.
    tokens = list(re.finditer(
        r"(?<![\w/])[+-]?\d+(?:[,.]\d+)?(?:\s*/\s*\d+(?:[,.]\d+)?)?"
        r"(?!\w|\s*/|[,.]\d)", source,
    ))
    observed: set[Score] = set()
    for literal in spans:
        if not isinstance(literal, str) or not literal.strip():
            return None
        literal = " ".join(unicodedata.normalize("NFC", literal).casefold().split())
        for occurrence in re.finditer(re.escape(literal), source):
            for token in tokens:
                if token.start() >= occurrence.end() or token.end() <= occurrence.start():
                    continue
                score = parse_score(token.group())
                if score is not None and score.value == supplied.value:
                    if supplied.scale is not None and score.scale != supplied.scale:
                        return None
                    observed.add(score)
    return next(iter(observed)) if len(observed) == 1 else None


def scores_equal(actual: Any, expected: Any, *, expected_scale: int | None) -> bool:
    """Compare values in a known table scale, retaining explicit denominators."""

    left, right = parse_score(actual), parse_score(expected)
    if left is None or right is None or left.value != right.value:
        return False
    declared = {item.scale for item in (left, right) if item.scale is not None}
    if len(declared) > 1:
        return False
    if expected_scale is not None:
        return not declared or declared == {Decimal(expected_scale)}
    return left.scale == right.scale
