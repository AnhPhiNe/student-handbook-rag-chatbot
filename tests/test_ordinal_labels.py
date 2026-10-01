"""A minimum level in a table cell gets the list of levels it admits."""
import json
from pathlib import Path

from src.retrieval.core.ordinal_labels import annotate_minimum_levels

ROOT = Path(__file__).resolve().parents[1]


def _table(cohort: str, subtype: str) -> dict:
    tables = json.loads((ROOT / "data/processed/tables/structured_tables_registry.json").read_text(encoding="utf-8"))
    return next(t for t in tables if t["cohort"] == cohort and t["table_subtype"] == subtype)


def test_k51_scholarship_rows_keep_the_handbook_cells_and_list_admitted_levels() -> None:
    rows = _table("K51", "scholarship_classification")["rows"]
    annotated = annotate_minimum_levels(rows)

    # The handbook's rows and wording are unchanged; only the list is added.
    assert [{k: v for k, v in row.items() if not k.endswith("_admitted_levels")} for row in annotated] == rows
    admitted = {
        (row["academic_classification"], row["conduct_classification_condition"]):
            row.get("conduct_classification_condition_admitted_levels")
        for row in annotated
    }
    assert admitted[("Giỏi", "Tốt trở lên")] == ["Tốt", "Xuất sắc"]
    assert admitted[("Khá", "Khá trở lên")] == ["Khá", "Tốt", "Xuất sắc"]
    assert admitted[("Xuất sắc", "Tốt")] is None


def test_tables_without_a_minimum_level_are_untouched() -> None:
    for cohort, subtype in (("K51", "academic_classification"), ("K50", "scholarship_classification"),
                            ("K48-K49", "conduct_classification"), ("K51", "scholarship_amount")):
        rows = _table(cohort, subtype)["rows"]
        assert annotate_minimum_levels(rows) == rows


def test_an_unknown_level_is_left_as_written() -> None:
    rows = [{"level": "Giỏi", "condition": "Hạng A trở lên"}]
    assert annotate_minimum_levels(rows) == rows
