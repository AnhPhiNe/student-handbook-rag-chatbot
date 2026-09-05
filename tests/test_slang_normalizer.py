import pytest

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


def test_academic_warning_acronym_is_canonicalized_for_router() -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router("các lý do dẫn đến cbht") == (
        "các lý do dẫn đến cảnh báo học tập"
    )
    assert normalizer.replace_for_router("CBHT do đâu?") == (
        "cảnh báo học tập do đâu?"
    )


@pytest.mark.parametrize(
    ("acronym", "expected"),
    [
        ("BCH", "Ban Chấp hành"),
        ("BCS", "Ban Cán sự"),
        ("CTĐT", "chương trình đào tạo"),
        ("CTCT&HSSV", "Công tác chính trị và Học sinh, sinh viên"),
        ("CTCT và HSSV", "Công tác chính trị và Học sinh, sinh viên"),
        ("CVHT", "cố vấn học tập"),
        ("ĐH", "đại học"),
        ("CĐ", "cao đẳng"),
        ("TCCN", "trung cấp chuyên nghiệp"),
        ("HBKKHT", "học bổng khuyến khích học tập"),
        ("HSSV", "học sinh, sinh viên"),
        ("KTX", "ký túc xá"),
        ("NCKH", "nghiên cứu khoa học"),
        ("NVSP", "nghiệp vụ sư phạm"),
        ("TNCS", "Thanh niên Cộng sản"),
        ("TBC", "trung bình cộng"),
        ("THCS", "trung học cơ sở"),
        ("THPT", "trung học phổ thông"),
    ],
)
def test_handbook_front_matter_acronyms_are_canonicalized(
    acronym: str,
    expected: str,
) -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router(acronym).casefold() == expected.casefold()


@pytest.mark.parametrize(
    ("acronym", "expected"),
    [
        ("KH&CN", "khoa học và công nghệ"),
        ("ĐHCQ", "đại học chính quy"),
    ],
)
def test_defined_body_acronyms_are_canonicalized(
    acronym: str,
    expected: str,
) -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router(acronym) == expected


@pytest.mark.parametrize(
    "legal_reference",
    [
        "1410/QĐ-ĐHSP",
        "81/2021/NĐ-CP",
        "35/2014/TTLT-BGDĐT-BTC",
    ],
)
def test_legal_reference_acronyms_remain_literal(legal_reference: str) -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router(legal_reference) == legal_reference


def test_generic_gpa_is_preserved_for_router_and_expanded_for_retrieval() -> None:
    normalizer = SlangNormalizer(program_directory=[])
    query = "hai kỳ liên tiếp GPA và điểm rèn luyện xuất sắc"

    router_query = normalizer.replace_for_router(query)
    retrieval_query = normalizer.normalize_for_retrieval(query)

    assert router_query == query
    assert "GPA" in retrieval_query
    assert "điểm trung bình học kỳ hoặc điểm trung bình tích lũy" in retrieval_query


def test_explicit_gpa_scope_keeps_existing_canonical_replacement() -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router("GPA học kỳ") == (
        "điểm trung bình chung học kỳ"
    )
    assert normalizer.replace_for_router("GPA tích lũy") == (
        "điểm trung bình chung tích lũy"
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
    assert "học lại học phần đã đạt" in normalized
    assert "học phần không đạt phải học lại" in normalized


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
    discipline_query = normalizer.normalize_for_retrieval("dính biên bản")
    assert "bị lập biên bản vi phạm" in discipline_query
    assert "cảnh cáo" not in discipline_query


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (
            "Học cải thiện tính điểm thế nào?",
            "học lại học phần đã đạt tính điểm thế nào?",
        ),
        (
            "hoc cai thien tinh diem the nao?",
            "học lại học phần đã đạt tinh diem the nao?",
        ),
        (
            "học cải thiện môn có bị hạ bằng không?",
            "học lại học phần đã đạt để cải thiện điểm có bị giảm một mức "
            "xếp loại tốt nghiệp không?",
        ),
    ],
)
def test_improvement_study_is_canonicalized_before_routing(
    query: str,
    expected: str,
) -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router(query) == expected
    assert normalizer.normalize_for_retrieval(query) == expected


@pytest.mark.parametrize(
    ("query", "original_term", "expected_expansion"),
    [
        ("kéo điểm bằng cách nào?", "kéo điểm", "nâng điểm trung bình"),
        ("gỡ điểm bằng cách nào?", "gỡ điểm", "nâng điểm trung bình"),
        ("điểm phẩy được tính sao?", "điểm phẩy", "điểm số thập phân"),
        (
            "nợ ngoại ngữ có tốt nghiệp được không?",
            "nợ ngoại ngữ",
            "chưa đạt chuẩn đầu ra ngoại ngữ",
        ),
        (
            "nợ tin học có tốt nghiệp được không?",
            "nợ tin học",
            "chưa hoàn thành học phần tin học",
        ),
        (
            "học bổng khuyến học cần điều kiện gì?",
            "học bổng khuyến học",
            "học bổng tài trợ",
        ),
        (
            "xin xem lại điểm ở đâu?",
            "xin xem lại điểm",
            "phúc khảo điểm thi kết thúc học phần",
        ),
        (
            "coi lại bài thi bằng cách nào?",
            "coi lại bài thi",
            "kiểm tra lại điểm học phần",
        ),
        (
            "chấm lại mất bao lâu?",
            "chấm lại",
            "phúc khảo điểm thi kết thúc học phần",
        ),
    ],
)
def test_ambiguous_handbook_terms_only_expand_retrieval(
    query: str,
    original_term: str,
    expected_expansion: str,
) -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router(query) == query
    retrieval_query = normalizer.normalize_for_retrieval(query)
    assert original_term in retrieval_query
    assert expected_expansion in retrieval_query


@pytest.mark.parametrize(
    ("query", "expected_expansion", "forbidden_assumption"),
    [
        (
            "học lại môn",
            "học phần không đạt phải học lại hoặc học phần đạt được học lại để "
            "cải thiện điểm",
            None,
        ),
        (
            "nợ môn",
            "học phần chưa hoàn thành hoặc học phần chưa đạt",
            None,
        ),
        (
            "nợ tín chỉ",
            "chưa tích lũy đủ tín chỉ hoặc tín chỉ nợ đọng",
            None,
        ),
        (
            "điểm cuối kỳ",
            "điểm thi kết thúc học phần hoặc điểm học phần",
            "điểm trung bình học kỳ",
        ),
        ("bỏ thi", "vắng mặt trong buổi thi", "không có lý do chính đáng"),
        (
            "dính biên bản",
            "bị lập biên bản vi phạm hoặc bị xem xét xử lý kỷ luật",
            "cảnh cáo",
        ),
        ("HP", "học phần hoặc học phí", None),
    ],
)
def test_ambiguous_terms_do_not_force_one_meaning_before_planning(
    query: str,
    expected_expansion: str,
    forbidden_assumption: str | None,
) -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router(query) == query
    retrieval_query = normalizer.normalize_for_retrieval(query)
    assert query in retrieval_query
    assert expected_expansion in retrieval_query
    if forbidden_assumption is not None:
        assert forbidden_assumption not in retrieval_query


def test_official_failed_course_term_is_not_reexpanded() -> None:
    normalizer = SlangNormalizer(program_directory=[])
    query = "học phần chưa đạt"

    assert normalizer.replace_for_router(query) == query
    assert normalizer.normalize_for_retrieval(query) == query


def test_academic_warning_alias_uses_official_handbook_term() -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router("warning học vụ") == "cảnh báo học tập"
    assert normalizer.replace_for_router("cảnh báo học vụ") == "cảnh báo học tập"


def test_specific_improvement_phrase_is_replaced_before_shorter_phrase() -> None:
    normalizer = SlangNormalizer(program_directory=[])

    normalized = normalizer.replace_for_router("học cải thiện điểm")
    assert normalized == "học lại học phần đã đạt để cải thiện điểm"
    assert "điểm điểm" not in normalized


@pytest.mark.parametrize(
    "query",
    [
        "skip tiết một buổi bị sao?",
        "nghỉ chui một buổi bị sao?",
        "trốn học một buổi bị sao?",
        "cúp học một buổi bị sao?",
        "bỏ tiết một buổi bị sao?",
        "nghi chui mot buoi bi sao?",
        "tron hoc mot buoi bi sao?",
        "cup hoc mot buoi bi sao?",
        "bo tiet mot buoi bi sao?",
    ],
)
def test_session_absence_slang_is_not_rewritten_as_abandoning_study(
    query: str,
) -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router(query) == query
    assert normalizer.normalize_for_retrieval(query) == query
    assert "tự ý bỏ học" not in normalizer.normalize_for_retrieval(query)


def test_generic_unexcused_absence_is_not_narrowed_to_exam_or_study_status() -> None:
    normalizer = SlangNormalizer(program_directory=[])
    query = "vắng không phép thì bị xử lý thế nào?"

    assert normalizer.replace_for_router(query) == query
    assert normalizer.normalize_for_retrieval(query) == query
    assert "buổi thi" not in normalizer.normalize_for_retrieval(query)
    assert "tự ý bỏ học" not in normalizer.normalize_for_retrieval(query)


@pytest.mark.parametrize(
    "query",
    [
        "học kỳ hè kéo dài bao lâu?",
        "xin nghỉ học một buổi thì sao?",
        "bỏ học một buổi có bị trừ điểm không?",
        "buộc thôi học khi nào?",
        "học bổng khuyến khích học tập cần điều kiện gì?",
    ],
)
def test_official_or_ambiguous_terms_are_not_overexpanded(query: str) -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router(query) == query
    assert normalizer.normalize_for_retrieval(query) == query


@pytest.mark.parametrize(
    ("query", "expected_expansion"),
    [
        (
            "học quá hạn có bị đuổi học không?",
            "thời gian học tập vượt quá giới hạn tối đa",
        ),
        (
            "điểm kỳ này được tính thế nào?",
            "điểm thi kết thúc học phần",
        ),
    ],
)
def test_ambiguous_time_and_grade_terms_only_expand_retrieval(
    query: str,
    expected_expansion: str,
) -> None:
    normalizer = SlangNormalizer(program_directory=[])

    router_query = normalizer.replace_for_router(query)
    retrieval_query = normalizer.normalize_for_retrieval(query)

    expected_router_query = query.replace("bị đuổi học", "buộc thôi học")
    assert router_query == expected_router_query
    assert expected_expansion in retrieval_query


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("có bị đuổi học không?", "có buộc thôi học không?"),
        ("trường có đuổi học không?", "trường có buộc thôi học không?"),
    ],
)
def test_dismissal_slang_is_canonicalized_before_routing(
    query: str,
    expected: str,
) -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router(query) == expected
    assert normalizer.normalize_for_retrieval(query) == expected


def test_generic_failure_slang_only_expands_retrieval() -> None:
    normalizer = SlangNormalizer(program_directory=[])
    query = "thi rớt 3 môn có bị đuổi học?"

    router_query = normalizer.replace_for_router(query)
    retrieval_query = normalizer.normalize_for_retrieval(query)

    assert router_query == "thi rớt 3 môn có buộc thôi học?"
    assert "rớt không đạt" in retrieval_query
    assert "buộc thôi học" in retrieval_query


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (
            "Nợ môn Thể chất có xét tốt nghiệp?",
            "chưa hoàn thành học phần giáo dục thể chất có xét tốt nghiệp?",
        ),
        (
            "nợ môn GDTC có tốt nghiệp được không?",
            "chưa hoàn thành học phần giáo dục thể chất có tốt nghiệp được không?",
        ),
        (
            "nợ môn quốc phòng có tốt nghiệp được không?",
            "chưa hoàn thành học phần giáo dục quốc phòng và an ninh có tốt nghiệp "
            "được không?",
        ),
        (
            "nợ môn GDQP có được ra trường?",
            "chưa hoàn thành học phần giáo dục quốc phòng và an ninh có được tốt "
            "nghiệp?",
        ),
    ],
)
def test_required_subject_debt_uses_handbook_course_names(
    query: str,
    expected: str,
) -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router(query) == expected


@pytest.mark.parametrize(
    ("query", "expected_fragment"),
    [
        ("rớt môn thì học lại sao?", "học phần chưa đạt"),
        ("đăng ký rớt thì xử lý sao?", "đăng ký học phần không thành công"),
        (
            "rớt bằng vì học lại?",
            "không được công nhận tốt nghiệp hoặc bị giảm một mức xếp loại tốt nghiệp",
        ),
    ],
)
def test_specific_failure_slang_keeps_its_more_precise_mapping(
    query: str,
    expected_fragment: str,
) -> None:
    normalizer = SlangNormalizer(program_directory=[])
    retrieval_query = normalizer.normalize_for_retrieval(query)

    assert expected_fragment in retrieval_query
    assert "rớt không đạt" not in retrieval_query


def test_unsupported_exam_ban_phrase_is_not_given_an_invented_policy_mapping() -> None:
    normalizer = SlangNormalizer(program_directory=[])
    query = "đóng học phí trễ có bị cấm thi không?"

    assert normalizer.replace_for_router(query) == query
    assert "cấm thi" in normalizer.normalize_for_retrieval(query)
    assert "không được dự thi" not in normalizer.normalize_for_retrieval(query)


@pytest.mark.parametrize(
    "query",
    [
        "chuẩn đầu ra là gì?",
        "chuẩn đầu ra của ngành được công bố ở đâu?",
        "chuan dau ra cua nganh la gi?",
    ],
)
def test_generic_output_standard_is_not_narrowed_to_specific_requirements(
    query: str,
) -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router(query) == query
    assert normalizer.normalize_for_retrieval(query) == query


def test_runtime_slang_categories_do_not_overlap() -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_dict.keys().isdisjoint(normalizer.expand_dict.keys())


def test_form_is_not_canonicalized_in_runtime_slang() -> None:
    normalizer = SlangNormalizer(program_directory=[])

    assert normalizer.replace_for_router("form xác nhận sinh viên") == (
        "form xác nhận sinh viên"
    )
