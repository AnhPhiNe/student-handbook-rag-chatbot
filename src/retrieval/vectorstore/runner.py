from pathlib import Path

from .chroma_store import (
    add_embeddings_to_collection,
    get_chroma_client,
    get_or_create_collection,
)
from .embedding_model import encode_texts, get_device, load_embedding_model
from .io_utils import load_json, load_yaml, save_json
from .metadata_utils import prepare_chroma_payload
from .report_builder import build_embedding_report
from .retrieval_tester import run_sample_retrieval_tests


CONFIG_PATH = Path("configs/embedding.yaml")


def validate_semantic_chunks(chunks: list[dict]) -> None:
    bad_chunks = []
    metadata_issues = []
    seen_ids: set[str] = set()

    for chunk in chunks:
        chunk_id = chunk.get("chunk_id")
        if not chunk_id:
            metadata_issues.append({"issue": "missing_chunk_id", "chunk": chunk})
        elif chunk_id in seen_ids:
            metadata_issues.append({"issue": "duplicate_chunk_id", "chunk_id": chunk_id})
        else:
            seen_ids.add(chunk_id)

        if chunk.get("index_mode") != "semantic":
            bad_chunks.append(chunk_id)

        metadata = chunk.get("metadata") or {}
        cohort = metadata.get("cohort")
        document_id = metadata.get("document_id")
        content_type = metadata.get("content_type") or chunk.get("chunk_type")
        if cohort not in {"K48-K49", "K50-K51"}:
            metadata_issues.append(
                {"issue": "invalid_cohort", "chunk_id": chunk_id, "cohort": cohort}
            )
        if not document_id:
            metadata_issues.append(
                {"issue": "missing_document_id", "chunk_id": chunk_id}
            )
        if not content_type:
            metadata_issues.append(
                {"issue": "missing_content_type", "chunk_id": chunk_id}
            )

    if bad_chunks:
        raise ValueError(
            f"Found non-semantic chunks in embedding input: {bad_chunks[:10]}"
        )
    if metadata_issues:
        raise ValueError(
            f"Invalid semantic chunk metadata: {metadata_issues[:20]}"
        )


def main() -> None:
    config = load_yaml(CONFIG_PATH)

    chunks_path = Path(config["input"]["semantic_chunks"])
    chunks = load_json(chunks_path)

    validate_semantic_chunks(chunks)

    model_name = config["embedding"]["model_name"]
    batch_size = config["embedding"]["batch_size"]
    normalize_embeddings = config["embedding"]["normalize_embeddings"]

    persist_dir = config["vectorstore"]["persist_dir"]
    collection_name = config["vectorstore"]["collection_name"]
    reset_collection = config["vectorstore"]["reset_collection"]

    print(f"Loading semantic chunks: {chunks_path}")
    print(f"Total chunks: {len(chunks)}")

    print(f"Loading embedding model: {model_name}")
    model = load_embedding_model(model_name)
    device = get_device()
    print(f"Device: {device}")

    ids, documents, metadatas = prepare_chroma_payload(chunks)

    print("Creating embeddings...")
    embeddings = encode_texts(
        model=model,
        texts=documents,
        batch_size=batch_size,
        normalize_embeddings=normalize_embeddings,
    )

    print("Saving embeddings to ChromaDB...")
    client = get_chroma_client(persist_dir)
    collection = get_or_create_collection(
        client=client,
        collection_name=collection_name,
        reset_collection=reset_collection,
    )

    add_embeddings_to_collection(
        collection=collection,
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    print("Running sample retrieval tests...")
    retrieval_tests = run_sample_retrieval_tests(
        collection=collection,
        model=model,
        batch_size=batch_size,
        normalize_embeddings=normalize_embeddings,
        top_k=3,
    )

    report = build_embedding_report(
        model_name=model_name,
        device=device,
        vectorstore_provider=config["vectorstore"]["provider"],
        persist_dir=persist_dir,
        collection_name=collection_name,
        total_chunks=len(chunks),
        total_embeddings=len(embeddings),
        retrieval_tests=retrieval_tests,
    )

    save_json(report, Path(config["output"]["report"]))

    print("Embedding completed.")
    print(f"Chunks embedded: {len(chunks)}")
    print(f"Embeddings created: {len(embeddings)}")
    print(f"Collection name: {collection_name}")
    print(f"Report saved: {config['output']['report']}")


if __name__ == "__main__":
    main()
