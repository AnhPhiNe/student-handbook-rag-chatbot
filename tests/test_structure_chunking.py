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
