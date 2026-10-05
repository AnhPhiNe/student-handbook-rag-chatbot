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


def test_long_clauses_are_split_with_their_lead_in(chunks):
    config = load_config()
    sizes = [len(c["content"]) for c in chunks if c["metadata"]["chunk_granularity"] != "section_heading"]
    assert max(sizes) < 1.1 * config["max_unit_chars"]
    parts = [c for c in chunks if c["metadata"]["chunk_granularity"] == "clause_part"
             and c["metadata"]["parent_section_id"] == "K48-K49_ThongBaoMienGiamHocPhi_Phan2"]
    assert len(parts) >= 2
    leads = {p["content"].split("\n", 1)[0] for p in parts}
    assert len(leads) == 1  # every part repeats the clause's lead-in


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
    # The first group keeps the notice's whole opening; later groups repeat only
    # the clause that introduces the list, not the notice's legal bases.
    long_list = texts_of(chunks, "K51_ThongBaoHocBongNguoiKhuyetTat_Phan1")
    assert len(long_list) >= 3 and long_list[0].startswith("Về việc thực hiện chế độ")
    carried = {t.split("\n", 1)[0] for t in long_list[1:]}
    assert len(carried) == 1 and next(iter(carried)).endswith("cụ thể như sau:")
    assert all(len(t.split("\n", 1)[0]) <= 300 for t in long_list[1:])


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
    assert all(p.startswith("- Đối tượng miễn, giảm học phí") for p in parts)  # each group keeps its lead-in


def test_a_heading_wrapped_over_two_lines_is_not_a_chunk(chunks):
    texts = texts_of(chunks, "K48-K49_K48_49_QuyCheDaoTao_Chuong4_Dieu17")
    assert not any(t.startswith("Điều 17") for t in texts)


def test_a_table_column_header_line_goes_with_the_table(published_chunks):
    clause = [c["content"] for c in published_chunks
              if c["metadata"]["parent_section_id"] == "K50_QuyCheDanhGiaKetQuaRenLuyen_Chuong3_Dieu9"]
    assert not any(t.rstrip().endswith("TT") for t in clause)


def test_a_list_reusing_the_clause_marker_stays_with_its_point():
    units = build_units(split_segments(
        "– Các khoa tổ chức hội nghị.\nThang điểm theo các tiêu chí sau:\na) Nội dung (20);\n"
        "e) Có công bố (chọn 01 trong các sản phẩm):\n– Bài báo trong nước;\n– Sáng chế (10).\n"
        "Xếp loại đánh giá đề tài:\na) Hội đồng cho điểm;\nb) Ghi biên bản.\n– Sau hội nghị cấp Trường."))
    assert [u.marker for u in units] == ["–", None, "–"]
    assert [p.text for p in units[0].items[-1].parts][1:] == ["– Bài báo trong nước;", "– Sáng chế (10)."]
    assert units[1].lead_text == "Xếp loại đánh giá đề tài:" and [i.marker for i in units[1].items] == ["a", "b"]


def test_sub_numbered_items_are_their_own_level_and_a_score_is_not_one():
    units = build_units(split_segments(
        "1. Đối tượng miễn học phí\n1.1. Người có công.\n− Thân nhân;\n1.2. Sinh viên khuyết tật.\nHồ sơ:\n• Đơn;"
        "\n2. Đối tượng giảm học phí\na) Điểm trung bình từ\n2.00 trở lên;"))
    assert [i.marker for i in units[0].items] == ["1.1", "1.2"]
    assert units[0].items[1].text == "1.2. Sinh viên khuyết tật.\nHồ sơ:\n• Đơn;"
    assert units[1].items[0].text == "a) Điểm trung bình từ 2.00 trở lên;"


def test_a_carried_lead_in_starts_at_the_main_clause():
    lead = ("Thực hiện Nghị định số 28/2012/NĐ-CP; Thông tư liên tịch số 42/2013 của Bộ Giáo dục và Đào tạo, "
            "Bộ Lao động – Thương binh và Xã hội, Bộ Tài chính về việc quy định chính sách về giáo dục đối với "
            "người khuyết tật, Trường thông báo thực hiện chế độ chính sách về học bổng đối với sinh viên chính "
            "quy là người khuyết tật thuộc hộ nghèo, cận nghèo, cụ thể như sau:")
    from scripts.structure_chunking import _carried_lead

    assert _carried_lead(lead, 300).startswith("Trường thông báo")


def test_capital_letter_sections_head_their_own_lists():
    units = build_units(split_segments(
        "A. Hội đồng gồm:\n1. Phó Hiệu trưởng;\n2. Giám đốc KTX.\n"
        "B. Đối tượng sinh viên được xét theo thứ tự ưu tiên\n1. Anh hùng lực lượng vũ trang;\n2. Sinh viên nữ."))
    assert [u.marker for u in units] == ["a", "b"]
    assert units[1].text().startswith("B. Đối tượng") and "Sinh viên nữ" in units[1].text()
