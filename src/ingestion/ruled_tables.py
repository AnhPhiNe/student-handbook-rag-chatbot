"""Read ruled tables from handbook PDF pages cell by cell.

Plain text extraction flattens a table: the cells of one row come out one
after another and the columns can no longer be told apart. The handbook
tables are drawn with ruling lines, so rows are the bands between horizontal
rules and cells are the spans between the vertical rules crossing each band.
Words (not whole text lines) are placed in cells, because one PDF text line
can run across a column rule. A cell whose top edge has no rule is the lower
part of a vertically merged cell: the merged text is given to every row it
spans. A row that continues onto the next page (no rule before the page
break) is merged back into the row it started in.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import fitz

RULE_TOLERANCE = 2.0


@dataclass
class TableRow:
    cells: list[str]
    pages: list[int] = field(default_factory=list)


def _rules(page: fitz.Page) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]]]:
    """Horizontal (y, x0, x1) and vertical (x, y0, y1) ruling segments."""
    horizontal, vertical = [], []
    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l":
                a, b = item[1], item[2]
                if abs(a.y - b.y) < 1 and abs(a.x - b.x) > 5:
                    horizontal.append((a.y, min(a.x, b.x), max(a.x, b.x)))
                elif abs(a.x - b.x) < 1 and abs(a.y - b.y) > 5:
                    vertical.append((a.x, min(a.y, b.y), max(a.y, b.y)))
            elif item[0] == "re":
                rect = item[1]
                if rect.height < 2 and rect.width > 5:
                    horizontal.append((rect.y0, rect.x0, rect.x1))
                elif rect.width < 2 and rect.height > 5:
                    vertical.append((rect.x0, rect.y0, rect.y1))
    return horizontal, vertical


def _merge_positions(values: list[float]) -> list[float]:
    merged: list[float] = []
    for value in sorted(values):
        if not merged or value - merged[-1] > RULE_TOLERANCE:
            merged.append(value)
    return merged


def _has_rule(horizontal: list[tuple[float, float, float]], y: float, x0: float, x1: float) -> bool:
    """Whether a horizontal rule at height y crosses the middle of [x0, x1]."""
    middle = (x0 + x1) / 2
    return any(abs(ry - y) <= RULE_TOLERANCE and rx0 - RULE_TOLERANCE <= middle <= rx1 + RULE_TOLERANCE
               for ry, rx0, rx1 in horizontal)


def page_table_rows(page: fitz.Page) -> tuple[list[list[str]], fitz.Rect | None]:
    """Rows of the ruled table on one page (cell texts), and the table's area."""
    horizontal, vertical = _rules(page)
    if len(vertical) < 2:
        return [], None
    top = min(y0 for _, y0, _ in vertical)
    bottom = max(y1 for _, _, y1 in vertical)
    left = min(x for x, _, _ in vertical)
    right = max(x for x, _, _ in vertical)
    area = fitz.Rect(left, top, right, bottom)
    ys = _merge_positions([top, bottom] + [y for y, x0, x1 in horizontal
                                           if top - RULE_TOLERANCE <= y <= bottom + RULE_TOLERANCE
                                           and x0 < right and x1 > left])
    words = [w for w in page.get_text("words")
             if area.contains(fitz.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2))]
    rows: list[list[str]] = []
    spans: list[list[tuple[float, float]]] = []  # each row's cell x-ranges
    for y0, y1 in zip(ys, ys[1:]):
        if y1 - y0 < 3:
            continue
        middle = (y0 + y1) / 2
        xs = _merge_positions([x for x, vy0, vy1 in vertical
                               if vy0 - RULE_TOLERANCE <= middle <= vy1 + RULE_TOLERANCE])
        cells, ranges = [], []
        for x0, x1 in zip(xs, xs[1:]):
            inside = [w for w in words
                      if y0 <= (w[1] + w[3]) / 2 <= y1 and x0 <= (w[0] + w[2]) / 2 < x1]
            inside.sort(key=lambda w: (w[5], w[6], w[7]))  # block, line, word order
            cells.append(" ".join(w[4] for w in inside).strip())
            ranges.append((x0, x1))
        if not any(cells):
            continue
        # Vertically merged cell: no rule above it -> it continues the cell above.
        if rows:
            above_cells, above_ranges = rows[-1], spans[-1]
            for index, (x0, x1) in enumerate(ranges):
                if _has_rule(horizontal, y0, x0, x1):
                    continue
                for above_index, (ax0, ax1) in enumerate(above_ranges):
                    if abs(ax0 - x0) <= RULE_TOLERANCE and abs(ax1 - x1) <= RULE_TOLERANCE:
                        merged = " ".join(part for part in (above_cells[above_index], cells[index]) if part)
                        above_cells[above_index] = merged
                        cells[index] = merged
                        _spread_up(rows, spans, len(rows) - 1, (x0, x1), merged)
        rows.append(cells)
        spans.append(ranges)
    return rows, area


def _spread_up(rows, spans, start, cell_range, text) -> None:
    """Give a merged cell's full text to the rows above that share it."""
    index = start
    while index >= 0:
        match = [i for i, (x0, x1) in enumerate(spans[index])
                 if abs(x0 - cell_range[0]) <= RULE_TOLERANCE and abs(x1 - cell_range[1]) <= RULE_TOLERANCE]
        if not match or not text.startswith(rows[index][match[0]]):
            return
        rows[index][match[0]] = text
        index -= 1


def extract_ruled_table(pdf_path: str, pages: list[int]) -> list[TableRow]:
    """Rows of one ruled table spanning `pages` (1-based), continuation rows merged.

    A page's first row continues the previous page's last row when its first
    cell is empty and it has the same number of cells.
    """
    document = fitz.open(pdf_path)
    rows: list[TableRow] = []
    for number in pages:
        page_rows, _ = page_table_rows(document[number - 1])
        for index, cells in enumerate(page_rows):
            if (index == 0 and rows and not cells[0].strip()
                    and len(cells) == len(rows[-1].cells)):
                previous = rows[-1]
                previous.cells = [" ".join(part for part in (a, b) if part).strip()
                                  for a, b in zip(previous.cells, cells)]
                if number not in previous.pages:
                    previous.pages.append(number)
                continue
            rows.append(TableRow(cells, [number]))
    return rows


def table_areas(pdf_path: str, pages: list[int]) -> dict[int, fitz.Rect]:
    """The ruled table area on each page, so prose extraction can skip it."""
    document = fitz.open(pdf_path)
    areas = {}
    for number in pages:
        _, area = page_table_rows(document[number - 1])
        if area is not None:
            areas[number] = area
    return areas
