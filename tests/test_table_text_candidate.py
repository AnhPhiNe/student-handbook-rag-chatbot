from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.build_table_text_candidate import build_candidate, dump
from scripts.build_child_parent_index import build_child_parent_chunks


def fixtures():
    table = {
        "table_id": "duration", "table_name": "Thời gian học",
        "data_category": "regulation_table", "quality_status": "approved",
        "cohort": "K51", "document_id": "handbook", "source_parent_id": "p1",
        "source_pages": [3], "applicability": "Chính quy",
        "columns": ["Chương trình", "Chuẩn", "Tối đa"],
        "rows": [
            {"Chương trình": "Chương trình thứ nhất", "Chuẩn": "4 năm", "Tối đa": "8 năm"},
            {"Chương trình": "Liên thông", "Chuẩn": "2 năm", "Tối đa": "4 năm"},
        ],
    }
    flat = "Chương trình\nChuẩn\nTối đa\nChương trình thứ nhất\n4 năm\n8 năm\nLiên thông\n2 năm\n4 năm"
    parent = {
        "_id": "p1", "content": f"Điều 3. Thời gian học\n1. Chỉ áp dụng chính quy:\n{flat}\n2. Sinh viên nộp đơn theo quy định.",
        "metadata": {"title": "Thời gian học", "content_type": "regulation_text",
                     "cohort": "K51", "document_id": "handbook", "source_pages": [3]},
    }
    return parent, table, flat


def test_complete_flat_table_replaced_preserving_prose_and_input():
    parent, table, flat = fixtures()
    before = copy.deepcopy(parent)
    chunks, audit = build_candidate([parent], [table])
    assert parent == before
    assert audit["parents"][0]["removed_spans"][0]["source_text"] == flat
    prose = "\n".join(c["content"] for c in chunks if c["metadata"].get("block_type") != "registry_table")
    assert "Chỉ áp dụng chính quy" in prose
    assert "Sinh viên nộp đơn" in prose
    assert "Chương trình thứ nhất" not in prose
    canonical = "\n".join(c["content"] for c in chunks if c["metadata"].get("block_type") == "registry_table")
    assert "Chính quy" in canonical
    for row in table["rows"]:
        assert canonical.count(dump(row)) == 1


def test_partial_table_kept_for_review_and_numbers_never_removed_alone():
    parent, table, _ = fixtures()
    parent["content"] = "Điều 3. Thời gian học\n1. Chương trình thứ nhất 4 năm 8 năm. Nộp 4 đơn."
    chunks, audit = build_candidate([parent], [table])
    assert audit["parents"][0]["removed_spans"] == []
    assert audit["parents_requiring_review"] == 1
    assert any("Nộp 4 đơn" in c["content"] for c in chunks)


def test_changed_number_or_sign_does_not_authorize_source_removal():
    parent, table, _ = fixtures()
    parent["content"] = parent["content"].replace("8 năm", "80 năm")
    _, audit = build_candidate([parent], [table])
    assert audit["parents"][0]["removed_spans"] == []
    parent, table, _ = fixtures()
    parent["content"] = parent["content"].replace("2 năm", "-2 năm")
    _, audit = build_candidate([parent], [table])
    assert audit["parents"][0]["removed_spans"] == []


def test_markdown_and_flat_duplicates_removed_once_each():
    parent, table, _ = fixtures()
    parent["content"] += "\n| Chương trình | Chuẩn | Tối đa |\n| --- | --- | --- |\n| Chương trình thứ nhất | 4 năm | 8 năm |\n| Liên thông | 2 năm | 4 năm |\nGhi chú: không áp dụng lớp khác."
    chunks, audit = build_candidate([parent], [table])
    assert len(audit["parents"][0]["removed_spans"]) == 2
    assert any("không áp dụng lớp khác" in c["content"] for c in chunks)
    assert audit["rows_rendered"] == 2


@pytest.mark.parametrize("field,value", [("cohort", "K50"), ("document_id", "other"), ("source_pages", [9]), ("source_parent_id", "missing")])
def test_invalid_binding_fails_before_build(field, value):
    parent, table, _ = fixtures()
    table[field] = value
    with pytest.raises(ValueError):
        build_candidate([parent], [table])


@pytest.mark.parametrize("field,value", [("data_category", "directory"), ("quality_status", "draft"), ("used_by_runtime", False)])
def test_nonapproved_and_directory_tables_not_rendered(field, value):
    parent, table, _ = fixtures()
    table[field] = value
    chunks, audit = build_candidate([parent], [table])
    assert audit["tables_rendered"] == 0
    assert not any(c["metadata"].get("block_type") == "registry_table" for c in chunks)


def test_same_table_id_in_different_cohorts_does_not_collide():
    parent, table, _ = fixtures()
    other_parent, other_table = copy.deepcopy(parent), copy.deepcopy(table)
    other_parent["_id"] = other_table["source_parent_id"] = "p2"
    other_parent["metadata"]["cohort"] = other_table["cohort"] = "K50"
    chunks, audit = build_candidate([parent, other_parent], [table, other_table])
    assert audit["tables_rendered"] == 2
    assert len({c["_id"] for c in chunks}) == len(chunks)
    conflicting = {**table, "rows": [{"wrong": "value"}]}
    with pytest.raises(ValueError, match="Conflicting"):
        build_candidate([parent], [table, conflicting])


def test_missing_columns_keep_all_fields_and_types_and_oversize_row_fails():
    parent, table, _ = fixtures()
    table["columns"] = []
    table["rows"] = [{"level": "Giỏi", "multiplier": 1.25, "note": None, "condition": {"min": 0}}]
    chunks, _ = build_candidate([parent], [table])
    assert any(dump(table["rows"][0]) in c["content"] for c in chunks)
    with pytest.raises(ValueError, match="budget"):
        build_candidate([parent], [table], max_chars=20)


def test_frozen_corpus_preserves_all_registry_rows_and_untouched_parents():
    root = Path("data/processed")
    parents = json.loads((root / "chunks/all_docstore_items.json").read_text(encoding="utf-8"))
    registry = json.loads((root / "tables/structured_tables_registry.json").read_text(encoding="utf-8"))
    # Compare the experimental transform against its own input, not a different
    # production corpus policy (which may already have removed table regions).
    baseline = build_child_parent_chunks(parents, structured_tables=registry)
    chunks, audit = build_candidate(parents, registry)
    assert audit["tables_rendered"] == len(registry)
    for table in registry:
        bound = [c for c in chunks if c["metadata"].get("table_id") == table["table_id"]
                 and c["metadata"]["parent_section_id"] == table["source_parent_id"]]
        indices = [i for c in bound for i in c["metadata"]["table_row_indices"]]
        assert indices == list(range(len(table["rows"])))
        for row in table["rows"]:
            assert any(dump(row) in c["content"] for c in bound)
    touched = {a["parent_id"] for a in audit["parents"]}
    old = [c for c in baseline if c["metadata"]["parent_section_id"] not in touched]
    new = [c for c in chunks if c["metadata"]["parent_section_id"] not in touched]
    # Build stamping is external to the chunker; compare payloads before stamping.
    for c in old + new:
        c.pop("build_id", None)
        c["metadata"].pop("build_id", None)
    assert old == new
