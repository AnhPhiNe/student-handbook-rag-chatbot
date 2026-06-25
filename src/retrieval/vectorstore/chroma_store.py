from pathlib import Path
import chromadb


def get_chroma_client(persist_dir: str):
    Path(persist_dir).mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=persist_dir,
        settings=chromadb.Settings(anonymized_telemetry=False)
    )


def get_or_create_collection(
    client,
    collection_name: str,
    reset_collection: bool = False,
):
    if reset_collection:
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass

    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def add_embeddings_to_collection(
    collection,
    ids: list[str],
    documents: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict],
) -> None:
    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )