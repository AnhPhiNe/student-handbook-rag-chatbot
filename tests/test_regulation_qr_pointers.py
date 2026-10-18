"""A QR pointer wrapped over two PDF lines is removed without cutting the text around it."""
import pytest

from src.chunking.regulation_parents import clean_regulation_source_content


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # Adviser rules Điều 4 (K49 p.62, K50, K51): the pointer used to leave "(xem trong".
        (
            "4. Khung thời gian làm việc được quy định tại Phụ lục 1. (xem trong\n"
            "đường dẫn hoặc mã QR ở cuối Quy định này)\nĐiều 5. Quyền lợi",
            "4. Khung thời gian làm việc được quy định tại Phụ lục 1.\nĐiều 5. Quyền lợi",
        ),
        # Nghị định 116 Điều 7: the second line also holds "theo hình thức nộp", which was lost.
        (
            "đến cơ sở đào tạo giáo viên (Mẫu số 01 – xem\n"
            "trong đường dẫn hoặc mã QR ở cuối Nghị định này) theo hình thức nộp\n"
            "trực tiếp hoặc qua bưu điện",
            "đến cơ sở đào tạo giáo viên (Mẫu số 01) theo hình thức nộp\n"
            "trực tiếp hoặc qua bưu điện",
        ),
        (
            "theo Mẫu số 02 Phụ lục ban hành kèm theo Nghị định 116 (xem trong\n"
            "đường dẫn hoặc mã QR ở cuối Nghị định này) tới Ủy ban nhân dân cấp",
            "theo Mẫu số 02 Phụ lục ban hành kèm theo Nghị định 116 tới Ủy ban nhân dân cấp",
        ),
    ],
)
def test_wrapped_qr_pointer_is_removed_and_the_sentence_kept(source, expected):
    assert clean_regulation_source_content(source) == expected
