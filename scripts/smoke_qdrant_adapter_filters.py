from __future__ import annotations

import json
import sys
from pathlib import Path

from qdrant_client.models import FieldCondition, Filter, MatchValue
from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.env_loader import load_project_env
from src.retrieval.core.retrieval_pipeline import content_types_for_chunk_types
from src.retrieval.core.vector_retriever import vector_search
from src.retrieval.vectorstore.vectorstore_factory import create_collection


TESTS = [
    {
        "name": "regulation",
        "query": "điều kiện xét tốt nghiệp là gì",
        "chunk_types": ["regulation"],
        "allowed_content_types": {"regulation", "regulation_sections", "regulation_text"},
    },
    {
        "name": "office",
        "query": "phòng công nghệ thông tin email ở đâu",
        "chunk_types": ["office_directory"],
        "allowed_content_types": {
            "office_directory",
            "student_office_profile",
            "student_service_directory",
        },
    },
    {
        "name": "form",
        "query": "mẫu đơn tạm nghỉ học",
        "chunk_types": ["form"],
        "allowed_content_types": {"form", "form_template"},
    },
    {
        "name": "structured",
        "query": "IELTS 5.5 tương đương bậc mấy",
        "chunk_types": ["structured_lookup"],
        "allowed_content_types": {
            "foreign_language_equivalency",
            "scoring_table",
            "structured_lookup",
            "threshold_rule",
        },
    },
]

REMOVED_KTX_PARENT_ID = (
    "K50_NghiDinhHoTroHocPhiSinhHoatPhiSinhVienSuPham_"
    "Chuong4_Dieu15_Supplement_04"
)


def main() -> None:
    load_project_env()
    model = SentenceTransformer("BAAI/bge-m3")
    collection = create_collection(
        "data/processed/chroma",
        "student_handbook_semantic_v7",
    )

    failures: list[str] = []
    local_chunks = json.loads(
        (PROJECT_ROOT / "data/processed/chunks/v7_child_parent_chunks.json").read_text(
            encoding="utf-8"
        )
    )
    remote_count = collection.client.count(
        collection_name=collection.collection_name,
        exact=True,
    ).count
    if remote_count != len(local_chunks):
        failures.append(
            f"collection count mismatch: remote={remote_count}, local={len(local_chunks)}"
        )

    removed_ktx_count = collection.client.count(
        collection_name=collection.collection_name,
        count_filter=Filter(
            must=[
                FieldCondition(
                    key="parent_section_id",
                    match=MatchValue(value=REMOVED_KTX_PARENT_ID),
                )
            ]
        ),
        exact=True,
    ).count
    if removed_ktx_count:
        failures.append(f"removed KTX supplement still has {removed_ktx_count} points")
    print(
        f"collection_count: remote={remote_count}, local={len(local_chunks)}; "
        f"removed_ktx_points={removed_ktx_count}"
    )

    for test in TESTS:
        chunk_types = test["chunk_types"]
        expected_content_types = set(content_types_for_chunk_types(chunk_types))
        if expected_content_types != test["allowed_content_types"]:
            failures.append(
                f"{test['name']}: mapping mismatch {sorted(expected_content_types)}"
            )
            continue

        results = vector_search(
            test["query"],
            model,
            collection,
            chunk_types=chunk_types,
            content_types=sorted(expected_content_types),
            top_k=5,
            batch_size=8,
            cohort="K50",
        )
        rows = []
        for result in results:
            metadata = result.get("metadata") or {}
            content_type = metadata.get("content_type")
            cohort = metadata.get("cohort")
            parent_id = metadata.get("parent_section_id")
            rows.append(
                {
                    "content_type": content_type,
                    "cohort": cohort,
                    "parent_section_id": parent_id,
                }
            )
            if content_type not in expected_content_types:
                failures.append(
                    f"{test['name']}: unexpected content_type {content_type!r}"
                )
            if cohort != "K50":
                failures.append(f"{test['name']}: unexpected cohort {cohort!r}")

        print(f"{test['name']}: {rows}")

    if failures:
        print("FAILURES:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)

    print("smoke_qdrant_adapter_filters: OK")


if __name__ == "__main__":
    main()
