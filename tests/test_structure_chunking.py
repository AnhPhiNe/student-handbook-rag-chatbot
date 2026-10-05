"""Structure-aware chunking: a clause keeps its points, the scope removes what it names."""
import json
from pathlib import Path

import pytest

from scripts.structure_chunking import (
    article_units,
    build_structure_chunks,
    load_config,
    load_scope,
    split_segments,
    build_units,
)

PARENTS = json.loads(Path("data/processed/chunks/all_docstore_items.json").read_text(encoding="utf-8"))
BY_ID = {p["_id"]: p for p in PARENTS}


@pytest.fixture(scope="module")
def chunks():
    return build_structure_chunks(PARENTS, config=load_config(), scope=load_scope())


def texts_of(chunks, parent_id):
    return [c["content"] for c in chunks if c["metadata"]["parent_section_id"] == parent_id
            and c["metadata"]["chunk_granularity"] != "section_heading"]


def test_a_point_stays_with_the_sentence_that_says_what_it_is(chunks):
    # The "rớt 3 môn" failure: the condition and the consequence were in two chunks.
    clause = [t for t in texts_of(chunks, "K50_QuyCheDaoTao_Chuong3_Dieu12") if t.startswith("2.")]
    assert len(clause) == 1
    assert "buộc thôi học" in clause[0] and "03 lần liên tiếp" in clause[0] and "lần thứ tư" in clause[0]


def test_every_chunk_names_its_document_and_article_for_embedding_only(chunks):
    child = next(c for c in chunks if c["_id"].startswith("cp_K50_QuyCheDaoTao_Chuong3_Dieu12_u01"))
    header = ("Quy chế đào tạo › Chương III - ĐÁNH GIÁ KẾT QUẢ HỌC TẬP VÀ CẤP BẰNG TỐT NGHIỆP"
              " › Điều 12. Xử lý kết quả học tập đối với hình thức đào tạo chính quy")
    assert child["metadata"]["context_header"] == header
    assert child["embedding_text"] == f"{header}\n{child['content']}"
    assert header not in child["content"]  # the BM25 and display text stay the handbook's words
    assert child["metadata"]["path"] == "Điều 12 › khoản 2"


def test_out_of_scope_articles_get_no_chunk(chunks):
    parents = {c["metadata"]["parent_section_id"] for c in chunks}
    for cohort in ("K48-K49_K48_49_", "K50_", "K51_"):
        assert f"{cohort}QuyCheDaoTao_Chuong3_Dieu13" not in parents
        assert f"{cohort}QuyCheDaoTao_Chuong1_Dieu6" not in parents
    assert "K51_QuyDinhQuyTacUngXu_Chuong2_Dieu5" in parents  # office hours are kept
    assert "K51_QuyDinhQuyTacUngXu_Chuong2_Dieu8" in parents  # conduct toward students is kept
    assert "K51_QuyDinhQuyTacUngXu_Chuong2_Dieu10" not in parents


def test_out_of_scope_points_leave_their_clause_otherwise_intact(chunks):
    for parent in ("K50_QuyCheDaoTao_Chuong1_Dieu3", "K48-K49_K48_49_QuyCheDaoTao_Chuong1_Dieu3"):
        joined = "\n".join(texts_of(chunks, parent))
        assert "hình thức đào tạo chính quy được quy định" in joined
        assert "vừa làm vừa học" not in joined.split("6.", 1)[1]
    k48_forms = "\n".join(texts_of(chunks, "K48-K49_K48_49_QuyCheDaoTao_Chuong1_Dieu5"))
    assert "Đào tạo chính quy" in k48_forms and "Đào tạo vừa làm vừa học" not in k48_forms
    transfer = "\n".join(texts_of(chunks, "K51_QuyCheCongTacSinhVien_Chuong5_Dieu31"))
    assert "cao đẳng sư phạm ngành Giáo dục Mầm non trúng tuyển từ năm 2024" not in transfer
    assert "Buộc thôi học" in transfer  # joint đại học / cao đẳng clauses are kept


def test_parents_are_never_edited():
    before = json.dumps(PARENTS, ensure_ascii=False, sort_keys=True)
    build_structure_chunks(PARENTS, config=load_config(), scope=load_scope())
    assert json.dumps(PARENTS, ensure_ascii=False, sort_keys=True) == before


def test_a_scope_rule_that_matches_nothing_fails_the_build():
    scope = {"exclude_units": [{"parent": "K50_QuyCheDaoTao_Chuong3_Dieu12", "unit": "9"}]}
    with pytest.raises(ValueError, match="match no clause"):
        build_structure_chunks([BY_ID["K50_QuyCheDaoTao_Chuong3_Dieu12"]], config=load_config(), scope=scope)
    with pytest.raises(ValueError, match="unknown parents"):
        build_structure_chunks(PARENTS[:1], config=load_config(), scope={"exclude_parents": [{"id": "nope"}]})


def test_a_long_khoan_is_one_chunk(chunks):
    # The longest khoản, 1.1 to 1.5 of the K48-K49 fee exemptions (about 4,700 characters).
    exempt = [t for t in texts_of(chunks, "K48-K49_ThongBaoMienGiamHocPhi_Phan2") if t.startswith("1. Đối tượng miễn")]
    assert len(exempt) == 1 and all(f"1.{n}." in exempt[0] for n in range(1, 6))
    assert {c["metadata"]["chunk_granularity"] for c in chunks} == {"section_heading", "clause", "article"}


def test_levels_follow_the_order_markers_appear():
    units = build_units(split_segments(
        "− Đào tạo chính quy\na) Giảng dạy tại\ncơ sở của Trường;\nb) Từ 06 giờ.\n− Đào tạo vừa làm vừa học\na) Linh hoạt."))
    assert [u.marker for u in units] == ["−", "−"]
    assert [i.marker for i in units[0].items] == ["a", "b"]
    assert units[0].items[0].text == "a) Giảng dạy tại cơ sở của Trường;"  # wrapped line joined


def test_article_heading_line_is_not_repeated_in_the_text():
    units = article_units(BY_ID["K48-K49_K48_49_QuyCheCongTacSinhVien_Chuong4_Dieu21"])
    assert not units[0].text().startswith("Điều 21")


def test_every_document_title_has_a_short_name():
    config = load_config()
    titles = {(p.get("metadata") or {}).get("document_title") for p in PARENTS}
    rules = [r["prefix"] for r in config["document_short_names"]]
    assert all(any(t.startswith(r) for r in rules) for t in titles)


def test_an_unnumbered_lead_in_keeps_the_list_that_follows_it(chunks):
    # "… gồm các nguồn sau:" then "1. …", "2. …" is one list, not separate clauses.
    funding = texts_of(chunks, "K51_QuyDinhNghienCuuKhoaHocSinhVien_Chuong1_Dieu5")
    assert len(funding) == 1 and funding[0].startswith("Tài chính cho hoạt động NCKH")
    assert "1." in funding[0] and "4." in funding[0]
    hours = texts_of(chunks, "K51_QuyDinhQuyTacUngXu_Chuong2_Dieu5")
    assert len(hours) == 1 and "thời gian làm việc" in hours[0] and "Khối hành chính" in hours[0]
    notice = texts_of(chunks, "K51_ThongBaoHocBongNguoiKhuyetTat_Phan1")
    assert len(notice) == 1 and notice[0].startswith("Về việc thực hiện chế độ") and "5. Thời gian" in notice[0]


@pytest.fixture(scope="module")
def published_chunks():
    from scripts.build_parent_child_artifacts import REGIONS

    reviewed = {e["parent_id"] for e in json.loads(REGIONS.read_text(encoding="utf-8"))["parents"]}
    return build_structure_chunks(PARENTS, config=load_config(), scope=load_scope(), drop_table_parents=reviewed)


def test_the_published_build_holds_every_chunk_invariant(published_chunks):
    from scripts.check_chunk_invariants import check

    assert {k: v for k, v in check(published_chunks, PARENTS, load_scope()).items() if v} == {}


def test_the_invariant_check_catches_a_cut_inside_a_sentence(published_chunks):
    from scripts.check_chunk_invariants import check

    broken = [dict(c) for c in published_chunks]
    victim = next(i for i, c in enumerate(broken) if c["metadata"]["parent_section_id"] == "K50_QuyCheDaoTao_Chuong3_Dieu12"
                  and c["metadata"]["chunk_granularity"] == "clause")
    words = broken[victim]["content"].split(" ")
    broken[victim]["content"] = " ".join(words[: len(words) // 2])
    problems = check(broken, PARENTS, load_scope())
    assert problems["boundary"] and problems["coverage"]


def test_a_long_line_is_cut_only_where_a_sentence_or_list_item_ends(published_chunks):
    # The PDF ran the "miễn 100% học phí" list into one 1,900-character line.
    parts = [c["content"] for c in published_chunks
             if c["metadata"]["parent_section_id"] == "K50_ThongBaoMienGiamHocPhi_Phan4"
             and "Cả cha và mẹ đang trong thời gian" in c["content"]]
    # It was cut as "… đang trong thời gian chấp" | "hành án phạt tù …".
    assert parts and all("Cả cha và mẹ đang trong thời gian chấp hành án phạt tù" in " ".join(p.split()) for p in parts)
    assert len(parts) == 1 and parts[0].startswith("- Đối tượng miễn, giảm học phí")  # with its lead-in


def test_a_heading_wrapped_over_two_lines_is_not_a_chunk(chunks):
    texts = texts_of(chunks, "K48-K49_K48_49_QuyCheDaoTao_Chuong4_Dieu17")
    assert not any(t.startswith("Điều 17") for t in texts)


def test_a_table_column_header_line_goes_with_the_table(published_chunks):
    clause = [c["content"] for c in published_chunks
              if c["metadata"]["parent_section_id"] == "K50_QuyCheDanhGiaKetQuaRenLuyen_Chuong3_Dieu9"]
    assert not any(t.rstrip().endswith("TT") for t in clause)


def test_layout_fixes_say_how_lines_group_without_changing_them():
    # NCKH Điều 7 in configs/layout_fixes.yaml, shortened: a date names the step under it,
    # e) lists publications with the steps' "–", "Xếp loại…" opens a second list.
    text = ("– Các khoa tổ chức hội nghị.\nThang điểm theo các tiêu chí sau:\na) Nội dung (20);\n"
            "e) Có công bố (chọn 01 trong các sản phẩm):\n– Bài báo trong nước;\n– Sáng chế (10).\n"
            "Xếp loại đánh giá đề tài:\na) Hội đồng cho điểm;\nb) Ghi biên bản.\nTháng 6 hằng năm\n"
            "– Sau hội nghị cấp Trường.")
    fixes = [{"line_prefix": "e) Có công bố", "fix": "nested_list", "lines": 2},
             {"line": "Xếp loại đánh giá đề tài:", "fix": "starts_group"},
             {"line": "Tháng 6 hằng năm", "fix": "label_of_next"}]
    plain = build_units(split_segments(text))
    assert [u.marker for u in plain] == ["–", "–", "–", "–"]  # without the fixes the list loses e)
    units = build_units(split_segments(text, fixes))
    assert [u.marker for u in units] == ["–", None, "–"]
    assert units[2].lead_text == "Tháng 6 hằng năm – Sau hội nghị cấp Trường."
    assert [p.text for p in units[0].items[-1].parts][1:] == ["– Bài báo trong nước;", "– Sáng chế (10)."]
    assert units[1].lead_text == "Xếp loại đánh giá đề tài:" and [i.marker for i in units[1].items] == ["a", "b"]


def test_sub_numbered_items_are_their_own_level_and_a_score_is_not_one():
    units = build_units(split_segments(
        "1. Đối tượng miễn học phí\n1.1. Người có công.\n− Thân nhân;\n1.2. Sinh viên khuyết tật.\nHồ sơ:\n• Đơn;"
        "\n2. Đối tượng giảm học phí\na) Điểm trung bình từ\n2.00 trở lên;"))
    assert [i.marker for i in units[0].items] == ["1.1", "1.2"]
    assert units[0].items[1].text == "1.2. Sinh viên khuyết tật. Hồ sơ:\n• Đơn;"
    assert units[1].items[0].text == "a) Điểm trung bình từ 2.00 trở lên;"


def test_capital_letter_sections_head_their_own_lists():
    units = build_units(split_segments(
        "A. Hội đồng gồm:\n1. Phó Hiệu trưởng;\n2. Giám đốc KTX.\n"
        "B. Đối tượng sinh viên được xét theo thứ tự ưu tiên\n1. Anh hùng lực lượng vũ trang;\n2. Sinh viên nữ."))
    assert [u.marker for u in units] == ["A", "B"]  # cited as "khoản B"
    assert units[1].text().startswith("B. Đối tượng") and "Sinh viên nữ" in units[1].text()


def test_a_date_label_goes_with_the_step_it_dates_and_is_never_taken_for_the_heading(published_chunks):
    steps = [c["content"] for c in published_chunks
             if c["metadata"]["parent_section_id"] == "K50_QuyDinhNghienCuuKhoaHocSinhVien_Chuong2_Dieu7"]
    assert any(t.startswith("Tháng 9 – 10 hằng năm – Phòng Khoa học") for t in steps)
    assert any(t.startswith("Tháng 6 hằng năm – Sau Hội nghị") for t in steps)
    assert not any(t.rstrip().endswith("Tháng 6 hằng năm") for t in steps)


def test_a_line_dropped_as_heading_must_be_in_the_stored_title_or_reviewed():
    from scripts.check_chunk_invariants import check

    parent = {"_id": "X_Dieu7", "content": "Nội dung:\nĐiều 7. Quy trình tổ chức hoạt động nghiên\ncứu khoa học\n"
              "Tháng 9 hằng năm\n– Phòng thông báo kế hoạch.",
              "metadata": {"article": "Điều 7.", "title": "Quy trình tổ chức hoạt động nghiên cứu khoa học",
                           "content_type": "regulation_text", "cohort": "K50"}}
    chunk = {"_id": "c", "content": "Tháng 9 hằng năm\n– Phòng thông báo kế hoạch.",
             "metadata": {"parent_section_id": "X_Dieu7", "chunk_granularity": "article"}}
    assert {k: v for k, v in check([chunk], [parent], {}).items() if v} == {}
    lost = {**chunk, "content": "– Phòng thông báo kế hoạch."}
    assert check([lost], [parent], {})["coverage"]


def test_the_heading_chunk_names_the_article_without_a_cut_excerpt(published_chunks):
    heading = next(c for c in published_chunks if c["_id"] == "cp_K50_QuyCheDaoTao_Chuong3_Dieu12_section_heading")
    assert heading["content"].startswith("Section heading: Điều 12. Xử lý kết quả học tập")
    assert "Summary anchor" not in heading["content"]


def test_every_layout_fix_is_used_and_a_stale_one_fails_the_build():
    from scripts.structure_chunking import load_layout_fixes

    fixes = load_layout_fixes()
    assert sum(map(len, fixes.values())) == 24
    assert {f["fix"] for fs in fixes.values() for f in fs} == {
        "heading_tail", "table_header", "label_of_next", "split_items", "nested_list", "starts_group"}
    parent = BY_ID["K50_QuyCheDanhGiaKetQuaRenLuyen_Chuong3_Dieu9"]
    import scripts.structure_chunking as sc

    saved = sc._LAYOUT_FIXES
    sc._LAYOUT_FIXES = {parent["_id"]: [{"parent": parent["_id"], "line": "no such line", "fix": "table_header"}]}
    try:
        with pytest.raises(ValueError, match="layout fixes match no line"):
            article_units(parent)
    finally:
        sc._LAYOUT_FIXES = saved


def test_a_title_the_stored_metadata_cuts_short_is_whole_again_in_both_heading_texts(chunks):
    rows = [c for c in chunks if c["metadata"]["parent_section_id"] == "K50_QuyCheCongTacSinhVien_Chuong4_Dieu17"]
    heading = next(c for c in rows if c["metadata"]["chunk_granularity"] == "section_heading")
    clause = next(c for c in rows if c["metadata"]["chunk_granularity"] != "section_heading")
    assert heading["content"].split("\n", 1)[0].endswith("Hội Sinh viên Việt Nam Trường")
    assert clause["metadata"]["context_header"].endswith("Hội Sinh viên Việt Nam Trường")
    notice = next(c for c in chunks if c["metadata"]["parent_section_id"] == "K50_ThongBaoHoTroChiPhiHocTap_Phan3"
                  and c["metadata"]["chunk_granularity"] != "section_heading")
    assert notice["metadata"]["context_header"].endswith("hỗ trợ chi phí học tập")
