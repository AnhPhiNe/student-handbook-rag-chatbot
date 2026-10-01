"""Addresses are read under every label the handbook uses for them."""
from scripts.build_structured_table_layer import extract_office


def test_the_three_address_labels_and_their_wrapped_lines() -> None:
    assert extract_office(
        "Email\n: a@hcmue.edu.vn\nVăn phòng làm việc : Nhà B, tầng 5,\nP.501, số 280 An Dương Vương.\n"
        "Những công việc của đơn vị liên quan đến sinh viên:"
    ) == "Nhà B, tầng 5, P.501, số 280 An Dương Vương."
    # K48-K49 and K50 label some units "Phòng làm việc", with the value on the next lines.
    assert extract_office(
        "Website\n: x.hcmue.edu.vn\nPhòng làm việc\n:\nDãy nhà B, tầng 6, P.601\nsố 280 An Dương Vương.\n"
        "Những công việc của đơn vị liên quan đến sinh viên:"
    ) == "Dãy nhà B, tầng 6, P.601 số 280 An Dương Vương."


def test_a_registration_desk_and_a_working_office_are_both_kept_and_named() -> None:
    assert extract_office(
        "Văn phòng ghi danh\n: 221 Nguyễn Văn Cừ, Phường 4.\nPhòng làm việc\n:\nDãy A, tầng trệt, P.004\n"
        "Những công việc của đơn vị liên quan đến sinh viên:"
    ) == "Văn phòng ghi danh: 221 Nguyễn Văn Cừ, Phường 4.; Phòng làm việc: Dãy A, tầng trệt, P.004"


def test_sub_units_name_their_own_addresses_and_do_not_leak_into_each_other() -> None:
    text = (
        "21. Đoàn Thanh niên và Hội Sinh viên Trường\n+ Văn phòng Đoàn Thanh niên:\nEmail\n: d@hcmue.edu.vn\n"
        "Phòng làm việc\n: Nhà A, P.001.\n+ Văn phòng Hội Sinh viên:\nEmail\n: h@hcmue.edu.vn\n"
        "Phòng làm việc\n: Nhà A, P.002."
    )
    assert extract_office(text) == (
        "Văn phòng Đoàn Thanh niên – Phòng làm việc: Nhà A, P.001.; "
        "Văn phòng Hội Sinh viên – Phòng làm việc: Nhà A, P.002."
    )


def test_no_label_means_no_address() -> None:
    assert extract_office("Email\n: a@hcmue.edu.vn\nĐiện thoại liên lạc\n: (028) 38352020") == ""


def test_a_faculty_is_not_given_its_programs_career_lines_as_duties() -> None:
    import json
    from pathlib import Path

    from src.retrieval.core.office_lookup import _summarize_office

    root = Path(__file__).resolve().parents[1]
    faculty = json.loads((root / "data/processed/directories/student_faculty_profiles.json").read_text(encoding="utf-8"))
    with_careers = [f for f in faculty if "Cơ hội nghề nghiệp" in str(f.get("raw_text") or "")]
    assert with_careers, "fixture premise: some faculty entries carry their programs' career text"
    assert all(not _summarize_office(f).get("responsibilities") for f in with_careers)
