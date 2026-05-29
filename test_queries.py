import sys
sys.path.insert(0, r'c:\Users\A Fee\Desktop\Workspace\student_handbook_rag')

from src.retrieval.core.ai_router import AIRouter
from src.retrieval.core.vector_retriever import get_chroma_collection, load_embedding_model, vector_search

router = AIRouter()
col = get_chroma_collection(r'c:\Users\A Fee\Desktop\Workspace\student_handbook_rag\data\vectorstore\chroma', 'student_handbook_semantic')
mod = load_embedding_model('keepitreal/vietnamese-sbert')

queries = [
    "khoa ngữ văn ở phòng nào",
    "khoa ngữ văn ở đâu",
    "số điện thoại của khoa tiếng Anh thì sao"
]

for q in queries:
    print(f"\n--- QUERY: {q} ---")
    route = router.route(q)
    print("Router intent:", route.get("intent"))
    print("Router strategy:", route.get("strategy"))
    print("Router targets:", route.get("target_chunk_types"))
    
    target_chunks = route.get("target_chunk_types", [])
    if not target_chunks:
        target_chunks = ["office_directory", "faculty_program_directory"]
        
    res = vector_search(q, mod, col, target_chunks, top_k=3, batch_size=8, normalize_embeddings=True)
    for i, r in enumerate(res):
        print(f"  Result {i+1}: {r['metadata'].get('faculty_or_unit_name')} or {r['metadata'].get('title')} (Score: {r['score']})")
