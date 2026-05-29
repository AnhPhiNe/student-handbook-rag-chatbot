import sys
sys.path.insert(0, r'c:\Users\A Fee\Desktop\Workspace\student_handbook_rag')
from src.api.dependencies import get_chroma_collection, get_embedding_model
from src.retrieval.core.retrieval_pipeline import run_retrieval_pipeline

col = get_chroma_collection(r'c:\Users\A Fee\Desktop\Workspace\student_handbook_rag\data\vectorstore\chroma')
mod = get_embedding_model()
res = run_retrieval_pipeline('Khi nào bị cảnh cáo học vụ?', mod, col, [], [], [], [])
print("Target chunk types:", res.get("target_chunk_types"))
print("Titles:")
for item in res['retrieved_items']:
    print("-", item['metadata'].get('title'))
