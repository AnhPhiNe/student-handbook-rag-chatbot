from __future__ import annotations

import unittest

from src.ui.streamlit.clarification_handler import _looks_like_new_question


class ClarificationHandlerTest(unittest.TestCase):
    def test_short_clarification_fragment_is_not_new_question(self) -> None:
        self.assertFalse(_looks_like_new_question("Phòng CNTT"))
        self.assertFalse(_looks_like_new_question("Khoa Công nghệ thông tin"))

    def test_full_followup_question_is_treated_as_new_question(self) -> None:
        self.assertTrue(_looks_like_new_question("cong thuc tinh diem gpa la gi"))
        self.assertTrue(_looks_like_new_question("Email Phòng Đào tạo là gì?"))
        self.assertTrue(_looks_like_new_question("Điều kiện xét học bổng là gì"))


if __name__ == "__main__":
    unittest.main()
