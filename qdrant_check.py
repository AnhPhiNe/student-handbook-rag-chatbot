import sys
sys.stdout.reconfigure(encoding='utf-8')
from qdrant_client import QdrantClient
import os
from src.common.env_loader import load_project_env
load_project_env()
client = QdrantClient(url=os.environ.get('QDRANT_URL'), api_key=os.environ.get('QDRANT_API_KEY'))
payload = client.scroll(collection_name='student_handbook_semantic_v2', limit=1)[0][0].payload
print({k: v for k, v in payload.items() if k != 'content'})
