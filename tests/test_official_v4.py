import json

from scripts.build_v4_cases import V4, build, clusters


def test_frozen_case_file_matches_its_sources():
    committed = json.loads((V4 / "generated_answer_cases.json").read_text(encoding="utf-8"))
    assert committed == build()


def test_clusters_join_near_duplicate_facts_only():
    same = ["thời gian học tập tối đa là 8 năm học đối với chính quy"]
    other = ["email của Khoa Vật lý là khoavatly@hcmue.edu.vn"]
    result = clusters({"a": same, "b": same, "c": other})
    assert result["a"] == result["b"] != result["c"]
