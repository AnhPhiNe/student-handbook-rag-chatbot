import os
import torch
from typing import Any
from sentence_transformers import CrossEncoder

class LocalReranker:
    _instance = None
    
    def __new__(cls, model_name: str = "itdainb/PhoRanker"):
        if cls._instance is None:
            cls._instance = super(LocalReranker, cls).__new__(cls)
            cls._instance._init(model_name)
        return cls._instance

    def _init(self, model_name: str):
        print(f"[Reranker] Loading local Cross-Encoder model: {model_name}...")
        self.model = CrossEncoder(model_name, max_length=512)
        print("[Reranker] Model loaded successfully.")

    def rerank(self, query: str, results: list[dict[str, Any]], top_n: int = 5) -> list[dict[str, Any]]:
        """Rerank documents using local Cross-Encoder."""
        if not results:
            return []
            
        try:
            # Prepare pairs of (query, document)
            pairs = []
            for res in results:
                content = res.get("content", "")
                title = res.get("metadata", {}).get("title", "")
                # We add title to the content for better context
                full_text = f"{title}\n{content}".strip()
                pairs.append((query, full_text))
                
            # Predict scores
            scores = self.model.predict(pairs)
            
            # Convert logits to probabilities (0 to 1) for consistent thresholding
            # Using sigmoid function
            probabilities = torch.sigmoid(torch.tensor(scores)).tolist()
            
            reranked_results = []
            for idx, prob in enumerate(probabilities):
                original_doc = results[idx]
                new_item = dict(original_doc)
                new_item["rerank"] = {
                    "final_score": prob,
                    "cross_encoder_score": prob,
                    "raw_logit": float(scores[idx])
                }
                reranked_results.append(new_item)
                
            # Sort by descending score
            reranked_results = sorted(reranked_results, key=lambda x: x["rerank"]["final_score"], reverse=True)
            return reranked_results[:top_n]
            
        except Exception as e:
            print(f"[Reranker] Error during reranking: {e}. Fallback to default ranking.")
            # Fallback Reranking: Use basic exact phrase boost
            query_lower = query.lower()
            for idx, res in enumerate(results):
                content = res.get("content", "").lower()
                title = res.get("metadata", {}).get("title", "").lower()
                text = f"{title} {content}"
                
                boost = 0.0
                if "bảng điểm" in query_lower and "bảng điểm" in text:
                    boost += 0.5
                    
                if "rerank" not in res:
                    base_score = max(0.90 - (idx * 0.01), 0.70)
                    res["rerank"] = {"final_score": base_score + boost}
                    
            reranked = sorted(results, key=lambda x: x["rerank"]["final_score"], reverse=True)
            return reranked[:top_n]

def get_local_reranker() -> LocalReranker:
    return LocalReranker()

def rerank_with_cross_encoder(
    query: str,
    results: list[dict[str, Any]],
    top_n: int = 5,
) -> list[dict[str, Any]]:
    reranker = get_local_reranker()
    return reranker.rerank(query, results, top_n)
