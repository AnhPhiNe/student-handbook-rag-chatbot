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


def _write_empty_vocabulary(tmp_path):
    path = tmp_path / "empty-vocabulary.yaml"
    path.write_text("replace_slangs: []\nexpand_slangs: []\n", encoding="utf-8")
    return path


def _write_unit_aliases(tmp_path):
    path = tmp_path / "unit-aliases.yaml"
    path.write_text(
        """
unit_aliases:
  Phòng Đào tạo: [PĐT, PDT]
  Phòng Công tác chính trị và Học sinh, sinh viên: [CTCT-HSSV, CTCT&HSSV, CTCT/HSSV, HSSV, Phòng Công tác sinh viên]
  Phòng Công nghệ Thông tin: [CNTT]
  Khoa Công nghệ Thông tin: [CNTT]
""".strip(),
        encoding="utf-8",
    )
    return path


def test_explicit_acronyms_are_case_insensitive(tmp_path) -> None:
    normalizer = SlangNormalizer(
        _write_vocabulary(tmp_path),
        program_directory=[],
    )

    assert normalizer.normalize_for_retrieval("CNTT") == "công nghệ thông tin"
    assert normalizer.normalize_for_retrieval("cntt") == "công nghệ thông tin"
    assert normalizer.normalize_for_retrieval("Cntt") == "công nghệ thông tin"


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

    assert normalizer.normalize_for_retrieval("GDMN học gì?") == "giáo dục mầm non học gì?"
    assert normalizer.normalize_for_retrieval("gdmn học gì?") == "giáo dục mầm non học gì?"
    assert normalizer.normalize_for_retrieval("Gdmn học gì?") == "giáo dục mầm non học gì?"


def test_short_or_ambiguous_generated_acronyms_are_not_replaced(tmp_path) -> None:
    normalizer = SlangNormalizer(
        _write_vocabulary(tmp_path),
        program_directory=[
            {"program_name": "Tiếng Anh"},
            {"program_name": "Sư phạm Tin học"},
            {"program_name": "Sư phạm Toán học"},
        ],
    )

    assert normalizer.normalize_for_retrieval("TA") == "TA"
    assert normalizer.normalize_for_retrieval("ta") == "ta"
    assert normalizer.normalize_for_retrieval("SPTH") == "SPTH"
    assert normalizer.normalize_for_retrieval("spth") == "spth"


def test_replacement_only_matches_complete_token(tmp_path) -> None:
    normalizer = SlangNormalizer(
        _write_vocabulary(tmp_path),
        program_directory=[],
    )

    assert normalizer.normalize_for_retrieval("cnttt") == "cnttt"
    assert normalizer.normalize_for_retrieval("học cntt") == "học công nghệ thông tin"


def test_unique_directory_aliases_are_canonicalized_before_routing(tmp_path) -> None:
    normalizer = SlangNormalizer(
        _write_empty_vocabulary(tmp_path),
        program_directory=[],
        unit_alias_config_path=_write_unit_aliases(tmp_path),
    )

    canonical = "phòng công tác chính trị và học sinh, sinh viên"
    assert normalizer.replace_for_router("Phòng CTCT-HSSV nằm ở đâu?") == (
        f"{canonical} nằm ở đâu?"
    )
    assert normalizer.replace_for_router("Phòng CTCT&HSSV nằm ở đâu?") == (
        f"{canonical} nằm ở đâu?"
    )
    assert normalizer.replace_for_router("Phòng CTCT/HSSV nằm ở đâu?") == (
        f"{canonical} nằm ở đâu?"
    )
    assert normalizer.replace_for_router("phòng công tác sinh viên ở đâu?") == (
        f"{canonical} ở đâu?"
    )
    assert normalizer.replace_for_router("số điện thoại PDT") == (
        "số điện thoại phòng đào tạo"
    )


def test_ambiguous_directory_alias_is_not_canonicalized(tmp_path) -> None:
    normalizer = SlangNormalizer(
        _write_empty_vocabulary(tmp_path),
        program_directory=[],
        unit_alias_config_path=_write_unit_aliases(tmp_path),
    )

    assert normalizer.replace_for_router("CNTT ở đâu?") == "CNTT ở đâu?"


def test_short_alias_is_not_replaced_inside_unregistered_compound(tmp_path) -> None:
    vocabulary = tmp_path / "compound-vocabulary.yaml"
    vocabulary.write_text(
        """
replace_slangs:
  - match: HSSV
    replace_with: học sinh, sinh viên
expand_slangs: []
""".strip(),
        encoding="utf-8",
    )
    normalizer = SlangNormalizer(
        vocabulary,
        program_directory=[],
        unit_alias_config_path=None,
    )

    for compound in ("CTCT-HSSV", "CTCT&HSSV", "CTCT/HSSV"):
        assert normalizer.replace_for_router(compound) == compound
    assert normalizer.replace_for_router("HSSV") == "học sinh, sinh viên"


def test_phone_abbreviation_is_canonicalized_for_router() -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router("sdt của phòng đào tạo") == (
        "số điện thoại của phòng đào tạo"
    )
    assert normalizer.replace_for_router("SĐT của phòng đào tạo") == (
        "số điện thoại của phòng đào tạo"
    )


def test_graduation_rank_slang_only_canonicalizes_the_user_term() -> None:
    normalizer = SlangNormalizer(program_directory=[])

    router_query = normalizer.replace_for_router(
        "học lại hay học cải thiện mới bị hạ bằng"
    )
    normalized = normalizer.normalize_for_retrieval(
        "học lại hay học cải thiện mới bị hạ bằng"
    )

    assert "hạ bằng" not in router_query
    assert "giảm một mức xếp loại tốt nghiệp" in router_query
    assert "hạ bằng" not in normalized
    assert "tiếp nhận trở lại học" not in normalized
    assert "giảm một mức xếp loại tốt nghiệp" in normalized
    assert "khối lượng tín chỉ học lại vượt quá 5%" not in normalized
    assert "kỷ luật cảnh cáo trở lên" not in normalized
    assert "công nhận tốt nghiệp và cấp bằng tốt nghiệp" not in normalized


def test_accentless_slangs_use_same_canonical_mappings() -> None:
    normalizer = SlangNormalizer(program_directory=[])

    router_query = normalizer.replace_for_router(
        "K50 hoc lai hay hoc cai thien moi bi ha bang?"
    )
    normalized = normalizer.normalize_for_retrieval(
        "K50 hoc lai hay hoc cai thien moi bi ha bang?"
    )

    assert "ha bang" not in router_query
    assert "giảm một mức xếp loại tốt nghiệp" in router_query
    assert "khối lượng tín chỉ học lại vượt quá 5%" not in normalized
    assert "kỷ luật cảnh cáo trở lên" not in normalized
    assert "học phần đã đạt đăng ký học lại để cải thiện điểm" in normalized
    assert "học phần chưa đạt phải học lại" in normalized


def test_program_acronym_replacement_handles_lowercase_user_input() -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router("nganh cntt o khoa nao") == (
        "nganh công nghệ thông tin o khoa nao"
    )


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
