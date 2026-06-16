import os
import unicodedata
import re
from typing import Any
from pathlib import Path
from rank_bm25 import BM25Okapi
from .io_utils import load_json

def normalize_text_for_bm25(text: str) -> str:
    text = text.lower()
    text = text.replace("–", "-")
    text = text.replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def get_searchable_text(item: dict[str, Any]) -> str:
    metadata = item.get("metadata", {})
    parts = [
        item.get("content", ""),
        metadata.get("title", ""),
        metadata.get("form_name", ""),
        metadata.get("unit_name", ""),
        metadata.get("faculty_or_unit_name", ""),
        metadata.get("procedure_name", ""),
    ]
    return " ".join(str(p) for p in parts if p)

class BM25Retriever:
    _instance = None
    
    def __new__(cls, chunks_path: str = "data/processed/chunks/semantic_chunks.json"):
        if cls._instance is None:
            cls._instance = super(BM25Retriever, cls).__new__(cls)
            cls._instance._init(chunks_path)
        return cls._instance
        
    def _init(self, chunks_path: str):
        self.chunks_path = chunks_path
        self.chunks = []
        self.bm25 = None
        self._load_and_index()
        
    def _load_and_index(self):
        if not os.path.exists(self.chunks_path):
            print(f"[BM25] Warning: {self.chunks_path} not found. BM25 indexing skipped.")
            return
            
        print(f"[BM25] Loading {self.chunks_path} for sparse indexing...")
        self.chunks = load_json(Path(self.chunks_path))
        
        tokenized_corpus = []
        for chunk in self.chunks:
            searchable_text = get_searchable_text(chunk)
            normalized = normalize_text_for_bm25(searchable_text)
            # Tokenize by whitespace
            tokens = normalized.split()
            tokenized_corpus.append(tokens)
            
        self.bm25 = BM25Okapi(tokenized_corpus)
        print(f"[BM25] Indexed {len(self.chunks)} chunks.")
        
    def sparse_search(self, query: str, top_k: int = 15) -> list[dict[str, Any]]:
        if not self.bm25 or not self.chunks:
            return []
            
        normalized_query = normalize_text_for_bm25(query)
        tokenized_query = normalized_query.split()
        
        # Get scores for all documents
        scores = self.bm25.get_scores(tokenized_query)
        
        # Get top-k indices
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        
        results = []
        for idx in top_indices:
            score = float(scores[idx])
            if score <= 0.0:
                continue
                
            chunk = self.chunks[idx]
            results.append({
                "chunk_id": chunk.get("chunk_id"),
                "distance": 0.0, # Not applicable for BM25
                "bm25_score": score,
                "content": chunk.get("content", ""),
                "metadata": chunk.get("metadata", {}),
            })
            
        return results

# Singleton helper
def get_bm25_retriever(chunks_path: str = "data/processed/chunks/semantic_chunks.json") -> BM25Retriever:
    return BM25Retriever(chunks_path)
