from sentence_transformers import SentenceTransformer


SAMPLE_QUERIES = [
    "Điều kiện xét học bổng là gì?",
    "Muốn tạm nghỉ học cần mẫu đơn nào?",
    "Phòng Đào tạo xử lý việc gì?",
    "Khoa Công nghệ thông tin có ngành nào?",
    "Quy trình vào ký túc xá như thế nào?",
]


def run_sample_retrieval_tests(
    collection,
    model: SentenceTransformer,
    batch_size: int = 8,
    normalize_embeddings: bool = True,
    top_k: int = 3,
) -> list[dict]:
    results = []

    for query in SAMPLE_QUERIES:
        query_embedding = model.encode(
            [query],
            batch_size=batch_size,
            normalize_embeddings=normalize_embeddings,
        ).tolist()

        response = collection.query(
            query_embeddings=query_embedding,
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        query_results = []

        for idx in range(len(response["ids"][0])):
            query_results.append(
                {
                    "chunk_id": response["ids"][0][idx],
                    "distance": response["distances"][0][idx],
                    "metadata": response["metadatas"][0][idx],
                    "preview": response["documents"][0][idx][:300],
                }
            )

        results.append(
            {
                "query": query,
                "top_k": query_results,
            }
        )

    return results
