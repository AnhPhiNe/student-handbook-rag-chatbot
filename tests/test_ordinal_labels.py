"""A minimum level in a table cell becomes one explicit row per admitted level."""
import json
from pathlib import Path

from src.retrieval.core.ordinal_labels import spell_out_minimum_levels

ROOT = Path(__file__).resolve().parents[1]


def _table(cohort: str, subtype: str) -> dict:
    tables = json.loads((ROOT / "data/processed/tables/structured_tables_registry.json").read_text(encoding="utf-8"))
    return next(t for t in tables if t["cohort"] == cohort and t["table_subtype"] == subtype)


def test_k51_scholarship_table_becomes_the_full_grid_of_pairs() -> None:
    rows = spell_out_minimum_levels(_table("K51", "scholarship_classification")["rows"])
    grid = {(r["academic_classification"], r["conduct_classification_condition"]): r["scholarship_level"] for r in rows}

    # Each pair has exactly one scholarship level, and the cases that failed are explicit.
    assert len(grid) == len(rows) == 9
    assert grid[("Giỏi", "Xuất sắc")] == "Giỏi"
    assert grid[("Khá", "Xuất sắc")] == "Khá"
    assert grid[("Khá", "Tốt")] == "Khá"
    assert grid[("Xuất sắc", "Tốt")] == "Giỏi"
    derived = [r for r in rows if r.get("condition_in_handbook")]
    assert {r["condition_in_handbook"] for r in derived} == {"Tốt trở lên", "Khá trở lên"}


def test_tables_without_a_minimum_level_are_untouched() -> None:
    for cohort, subtype in (("K51", "academic_classification"), ("K50", "scholarship_classification"),
                            ("K48-K49", "conduct_classification"), ("K51", "scholarship_amount")):
        rows = _table(cohort, subtype)["rows"]
        assert spell_out_minimum_levels(rows) == rows


def test_an_unknown_level_is_left_as_written() -> None:
    rows = [{"level": "Giỏi", "condition": "Hạng A trở lên"}]
    assert spell_out_minimum_levels(rows) == rows
