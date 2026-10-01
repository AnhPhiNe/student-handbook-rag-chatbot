"""Structured data matches the handbook text it was read from, both ways."""
import json
from pathlib import Path

import scripts.audit_extraction as audit_extraction

# The scholarship eligibility table restates Điều 27 in short form: its numbers
# match the source, its wording and its criterion labels ("Đối tượng") do not.
# No `aspect` value selects this table yet; make it verbatim before one does.
KNOWN_PARAPHRASES = {
    ("scholarship_eligibility", 0, "criterion"),
    ("scholarship_eligibility", 0, "requirement"),
    ("scholarship_eligibility", 2, "criterion"),
}


def test_committed_data_matches_its_source_but_for_the_known_paraphrases() -> None:
    _, findings = audit_extraction.audit()

    assert {f["kind"] for f in findings} <= {"cell_not_in_source"}, findings
    assert {(f["table"], f["row"], f["column"]) for f in findings} <= KNOWN_PARAPHRASES, findings


def _write(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_an_address_under_an_unread_label_is_reported(tmp_path, monkeypatch) -> None:
    """The defect this audit was written for: K48-K49 and K50 wrote "Phòng làm việc"."""

    record = {"cohort": "K50", "unit_name": "Trung tâm Ngoại ngữ", "office": "", "emails": ["tt@hcmue.edu.vn"],
              "raw_text": "Email\n: tt@hcmue.edu.vn\nPhòng làm việc\n: Dãy nhà B, tầng 6, P.601"}
    _write(tmp_path / "student_service_directory.json", [record])
    _write(tmp_path / "student_faculty_profiles.json", [])
    monkeypatch.setattr(audit_extraction, "DIRECTORIES", tmp_path)

    found = list(audit_extraction.directory_findings())

    assert [(f["kind"], f["field"]) for f in found] == [("labelled_value_not_extracted", "office")]


def test_a_cell_whose_number_the_source_does_not_hold_is_reported(tmp_path, monkeypatch) -> None:
    docstore = _write(tmp_path / "docstore.json", [{"_id": "p1", "content": "Giỏi: từ 3,20 đến 3,672"}])
    tables = _write(tmp_path / "tables.json", [{
        "table_id": "t", "source_parent_id": "p1",
        "rows": [{"label": "Giỏi", "scholarship_score_range": "3.20-3.60"}],
    }])
    monkeypatch.setattr(audit_extraction, "DOCSTORE", docstore)
    monkeypatch.setattr(audit_extraction, "TABLES", tables)

    found = list(audit_extraction.table_findings())

    assert [(f["column"], f["value"]) for f in found] == [("scholarship_score_range", "3.20-3.60")]
