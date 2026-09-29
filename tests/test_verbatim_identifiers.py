"""Identifiers in an answer are checked against the evidence and corrected when unambiguous."""
import json

from src.generation.answer_pipeline import STREAM_OUTPUT_GUARDRAIL_BUFFER_CHARS, StreamAnswerCleaner
from src.generation.verbatim_identifiers import IdentifierCorrector

EVIDENCE = json.dumps({"units": [{"primary_evidence": [{"content": (
    "Khoa Tiếng Anh: khoatienganh@hcmue.edu.vn, khoaanh.hcmue.edu.vn, (028) 38352020, "
    "nội bộ 102. Nhà B, P.506. Nghị định 116/2016/NĐ-CP."
)}]}]})  # ensure_ascii: "Đ" arrives escaped


def test_identifiers_found_in_the_evidence_are_kept():
    text = ("Email khoatienganh@hcmue.edu.vn, web https://khoaanh.hcmue.edu.vn/, "
            "điện thoại (028) 3835 2020, phòng P. 506, Nghị định 116/2016/NĐ-CP.")
    assert IdentifierCorrector(EVIDENCE).fix(text) == text


def test_a_near_miss_with_one_candidate_is_corrected():
    fix = IdentifierCorrector(EVIDENCE).fix
    assert fix("Email khotienganh@hcmue.edu.vn nhé.") == "Email khoatienganh@hcmue.edu.vn nhé."
    assert fix("Gọi (028) 38352021.") == "Gọi (028) 38352020."
    assert fix("Xem khoaan.hcmue.edu.vn") == "Xem khoaanh.hcmue.edu.vn"


def test_two_swapped_neighbouring_characters_count_as_one_edit():
    fix = IdentifierCorrector(EVIDENCE).fix
    assert fix("Gọi (028) 38352002.") == "Gọi (028) 38352020."           # "20" typed as "02"
    assert fix("Email khoatieganhn@hcmue.edu.vn") == "Email khoatienganh@hcmue.edu.vn"
    # Two separate wrong digits are still more than a phone number's one edit.
    assert fix("Gọi (028) 38352911.") == "Gọi (028) 38352911."


def test_an_identifier_with_no_single_near_match_is_left_alone():
    two = IdentifierCorrector("a1@hcmue.edu.vn và a2@hcmue.edu.vn").fix
    assert two("Email a3@hcmue.edu.vn") == "Email a3@hcmue.edu.vn"
    assert IdentifierCorrector(EVIDENCE).fix("Email phongdaotao@gmail.com") == "Email phongdaotao@gmail.com"


def test_the_question_counts_as_evidence():
    question = "Em gửi mail từ sv123@student.hcmue.edu.vn có được không?"
    text = "Được, em dùng sv123@student.hcmue.edu.vn."
    assert IdentifierCorrector(EVIDENCE, question).fix(text) == text


def test_a_stream_releases_whole_words_so_identifiers_are_corrected():
    cleaner = StreamAnswerCleaner(fix=IdentifierCorrector(EVIDENCE).fix)
    text = "a" * (STREAM_OUTPUT_GUARDRAIL_BUFFER_CHARS - 20) + " liên hệ khotienganh@hcmue.edu.vn " + "b " * 200
    shown = [piece for i in range(0, len(text), 7) if (piece := cleaner.feed(text[i:i + 7]))]
    if tail := cleaner.finish():
        shown.append(tail)
    joined = "".join(shown)
    assert "khoatienganh@hcmue.edu.vn" in joined and "khotienganh" not in joined
    assert all(piece.endswith((" ", "\n")) for piece in shown[:-1])
