"""Spell out a "<level> trở lên" table cell as one row per level it admits.

K51's scholarship table states some conditions as a minimum level, for example
academic "Giỏi" with conduct "Tốt trở lên". Asked about academic Giỏi with
conduct Xuất sắc, the composer found no row that matched word for word and
denied the scholarship in two of three tries. A row for every admitted level
leaves it a row to read, not a comparison to make. The handbook's own wording
stays on each derived row.
"""
from __future__ import annotations

import re
from typing import Any

from src.common.text import fold_text

# Each scale from lowest to highest, as the handbook's classification tables order them.
ACADEMIC = ("Kém", "Yếu", "Trung bình", "Khá", "Giỏi", "Xuất sắc")
CONDUCT = ("Kém", "Yếu", "Trung bình", "Khá", "Tốt", "Xuất sắc")

_AT_LEAST = re.compile(r"^\s*(.+?)\s+trở lên\s*$", re.IGNORECASE)


def _scale_of(values: list[str]) -> tuple[str, ...] | None:
    """The scale a column uses, told apart by the level only one scale has."""

    bases = {fold_text(_AT_LEAST.sub(r"\1", value)) for value in values}
    if fold_text("Tốt") in bases:
        return CONDUCT
    if fold_text("Giỏi") in bases:
        return ACADEMIC
    return None


def spell_out_minimum_levels(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace each "<level> trở lên" cell by one row per admitted level.

    A cell that names no level of its column's scale is left as it is, and so is
    every row without such a cell. Derived rows carry `condition_in_handbook`.
    """
    columns = {key for row in rows for key, value in row.items() if isinstance(value, str)}
    scales = {}
    for column in columns:
        values = [row[column] for row in rows if isinstance(row.get(column), str)]
        if any(_AT_LEAST.match(value) for value in values):
            scale = _scale_of(values)
            if scale:
                scales[column] = scale

    out: list[dict[str, Any]] = []
    for row in rows:
        expanded = [dict(row)]
        for column, scale in scales.items():
            match = _AT_LEAST.match(str(row.get(column) or ""))
            folded = [fold_text(level) for level in scale]
            if not match or fold_text(match.group(1)) not in folded:
                continue
            admitted = scale[folded.index(fold_text(match.group(1))):]
            expanded = [
                {**variant, column: level, "condition_in_handbook": row[column]}
                for variant in expanded
                for level in admitted
            ]
        out.extend(expanded)
    return out
