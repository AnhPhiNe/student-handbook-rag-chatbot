from src.common.text import fold_text, slot_values


def test_fold_text_drops_diacritics_and_keeps_d_stroke() -> None:
    assert fold_text("Điểm TƯƠNG ĐƯƠNG bậc 3") == "diem tuong duong bac 3"


def test_fold_text_keeps_only_requested_punctuation() -> None:
    assert fold_text("IELTS 6,5 / TOEIC", keep="+.,-") == "ielts 6,5 toeic"
    assert fold_text("pdt@hcmue.edu.vn", keep="@._+-") == "pdt@hcmue.edu.vn"
    assert fold_text("pdt@hcmue.edu.vn") == "pdt hcmue edu vn"


def test_slot_values_keeps_lists_and_drops_blanks() -> None:
    assert slot_values(["a", "", None, "b"]) == ["a", "b"]
    assert slot_values("  ") == []
    assert slot_values(3.5) == [3.5]
