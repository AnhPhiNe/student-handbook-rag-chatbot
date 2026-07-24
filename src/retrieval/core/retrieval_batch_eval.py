from pathlib import Path

from src.common.console import configure_utf8_stdio

from .io_utils import load_json, load_yaml, save_json
from .report_builder import build_retrieval_report
from .hybrid_pipeline import run_hybrid_retrieval_pipeline
from .vector_retriever import get_chroma_collection, load_embedding_model


CONFIG_PATH = Path("configs/retrieval.yaml")

TEST_QUERIES = [
    # =========================
    # A. Regulation / học vụ
    # =========================
    "Nếu bị điểm F thì sao?",
    "Sinh viên bị cảnh báo học tập khi nào vậy?",
    "Điểm D có được tính đạt không?",
    "Muốn học vượt thì cần điều kiện gì?",
    "Một học phần có thể học lại mấy lần?",
    "Nếu nghỉ học quá lâu thì có bị thôi học không?",
    "Sinh viên có được đăng ký học lại để cải thiện điểm không?",
    "Bao nhiêu tín chỉ thì bị chậm tiến độ?",
    "Điểm trung bình tích lũy dùng để làm gì?",
    "Khi nào thì bị xóa tên khỏi danh sách sinh viên?",
    # =========================
    # B. Lookup / scoring
    # =========================
    "Điểm rèn luyện 92 là loại gì?",
    "GPA 2.95 được xếp loại học lực gì?",
    "Điểm B+ quy đổi sang hệ 4 bao nhiêu?",
    "Điểm chữ C tương đương mấy điểm?",
    "Rèn luyện 49 có bị yếu không?",
    "Điểm học bổng tính kiểu gì?",
    "GPA 1.9 có bị cảnh báo không?",
    "3.6 GPA là xuất sắc hay giỏi?",
    "Điểm A có tương đương 4.0 không?",
    "Rèn luyện 75 là khá hay tốt?",
    # =========================
    # C. Form queries
    # =========================
    "Muốn quay lại học sau bảo lưu thì dùng đơn gì?",
    "Có mẫu đơn xin trợ cấp xã hội không?",
    "Mẫu đơn xin ở ký túc xá nằm ở đâu?",
    "Biểu mẫu miễn giảm học phí gồm gì?",
    "Muốn xác nhận sinh viên để vay vốn thì làm giấy nào?",
    "Đơn xin thôi học cần khai thông tin gì?",
    "Muốn xin chuyển trường thì dùng biểu mẫu nào?",
    "Có phiếu theo dõi tiến độ học tập không?",
    "Đơn học lại yêu cầu thông tin gì?",
    "Muốn xin hỗ trợ chi phí học tập thì điền mẫu gì?",
    # =========================
    # D. Office queries
    # =========================
    "Email phòng đào tạo là gì?",
    "Phòng CTCT-HSSV ở tầng mấy?",
    "Muốn hỏi về học phí thì liên hệ đơn vị nào?",
    "Website phòng CNTT là gì?",
    "Số điện thoại phòng Sau đại học bao nhiêu?",
    "Phòng nào phụ trách ký túc xá?",
    "Liên hệ học vụ ở đâu?",
    "Đơn vị nào xử lý công tác sinh viên?",
    "Phòng Kế hoạch – Tài chính làm gì?",
    "Muốn giải quyết giấy tờ sinh viên thì tìm ai?",
    # =========================
    # E. Faculty queries
    # =========================
    "Khoa CNTT đào tạo gì?",
    "Ngành Công nghệ thông tin học xong làm nghề gì?",
    "Khoa Tiếng Pháp nằm ở đâu?",
    "Khoa Sinh học có nghiên cứu không?",
    "Ngành Vật lí sau này làm gì?",
    "Khoa Toán – Tin học có email không?",
    "Khoa Hóa học đào tạo những gì?",
    "Ngành tiếng Anh ra trường có thể làm gì?",
    "Khoa Địa lí có website không?",
    "Tổ trực thuộc nào liên quan công nghệ?",
    # =========================
    # F. Procedure / KTX
    # =========================
    "Ai được ưu tiên vào ký túc xá?",
    "Quy trình xét KTX gồm những bước nào?",
    "Muốn ở nội trú thì làm sao?",
    "Hội đồng xét KTX gồm ai?",
    "Sinh viên nữ có được ưu tiên KTX không?",
    "Điều kiện để vào ký túc xá là gì?",
    "Có cần nộp đơn để xét KTX không?",
    "KTX xét theo tiêu chí nào?",
    "Thủ tục vào ở nội trú như thế nào?",
    "Con hộ nghèo có ưu tiên KTX không?",
    # =========================
    # G. Mixed / khó hơn
    # =========================
    "Muốn bảo lưu thì vừa cần điều kiện gì vừa cần mẫu đơn nào?",
    "Nếu GPA thấp thì còn được học bổng không?",
    "Muốn xin vào KTX thì liên hệ phòng nào và dùng mẫu gì?",
    "Nếu bị cảnh báo học tập thì có bị thôi học không?",
    "Muốn chuyển trường thì cần biểu mẫu gì và quy định ra sao?",
    "Nếu nghỉ tạm thời xong thì làm sao học lại?",
    "Muốn miễn giảm học phí thì liên hệ ai?",
    "Nếu rớt môn thì học lại bằng cách nào?",
    "Muốn vay vốn sinh viên thì cần giấy xác nhận gì?",
    "Muốn giải quyết học vụ và xin học lại thì phải làm gì?",
]


def simplify_result(result: dict) -> dict:
    """
    Rút gọn result để dễ đọc report.
    Có giữ thêm retrieval_query, detected_entities, retrieval_plan và rerank score
    để debug Retrieval chính xác hơn.
    """
    retrieved_items = result.get("retrieved_items", [])

    top_items = []
    for item in retrieved_items[:3]:
        metadata = item.get("metadata", {})

        top_items.append(
            {
                "chunk_id": item.get("chunk_id"),
                "distance": item.get("distance"),
                "rerank": item.get("rerank"),
                "retrieval_purpose": item.get("retrieval_purpose"),
                "chunk_type": metadata.get("chunk_type"),
                "title": (
                    metadata.get("title")
                    or metadata.get("form_name")
                    or metadata.get("unit_name")
                    or metadata.get("faculty_or_unit_name")
                    or metadata.get("procedure_name")
                ),
                "source_pages": metadata.get("source_pages"),
                "preview": item.get("content", "")[:250],
            }
        )

    return {
        "query": result.get("query"),
        "retrieval_query": result.get("retrieval_query"),
        "detected_entities": result.get("detected_entities"),
        "intent": result.get("intent"),
        "strategy": result.get("strategy"),
        "target_chunk_types": result.get("target_chunk_types"),
        "retrieval_plan": result.get("retrieval_plan"),
        "structured_result": result.get("structured_result"),
        "tool_result": result.get("tool_result"),
        "top_items": top_items,
        "citations": result.get("citations", [])[:3],
        "has_context": bool(result.get("context_for_llm")),
        "context_preview": result.get("context_for_llm", "")[:500],
    }


def main() -> None:
    configure_utf8_stdio()

    config = load_yaml(CONFIG_PATH)

    entity_registry = load_json(Path(config["input"]["entity_registry"]))
    expansion_rules = load_json(Path(config["input"]["query_expansion_rules"]))

    scoring_tables = load_json(Path(config["input"]["scoring_tables"]))
    formula_rules = load_json(Path(config["input"]["formula_rules"]))
    student_service_path = config["input"].get("student_service_directory")
    student_service_directory = (
        load_json(Path(student_service_path)) if student_service_path else []
    )
    foreign_language_path = config["input"].get("foreign_language_equivalency_table")
    foreign_language_tables = (
        load_json(Path(foreign_language_path)) if foreign_language_path else []
    )
    structured_tables_path = config["input"].get("structured_tables_registry")
    structured_tables_registry = (
        load_json(Path(structured_tables_path)) if structured_tables_path else []
    )
    program_directory = load_json(Path(config["input"]["program_directory"]))

    model = load_embedding_model(config["embedding"]["model_name"])
    collection = get_chroma_collection(
        persist_dir=config["vectorstore"]["persist_dir"],
        collection_name=config["vectorstore"]["collection_name"],
    )

    full_results = []
    simplified_results = []

    for idx, query in enumerate(TEST_QUERIES, start=1):
        print("=" * 80)
        print(f"[{idx}/{len(TEST_QUERIES)}] Query: {query}")

        result = run_hybrid_retrieval_pipeline(
            query=query,
            model=model,
            collection=collection,
            scoring_tables=scoring_tables,
            formula_rules=formula_rules,
            student_service_directory=student_service_directory,
            foreign_language_tables=foreign_language_tables,
            structured_tables_registry=structured_tables_registry,
            program_directory=program_directory,
            top_k=config["retrieval"]["default_top_k"],
            batch_size=config["embedding"]["batch_size"],
            entity_registry=entity_registry,
            expansion_rules=expansion_rules,
            normalize_embeddings=config["embedding"]["normalize_embeddings"],
            candidate_multiplier=config["retrieval"].get("candidate_multiplier", 5),
            min_candidates=config["retrieval"].get("min_candidates", 25),
        )

        simple = simplify_result(result)

        print("Intent:", simple["intent"])
        print("Strategy:", simple["strategy"])
        print("Has context:", simple["has_context"])

        if simple["structured_result"]:
            print("Structured result:", simple["structured_result"])

        if simple["tool_result"]:
            print("Tool result:", simple["tool_result"])

        if simple["top_items"]:
            print(
                "Top 1:",
                simple["top_items"][0]["chunk_id"],
                "|",
                simple["top_items"][0]["title"],
            )

        full_results.append(result)
        simplified_results.append(simple)

    report = build_retrieval_report(full_results)

    output_dir = Path("data/processed/metadata")
    save_json(report, output_dir / "retrieval_batch_eval_full.json")
    save_json(simplified_results, output_dir / "retrieval_batch_eval_simplified.json")

    print("\nRetrieval batch evaluation completed.")
    print(f"Total queries: {len(TEST_QUERIES)}")
    print("Saved full report: data/processed/metadata/retrieval_batch_eval_full.json")
    print(
        "Saved simplified report: data/processed/metadata/retrieval_batch_eval_simplified.json"
    )


if __name__ == "__main__":
    main()
