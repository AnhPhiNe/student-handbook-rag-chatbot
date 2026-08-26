from __future__ import annotations

import json
from pathlib import Path

from scripts.build_child_parent_index import build_child_parent_chunks


def _parent(content: str) -> dict:
    parent_id = "K51_Test_Dieu1"
    return {
        "_id": parent_id,
        "cohort": "K51",
        "document_id": "so_tay_sinh_vien_khoa_51",
        "content": f"Nội dung:\n{content}",
        "metadata": {
            "parent_section_id": parent_id,
            "cohort": "K51",
            "document_id": "so_tay_sinh_vien_khoa_51",
            "document_title": "Sổ tay sinh viên khóa 51",
            "title": "Điều 1",
            "article": "Điều 1.",
            "content_type": "regulation_text",
            "source_pages": [10],
        },
    }


def _table() -> dict:
    return {
        "table_id": "K51_Test_Dieu1_duration",
        "cohort": "K51",
        "source_parent_id": "K51_Test_Dieu1",
        "columns": ["Chương trình", "Chuẩn", "Tối đa"],
        "rows": [
            {
                "Chương trình": "Cấp bằng thứ nhất",
                "Chuẩn": "4 năm",
                "Tối đa": "6 năm",
            }
        ],
        "source_pages": [10],
        "quality_status": "approved",
        "used_by_runtime": True,
    }


def test_only_registry_covered_table_rows_are_excluded() -> None:
    parent = _parent(
        "\n".join(
            [
                "| Chương trình | Chuẩn | Tối đa |",
                "| --- | --- | --- |",
                "| Cấp bằng thứ nhất | 4 năm | 6 năm |",
                "| Chương trình chưa chuẩn hóa | 5 năm | 8 năm |",
            ]
        )
    )
    audit: list[dict] = []

    chunks = build_child_parent_chunks(
        [parent],
        structured_tables=[_table()],
        table_embedding_audit=audit,
    )

    assert [row["status"] for row in audit] == [
        "excluded_as_structured",
        "ignored_non_content",
        "excluded_as_structured",
        "retained_unmatched",
    ]
    child_text = "\n".join(
        chunk["content"]
        for chunk in chunks
        if chunk["metadata"]["chunk_granularity"] == "child"
    )
    assert "Cấp bằng thứ nhất" not in child_text
    assert "Chương trình chưa chuẩn hóa" in child_text
    assert "| --- | --- | --- |" not in child_text


def test_cohort_or_source_parent_mismatch_never_suppresses_row() -> None:
    parent = _parent("| Cấp bằng thứ nhất | 4 năm | 6 năm |")
    wrong_table = {**_table(), "cohort": "K50"}
    audit: list[dict] = []

    chunks = build_child_parent_chunks(
        [parent],
        structured_tables=[wrong_table],
        table_embedding_audit=audit,
    )

    assert audit[0]["status"] == "retained_unmatched"
    assert audit[0]["reason"] == "cohort_or_quality_mismatch"
    assert any("Cấp bằng thứ nhất" in chunk["content"] for chunk in chunks)


def test_current_registry_covers_every_contentful_table_row() -> None:
    parents = json.loads(
        Path("data/processed/chunks/all_docstore_items.json").read_text(
            encoding="utf-8"
        )
    )
    registry = json.loads(
        Path("data/processed/tables/structured_tables_registry.json").read_text(
            encoding="utf-8"
        )
    )
    audit: list[dict] = []

    chunks = build_child_parent_chunks(
        parents,
        structured_tables=registry,
        table_embedding_audit=audit,
    )

    assert len(audit) == 167
    assert sum(row["status"] == "excluded_as_structured" for row in audit) == 145
    assert sum(row["status"] == "ignored_non_content" for row in audit) == 22
    assert not [row for row in audit if row["status"] == "retained_unmatched"]
    assert not [
        chunk
        for chunk in chunks
        if (chunk.get("metadata") or {}).get("block_type") == "table_like_row"
    ]
