import json
from pathlib import Path


FORMS_PATH = Path("data/processed/forms/form_templates.json")
OFFICE_PATH = Path("data/processed/directories/office_directory.json")
FACULTY_PATH = Path("data/processed/directories/faculty_program_directory.json")


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_no_bullet_records(office, faculty):
    print("\n===== TEST 1: NO BULLET RECORDS =====")

    bad_office = [
        item for item in office
        if item["unit_name"].startswith(("–", "-", "−", "+"))
    ]

    bad_faculty = [
        item for item in faculty
        if item["faculty_or_unit_name"].startswith(("–", "-", "−", "+"))
    ]

    print("Bad office records:", len(bad_office))
    print("Bad faculty records:", len(bad_faculty))

    assert len(bad_office) == 0, "Office directory still has bullet records"
    assert len(bad_faculty) == 0, "Faculty directory still has bullet records"

    print("PASS ✅")


def test_source_pages_exist(forms, office, faculty):
    print("\n===== TEST 2: SOURCE PAGES EXIST =====")

    bad_items = []

    for dataset in [forms, office, faculty]:
        for item in dataset:
            if not item.get("source_pages"):
                bad_items.append(item)

    print("Items missing source_pages:", len(bad_items))

    assert len(bad_items) == 0, "Some items missing source_pages"

    print("PASS ✅")


def test_required_forms_exist(forms):
    print("\n===== TEST 3: REQUIRED FORMS EXIST =====")

    required_forms = [
        "ĐƠN XIN TẠM NGHỈ HỌC",
        "ĐƠN XIN HỌC LẠI",
        "ĐƠN XIN THÔI HỌC",
        "ĐƠN XIN VÀO Ở KÝ TÚC XÁ",
        "GIẤY XÁC NHẬN",
    ]

    for form_name in required_forms:
        found = any(form_name in form["form_name"] for form in forms)

        print(f"{form_name}: {found}")

        assert found, f"Missing form: {form_name}"

    print("PASS ✅")


def main():
    forms = load_json(FORMS_PATH)
    office = load_json(OFFICE_PATH)
    faculty = load_json(FACULTY_PATH)

    test_no_bullet_records(office, faculty)
    test_source_pages_exist(forms, office, faculty)
    test_required_forms_exist(forms)

    print("\n🎉 ALL PHASE 4 VALIDATIONS PASSED")


if __name__ == "__main__":
    main()