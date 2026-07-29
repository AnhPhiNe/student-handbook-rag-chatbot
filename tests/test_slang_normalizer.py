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
