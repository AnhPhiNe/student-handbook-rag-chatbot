from typing import Any


def build_embedding_report(
    model_name: str,
    device: str,
    vectorstore_provider: str,
    persist_dir: str,
    collection_name: str,
    total_chunks: int,
    total_embeddings: int,
    retrieval_tests: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "phase": "phase_6_embedding_and_vectorstore",
        "embedding_model": model_name,
        "device": device,
        "vectorstore_provider": vectorstore_provider,
        "persist_dir": persist_dir,
        "collection_name": collection_name,
        "total_chunks_loaded": total_chunks,
        "total_embeddings_created": total_embeddings,
        "retrieval_tests_count": len(retrieval_tests),
        "retrieval_tests": retrieval_tests,
        "status": "completed",
    }