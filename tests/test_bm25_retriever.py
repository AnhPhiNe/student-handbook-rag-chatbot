from src.retrieval.core.bm25_retriever import BM25Retriever


def _chunk(
    chunk_id: str,
    content: str,
    *,
    cohort: str,
    content_type: str = "regulation_text",
    chunk_type: str = "regulation",
) -> dict:
    return {
        "chunk_id": chunk_id,
        "content": content,
        "metadata": {
            "cohort": cohort,
            "content_type": content_type,
            "chunk_type": chunk_type,
        },
    }


def test_sparse_search_filters_before_applying_top_k(monkeypatch) -> None:
    retriever = BM25Retriever()
    wrong_cohort = _chunk("wrong-cohort", "hoc bong hoc tap", cohort="K50")
    expected = _chunk("expected", "hoc bong khuyen khich hoc tap", cohort="K51")
    wrong_type = _chunk(
        "wrong-type",
        "hoc bong hoc tap",
        cohort="K51",
        content_type="student_office_profile",
        chunk_type="office_directory",
    )
    retriever.chunks = [wrong_cohort, expected, wrong_type]
    monkeypatch.setattr(
        retriever,
        "search_bm25",
        lambda query, top_k: [
            (3.0, wrong_cohort),
            (2.0, expected),
            (1.0, wrong_type),
        ],
    )

    results = retriever.sparse_search(
        "hoc bong hoc tap",
        top_k=1,
        chunk_types=["regulation"],
        content_types=["regulation_text"],
        cohort="K51",
    )

    assert [item["chunk_id"] for item in results] == ["expected"]
    assert results[0]["bm25_score"] > 0


def test_sparse_search_returns_empty_for_unbuilt_index() -> None:
    retriever = BM25Retriever()

    assert retriever.sparse_search("hoc bong", top_k=5) == []


def test_acronym_registry_merges_config_and_directory(tmp_path) -> None:
    vocabulary_path = tmp_path / "query_vocabulary.yaml"
    vocabulary_path.write_text(
        """
replace_slangs:
  - match: CTCT&HSSV
    replace_with: Công tác chính trị và Học sinh, sinh viên
  - match: KTX
    replace_with: ký túc xá
  - match: GPA
    replace_with: điểm trung bình
  - match: hoc phi
    replace_with: học phí
""".strip(),
        encoding="utf-8",
    )
    directory_path = tmp_path / "program_directory.json"
    directory_path.write_text(
        """
[
  {
    "program_name": "Sư phạm Tin học",
    "faculty_name": "Khoa Công nghệ Thông tin"
  },
  {
    "program_name": "Giáo dục Mầm non (trình độ đại học)",
    "faculty_name": "Khoa Giáo dục Mầm non"
  },
  {
    "program_name": "Tiếng Anh",
    "faculty_name": "Khoa Ngoại ngữ"
  }
]
""".strip(),
        encoding="utf-8",
    )

    retriever = BM25Retriever(
        vocabulary_path=vocabulary_path,
        program_directory_path=directory_path,
    )

    assert {"CTCT", "HSSV", "CTCTHSSV", "KTX"} <= retriever.acronym_whitelist
    assert {"SPTH", "CNTT", "GDMN"} <= retriever.acronym_whitelist
    assert "GPA" in retriever.acronym_whitelist
    assert "HOCPHI" not in retriever.acronym_whitelist
    assert retriever._is_known_acronym_token("TA")
    assert not retriever._is_known_acronym_token("ta")
    assert retriever._is_known_acronym_token("ktx")


def test_acronym_registry_is_empty_when_sources_are_missing(tmp_path) -> None:
    retriever = BM25Retriever(
        vocabulary_path=tmp_path / "missing.yaml",
        program_directory_path=tmp_path / "missing.json",
    )

    assert retriever.acronym_whitelist == set()


def test_tokenize_preserves_configured_acronyms(tmp_path) -> None:
    vocabulary_path = tmp_path / "query_vocabulary.yaml"
    vocabulary_path.write_text(
        """
replace_slangs:
  - match: CTCT&HSSV
    replace_with: Công tác chính trị và Học sinh, sinh viên
""".strip(),
        encoding="utf-8",
    )

    retriever = BM25Retriever(
        vocabulary_path=vocabulary_path,
        program_directory_path=tmp_path / "missing.json",
    )

    tokens = retriever._tokenize("Liên hệ CTCT&HSSV")

    assert "ctcthssv" in tokens


def test_bm25_matches_full_name_from_safe_generated_acronym(tmp_path) -> None:
    vocabulary_path = tmp_path / "query_vocabulary.yaml"
    vocabulary_path.write_text("replace_slangs: []", encoding="utf-8")
    directory_path = tmp_path / "program_directory.json"
    directory_path.write_text(
        """
[
  {
    "program_name": "Giáo dục Mầm non",
    "faculty_name": "Khoa Giáo dục Mầm non"
  }
]
""".strip(),
        encoding="utf-8",
    )
    retriever = BM25Retriever(
        vocabulary_path=vocabulary_path,
        program_directory_path=directory_path,
    )
    expected = _chunk(
        "expected",
        "Ngành Giáo dục Mầm non đào tạo giáo viên.",
        cohort="K51",
    )
    retriever.build_bm25_index(
        [
            expected,
            _chunk("other-1", "Quy định học phí sinh viên.", cohort="K51"),
            _chunk("other-2", "Thông tin ký túc xá.", cohort="K51"),
        ]
    )

    results = retriever.search_bm25("gdmn", top_k=3)

    assert results
    assert results[0][1]["chunk_id"] == "expected"
