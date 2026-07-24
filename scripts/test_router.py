import sys
from src.retrieval.core.query_router import route_query

query = "Em thuộc K48-K49, cho em hỏi quy định về hiệu lực và trách nhiệm thi hành là như thế nào?"
plan = route_query(query)
print("Intent:", plan.get("intent"))
print("Chunk types:", plan.get("chunk_types"))
print("Strategy:", plan.get("strategy"))
