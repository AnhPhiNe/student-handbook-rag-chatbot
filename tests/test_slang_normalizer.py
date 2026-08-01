from src.retrieval.core.slang_normalizer import SlangNormalizer


def _write_vocabulary(tmp_path):
    path = tmp_path / "vocabulary.yaml"
    path.write_text(
        """
replace_slangs:
  - match: CNTT
    replace_with: công nghệ thông tin
  - match: GPA
    replace_with: điểm trung bình
expand_slangs:
  - match: học bổng
    expand_with: học bổng khuyến khích học tập
""".strip(),
        encoding="utf-8",
    )
    return path


def test_explicit_acronyms_are_case_insensitive(tmp_path) -> None:
    normalizer = SlangNormalizer(
        _write_vocabulary(tmp_path),
        program_directory=[],
    )

    assert normalizer.normalize("CNTT") == "công nghệ thông tin"
    assert normalizer.normalize("cntt") == "công nghệ thông tin"
    assert normalizer.normalize("Cntt") == "công nghệ thông tin"


def test_router_replacement_does_not_apply_retrieval_expansion(tmp_path) -> None:
    normalizer = SlangNormalizer(
        _write_vocabulary(tmp_path),
        program_directory=[],
    )

    query = "cntt có học bổng không?"

    assert (
        normalizer.replace_for_router(query)
        == "công nghệ thông tin có học bổng không?"
    )
    assert normalizer.normalize_for_retrieval(query) == (
        "công nghệ thông tin có học bổng học bổng khuyến khích học tập không?"
    )


def test_long_replacement_is_protected_from_short_expansion(tmp_path) -> None:
    path = tmp_path / "vocabulary.yaml"
    path.write_text(
        """
replace_slangs:
  - match: học bổng KKHT
    replace_with: học bổng khuyến khích học tập
expand_slangs:
  - match: học bổng
    expand_with: học bổng chính sách học bổng tài trợ
""".strip(),
        encoding="utf-8",
    )
    normalizer = SlangNormalizer(path, program_directory=[])

    normalized = normalizer.normalize_for_retrieval("học bổng KKHT cần gì?")

    assert normalized == "học bổng khuyến khích học tập cần gì?"
    assert "học bổng chính sách" not in normalized


def test_unique_generated_acronyms_are_replaced_case_insensitively(tmp_path) -> None:
    normalizer = SlangNormalizer(
        _write_vocabulary(tmp_path),
        program_directory=[
            {
                "program_name": "Giáo dục Mầm non",
                "faculty_name": "Khoa Giáo dục Mầm non",
            }
        ],
    )

    assert normalizer.normalize("GDMN học gì?") == "giáo dục mầm non học gì?"
    assert normalizer.normalize("gdmn học gì?") == "giáo dục mầm non học gì?"
    assert normalizer.normalize("Gdmn học gì?") == "giáo dục mầm non học gì?"


def test_short_or_ambiguous_generated_acronyms_are_not_replaced(tmp_path) -> None:
    normalizer = SlangNormalizer(
        _write_vocabulary(tmp_path),
        program_directory=[
            {"program_name": "Tiếng Anh"},
            {"program_name": "Sư phạm Tin học"},
            {"program_name": "Sư phạm Toán học"},
        ],
    )

    assert normalizer.normalize("TA") == "TA"
    assert normalizer.normalize("ta") == "ta"
    assert normalizer.normalize("SPTH") == "SPTH"
    assert normalizer.normalize("spth") == "spth"


def test_replacement_only_matches_complete_token(tmp_path) -> None:
    normalizer = SlangNormalizer(
        _write_vocabulary(tmp_path),
        program_directory=[],
    )

    assert normalizer.normalize("cnttt") == "cnttt"
    assert normalizer.normalize("học cntt") == "học công nghệ thông tin"


def test_graduation_rank_slang_adds_regulation_anchor() -> None:
    normalizer = SlangNormalizer(program_directory=[])

    router_query = normalizer.replace_for_router(
        "học lại hay học cải thiện mới bị hạ bằng"
    )
    normalized = normalizer.normalize_for_retrieval(
        "học lại hay học cải thiện mới bị hạ bằng"
    )

    assert "hạ bằng" not in router_query
    assert "hạng tốt nghiệp bị giảm đi một mức" in router_query
    assert "hạ bằng" not in normalized
    assert "tiếp nhận trở lại học" not in normalized
    assert "hạng tốt nghiệp bị giảm đi một mức" in normalized
    assert "công nhận tốt nghiệp và cấp bằng tốt nghiệp" in normalized


def test_ambiguous_slangs_expand_but_do_not_replace_for_router() -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router("thi bù") == "thi bù"
    assert normalizer.replace_for_router("chuyển khoa") == "chuyển khoa"
    assert normalizer.replace_for_router("gap year") == "gap year"
    assert normalizer.replace_for_router("treo học") == "treo học"
    assert normalizer.replace_for_router("dính biên bản") == "dính biên bản"
    assert normalizer.replace_for_router("học lại sau bảo lưu") == (
        "học lại sau bảo lưu"
    )

    assert "kỳ thi phụ" in normalizer.normalize_for_retrieval("thi bù")
    assert "chuyển chương trình đào tạo" in normalizer.normalize_for_retrieval(
        "chuyển khoa"
    )
    assert "bảo lưu kết quả học tập" in normalizer.normalize_for_retrieval("gap year")
    assert "đình chỉ học tập có thời hạn" in normalizer.normalize_for_retrieval(
        "treo học"
    )
    assert "kỷ luật cảnh cáo" in normalizer.normalize_for_retrieval("dính biên bản")


def test_form_is_not_canonicalized_in_runtime_slang() -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router("form xác nhận sinh viên") == (
        "form xác nhận sinh viên"
    )
