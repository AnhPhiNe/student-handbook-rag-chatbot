"""Answers name the handbook they come from and flag documents a later handbook replaced."""
import json
from pathlib import Path

import yaml

from src.generation.prompt_builder import HANDBOOK_CURRENCY_PATH, render_answer_prompt

ROOT = Path(__file__).resolve().parents[1]


def _unit(cohort: str, *sources: dict) -> dict:
    return {"task_id": "t1", "question": "q", "cohort": cohort, "coverage": "covered", "mode": "rag",
            "clarification_question": None, "allowed_source_refs": ["S1"],
            "primary_evidence": [{"source_ref": f"S{i + 1}", "content": "...", **s} for i, s in enumerate(sources)]}


def _rendered_sources(packet: dict) -> list[dict]:
    _, context = render_answer_prompt("q", packet)
    return [s for unit in json.loads(context)["units"] for s in unit["primary_evidence"]]


def test_every_note_matches_sections_that_exist() -> None:
    """A renamed section id would silently drop a note; every prefix must still match."""

    config = yaml.safe_load(HANDBOOK_CURRENCY_PATH.read_text(encoding="utf-8"))
    ids = {str(d["_id"]) for d in json.loads((ROOT / "data/processed/chunks/all_docstore_items.json").read_text(encoding="utf-8"))}
    assert set(config["handbook_years"]) == {"K48-K49", "K50", "K51"}
    for entry in config["notes"]:
        assert entry["note"].strip() and entry["basis"].strip()
        for prefix in entry["sources"]:
            assert any(i.startswith(prefix) for i in ids), prefix


def test_a_replaced_regulation_is_labelled_with_its_handbook_and_flagged() -> None:
    old, current = _rendered_sources({"units": [_unit(
        "K48-K49",
        {"source_id": "K48-K49_K48_49_QuyCheCongTacSinhVien_Chuong5_Dieu28", "source_cohort": "K48-K49"},
    )]})[0], _rendered_sources({"units": [_unit(
        "K51",
        {"source_id": "K51_QuyCheCongTacSinhVien_Chuong5_Dieu27", "source_cohort": "K51"},
    )]})[0]

    assert old["printed_in"] == "Sổ tay sinh viên khóa K48-K49 (năm học 2022 – 2023)"
    assert "1999/QĐ-ĐHSP" in old["currency_note"] and "Sổ tay khóa K51" in old["currency_note"]
    assert current["printed_in"] == "Sổ tay sinh viên khóa K51 (năm học 2025 – 2026)"
    assert "currency_note" not in current


def test_a_document_printed_in_another_cohort_names_that_handbook() -> None:
    """The foreign-language regulation is printed only in the K50 handbook but applies to K51."""

    source = _rendered_sources({"units": [_unit(
        "K51",
        {"source_id": "K50_QuyDinhChuanDauRaNgoaiNgu_KhongCoChuong_Dieu8", "source_cohort": "K50"},
    )]})[0]

    assert source["printed_in"].startswith("Sổ tay sinh viên khóa K50")


def test_the_composer_is_told_to_name_the_handbook_and_carry_the_note() -> None:
    prompt, _ = render_answer_prompt("q", {"units": [_unit("K50", {"source_id": "x", "source_cohort": "K50"})]})

    assert "Nêu rõ câu trả lời dựa theo sổ tay nào, theo printed_in" in prompt
    assert "thêm nguyên nội dung currency_note" in prompt


def test_the_judge_sees_the_handbook_and_the_note_the_composer_was_given() -> None:
    """Otherwise a note the composer was told to repeat reads as an unsupported claim."""

    from src.evaluation.judge import _authorized_packet_evidence_units

    _, context = render_answer_prompt("q", {"units": [_unit(
        "K48-K49",
        {"source_id": "K48-K49_K48_49_QuyCheCongTacSinhVien_Chuong5_Dieu28", "source_cohort": "K48-K49"},
    )]})
    units = _authorized_packet_evidence_units(context)

    assert any("Printed in: Sổ tay sinh viên khóa K48-K49" in u for u in units)
    assert any("Currency note:" in u and "1999/QĐ-ĐHSP" in u for u in units)
