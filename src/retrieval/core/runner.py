from pathlib import Path

from src.common.console import configure_utf8_stdio

from .io_utils import load_json, load_yaml, save_json
from .report_builder import build_retrieval_report
from .retrieval_pipeline import run_retrieval_pipeline
from .vector_retriever import get_chroma_collection, load_embedding_model


CONFIG_PATH = Path("configs/retrieval.yaml")


TEST_QUERIES = [
    "Điều kiện xét học bổng là gì?",
    "Muốn tạm nghỉ học cần mẫu đơn nào?",
    "Phòng Đào tạo xử lý việc gì?",
    "Email Phòng Công tác chính trị và HSSV là gì?",
    "Khoa Công nghệ thông tin có ngành nào?",
    "Quy trình vào ký túc xá như thế nào?",
    "Điểm rèn luyện 85 là loại gì?",
    "GPA 3.4 là loại học lực gì?",
    "Điểm A quy đổi sang thang điểm 4 là bao nhiêu?",
    "Tính điểm học bổng nếu điểm học tập 3.4 và điểm rèn luyện 85",
]


def main() -> None:
    configure_utf8_stdio()

    config = load_yaml(CONFIG_PATH)

    entity_registry = load_json(Path(config["input"]["entity_registry"]))
    expansion_rules = load_json(Path(config["input"]["query_expansion_rules"]))

    scoring_tables = load_json(Path(config["input"]["scoring_tables"]))
    formula_rules = load_json(Path(config["input"]["formula_rules"]))
    form_templates = load_json(Path(config["input"]["form_templates"]))
    program_directory = load_json(Path(config["input"]["program_directory"]))

    model = load_embedding_model(config["embedding"]["model_name"])
    collection = get_chroma_collection(
        persist_dir=config["vectorstore"]["persist_dir"],
        collection_name=config["vectorstore"]["collection_name"],
    )

    results = []

    for query in TEST_QUERIES:
        result = run_retrieval_pipeline(
            query=query,
            model=model,
            collection=collection,
            scoring_tables=scoring_tables,
            formula_rules=formula_rules,
            form_templates=form_templates,
            program_directory=program_directory,
            top_k=config["retrieval"]["default_top_k"],
            batch_size=config["embedding"]["batch_size"],
            normalize_embeddings=config["embedding"]["normalize_embeddings"],
            entity_registry=entity_registry,
            expansion_rules=expansion_rules,
        )

        results.append(result)

        print("=" * 80)
        print("Query:", query)
        print("Intent:", result["intent"])
        print("Strategy:", result["strategy"])
        print("Citations:", result["citations"][:2])
        print("Context preview:", result["context_for_llm"][:500])

    report = build_retrieval_report(results)
    save_json(report, Path(config["output"]["test_report"]))

    print("\nRetrieval completed.")
    print(f"Test queries: {len(results)}")
    print(f"Report saved: {config['output']['test_report']}")


if __name__ == "__main__":
    main()
