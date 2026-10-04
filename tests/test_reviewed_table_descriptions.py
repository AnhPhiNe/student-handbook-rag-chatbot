"""Frozen source-reviewed text changes discovery, never metadata or table facts."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts.build_table_search_candidate import ROOT, apply_reviewed_descriptions, build_candidate
from src.retrieval.core.bm25_retriever import BM25Retriever
from src.retrieval.core.table_search import VERSION, build_table_descriptions, raw_table_for_handle, table_key

REVIEW = ROOT / "configs/table_search_descriptions.yaml"


def reviewed_sources():
    manifest = json.loads((ROOT / "data/processed/metadata/build_manifest.json").read_text(encoding="utf-8"))
    tables, parents = [json.loads((ROOT / manifest["artifacts"][name]["path"]).read_text(encoding="utf-8"))
                       for name in ("structured_tables", "parent_docstore")]
    hashes = {name: manifest["artifacts"][name]["sha256"] for name in ("structured_tables", "parent_docstore")}
    baseline = build_table_descriptions(tables, parents)
    reviewed, provenance = apply_reviewed_descriptions(baseline, REVIEW, hashes)
    return tables, baseline, reviewed, provenance, hashes


def test_all_35_descriptions_preserve_identity_metadata_and_raw_tables():
    tables, baseline, reviewed, provenance, _ = reviewed_sources()
    assert len(reviewed) == 35
    assert len({h["content"] for h in reviewed}) == 35
    assert provenance["version"] == "table-description-reviewed-v2"
    assert provenance["sha256"] == hashlib.sha256(REVIEW.read_bytes()).hexdigest()
    catalog = {table_key(t): t for t in tables}
    for old, new in zip(baseline, reviewed):
        restored = copy.deepcopy(new)
        restored["content"] = old["content"]
        restored["metadata"]["description_version"] = VERSION
        assert restored == old
        assert raw_table_for_handle(new, catalog, new["metadata"]["cohort"]) == catalog[new["metadata"]["table_search_key"]]
        assert 2 <= new["content"].count(".") <= 4
        assert "275" not in new["content"]  # thresholds belong only to raw evidence
        assert "scholarship_level" not in new["content"]
        assert "equivalent_level" not in new["content"]


def test_source_specific_scopes_scales_and_scholarship_shapes():
    _, _, handles, _, _ = reviewed_sources()
    def content(cohort, suffix):
        return next(h["content"] for h in handles if h["metadata"]["cohort"] == cohort
                    and json.loads(h["metadata"]["table_search_key"])[2].endswith(suffix))
    for cohort in ("K48-K49", "K50", "K51"):
        assert "không tính" in content(cohort, "pass_fail_ungraded")
        assert "thang 10" in content(cohort, "pass_fail_ungraded")
        assert "thang 4" in content(cohort, "scholarship_score_formula")
        assert "thang 100" in content(cohort, "scholarship_score_formula")
    assert "giáo dục đại cương" in content("K51", "grade_scale_foundation")
    assert "còn lại ngoài nhóm nền tảng" in content("K51", "grade_scale_remaining")
    assert "tổ hợp xếp loại học tập" in content("K51", "scholarship_classification")
    assert "khoảng điểm học bổng" in content("K50", "scholarship_classification")
    foreign = content("K50", "foreign_language_equivalency_dieu8")
    assert "4 kỹ năng" in foreign and "điểm từng kỹ năng" in foreign
    assert "không tự xác lập TOEIC" in foreign and "Điều 1" in foreign


@pytest.mark.parametrize("cohort", ["K48-K49", "K50", "K51"])
@pytest.mark.parametrize("mode,query", [("chinh_quy", "hình thức đào tạo chính quy"),
                                      ("vua_lam_vua_hoc", "hình thức đào tạo vừa làm vừa học VLVH")])
def test_duration_descriptions_distinguish_training_mode_in_same_parent(cohort, mode, query):
    _, _, handles, _, _ = reviewed_sources()
    retriever = BM25Retriever()
    # Six duration-only documents give mode tokens zero IDF (three of six).
    # Keep the entire description corpus when comparing the two same-parent tables.
    retriever.build_bm25_index(handles)
    hits = [h for h in retriever.sparse_search(query, top_k=35, cohort=cohort)
            if "study_duration" in h["metadata"]["table_search_key"]]
    assert len(hits) == 2
    assert json.loads(hits[0]["metadata"]["table_search_key"])[2].endswith(f"study_duration_{mode}")
    assert hits[0]["metadata"]["parent_section_id"] == hits[1]["metadata"]["parent_section_id"]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown", "metadata", "empty", "stale_tables", "stale_parents"])
def test_review_document_rejects_partial_stale_or_metadata_overrides(tmp_path, mutation):
    _, baseline, _, _, hashes = reviewed_sources()
    review = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))
    if mutation == "missing":
        review["descriptions"].pop()
    elif mutation == "duplicate":
        review["descriptions"].append(copy.deepcopy(review["descriptions"][0]))
    elif mutation == "unknown":
        review["descriptions"][0]["key"] = '["K99","wrong","wrong"]'
    elif mutation == "metadata":
        review["descriptions"][0]["applicable_cohorts"] = ["K51"]
    elif mutation == "empty":
        review["descriptions"][0]["content"] = " "
    else:
        review["source_hashes"]["structured_tables" if mutation == "stale_tables" else "parent_docstore"] = "stale"
    path = tmp_path / "review.yaml"
    path.write_text(yaml.safe_dump(review, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError):
        apply_reviewed_descriptions(baseline, path, hashes)


def test_reviewed_candidate_has_separate_namespace_and_text_hash_identity(tmp_path):
    baseline = build_candidate(ROOT, tmp_path / "metadata_v1")
    preserved = {p: p.read_bytes() for p in (tmp_path / "metadata_v1").iterdir()}
    with pytest.raises(FileExistsError):
        build_candidate(ROOT, tmp_path / "metadata_v1", REVIEW)
    assert {p: p.read_bytes() for p in preserved} == preserved
    reviewed = build_candidate(ROOT, tmp_path / "reviewed_v2", REVIEW)
    assert baseline["storage_targets"] != reviewed["storage_targets"]
    assert reviewed["artifacts"]["table_descriptions"]["count"] == 35
    assert reviewed["artifacts"]["child_chunks"]["count"] == 3835
    assert reviewed["parent_source"] == baseline["parent_source"]
    assert not reviewed["embedding_created"] and reviewed["model_calls"] == 0
    changed = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))
    changed["descriptions"][0]["content"] += " Nguồn tham chiếu."
    changed_path = tmp_path / "changed.yaml"
    changed_path.write_text(yaml.safe_dump(changed, allow_unicode=True), encoding="utf-8")
    other = build_candidate(ROOT, tmp_path / "changed", changed_path)
    assert other["storage_targets"] != reviewed["storage_targets"]
    handles = json.loads(Path(reviewed["artifacts"]["table_descriptions"]["path"]).read_text(encoding="utf-8"))
    combined = json.loads(Path(reviewed["artifacts"]["child_chunks"]["path"]).read_text(encoding="utf-8"))
    source = json.loads((ROOT / "data/processed/chunks/child_parent_chunks.json").read_text(encoding="utf-8"))
    assert combined == source + handles


def test_partially_populated_output_cannot_be_overwritten(tmp_path):
    target = tmp_path / "retrieval.yaml"
    target.write_text("preserve me", encoding="utf-8")
    with pytest.raises(FileExistsError):
        build_candidate(ROOT, tmp_path, REVIEW)
    assert target.read_text(encoding="utf-8") == "preserve me"
