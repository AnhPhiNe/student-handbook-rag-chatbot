"""Text rules for the handbook texts without articles and for content printed as images."""
import pytest

from src.chunking.image_text import restore_image_text
from src.chunking.supplementary_parents import _is_checkbox_row, _without_qr_pointers


def test_qr_pointer_is_dropped_where_the_sentence_gives_the_link() -> None:
    text = ("Sinh viên truy cập đường dẫn http://tracuu.hcmue.edu.vn/bieumauctsv hoặc quét\n"
            "mã QR kế bên để tìm, đọc và tải.")
    assert _without_qr_pointers(text, [172]) == (
        "Sinh viên truy cập đường dẫn http://tracuu.hcmue.edu.vn/bieumauctsv để tìm, đọc và tải.")
    assert _without_qr_pointers(
        "Sinh viên có thể quét mã QR hoặc truy cập đường link này để đọc", [144],
    ) == "Sinh viên có thể truy cập đường link này để đọc"


def test_qr_only_pointer_becomes_a_page_reference() -> None:
    text = "Sinh viên xem chi tiết Hướng dẫn số 707/HD-ĐHSP bằng cách quét mã QR kế bên."
    assert _without_qr_pointers(text, [156]) == (
        "Sinh viên xem chi tiết Hướng dẫn số 707/HD-ĐHSP qua mã QR in trong Sổ tay sinh viên (trang 156).")


def test_unknown_qr_wording_fails_the_build() -> None:
    with pytest.raises(ValueError, match="Unhandled QR pointer"):
        _without_qr_pointers("Quét mã QR ở cuối trang để xem thêm.", [10])


def test_form_tick_box_row_is_recognised() -> None:
    assert _is_checkbox_row(" ĐẠT LOẠI RÈN LUYỆN: XUẤT SẮC c TỐT c KHÁ c TB c YẾU c KÉM c")
    assert not _is_checkbox_row(" Tổng điểm của phần 1 là 20 điểm, nếu điểm vượt khung thì quy về 20 điểm")


def _parent(content: str) -> dict:
    return {"_id": "p", "content": content, "normalized_content": content}


def test_image_text_goes_in_front_of_its_anchor_once() -> None:
    parents = [_parent("tính theo công thức sau:\nTrong đó:\nA là điểm trung bình chung học kỳ"),
               _parent("Điều khác")]
    restore_image_text(parents, "K51")
    assert parents[0]["content"] == (
        "tính theo công thức sau:\nA = Σ(ai × ni) / Σ(ni)\nTrong đó:\nA là điểm trung bình chung học kỳ")
    assert parents[0]["normalized_content"] == parents[0]["content"]
    restore_image_text(parents, "K51")  # a second run does not insert it twice
    assert parents[0]["content"].count("Σ(ai × ni)") == 1


def test_image_text_fails_when_its_anchor_is_missing() -> None:
    with pytest.raises(ValueError, match="anchor found in 0 parents"):
        restore_image_text([_parent("Điều khác")], "K50")
