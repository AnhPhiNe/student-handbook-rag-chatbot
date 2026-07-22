import os
import re
import csv
import logging
from typing import Any, List, Dict, Optional
from rank_bm25 import BM25Okapi
import underthesea

logger = logging.getLogger(__name__)

class BM25Retriever:
    def __init__(self):
        self.bm25_index = None
        self.chunks = []
        self.acronym_whitelist = set()
        self._load_acronym_whitelist()

        # Regex for capturing codes and numbers (e.g., 7480201, 23/QĐ-BGDĐT)
        self.literal_regex = re.compile(
            r'\b\d{4,}\b|\d+/[A-ZĐ\-]+|IELTS|TOEFL|B1|B2|Goethe-Zertifikat',
            re.IGNORECASE
        )

    def _load_acronym_whitelist(self):
        csv_path = os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "../../../crawl_data/chuong_trinh_dao_tao.csv"
        ))
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                departments = set()
                for row in reader:
                    dept = row.get("query_department")
                    if dept and str(dept).strip():
                        departments.add(str(dept).strip())
            
            for dept in departments:
                # Naive acronym generation: take the first letter of each word
                words = str(dept).split()
                acronym = "".join([w[0].upper() for w in words if w])
                if len(acronym) > 1:
                    self.acronym_whitelist.add(acronym)
            logger.info(f"Loaded {len(self.acronym_whitelist)} acronyms from CSV.")
        except Exception as e:
            logger.warning(f"Could not load acronym whitelist: {e}")
            # Fallback hardcoded list if CSV fails
            self.acronym_whitelist.update(["CNTT", "GDTC", "GDQP", "GDMN", "GDTH", "GDDB"])

    def _tokenize(self, text: str) -> list[str]:
        if not text:
            return []

        tokens = []
        # Layer 1: Literal Extraction
        # Find all literal matches and remove them from the text to be segmented
        literals = []
        
        def literal_replacer(match):
            lit = match.group(0)
            literals.append(lit.lower())
            return " "
            
        text_for_segmentation = self.literal_regex.sub(literal_replacer, text)
        
        # Also extract acronyms from whitelist
        words = text_for_segmentation.split()
        for w in words:
            if w.upper() in self.acronym_whitelist:
                literals.append(w.lower())
                text_for_segmentation = text_for_segmentation.replace(w, " ")

        tokens.extend(literals)

        # Layer 2: Word Segmentation (underthesea)
        try:
            segmented_words = underthesea.word_tokenize(text_for_segmentation.lower())
            tokens.extend([w.replace(" ", "_") for w in segmented_words])
            
            # Bigrams of adjacent segmented syllables (fallback for bad segmentation)
            syllables = text_for_segmentation.lower().split()
            bigrams = [f"{syllables[i]}_{syllables[i+1]}" for i in range(len(syllables)-1)]
            tokens.extend(bigrams)
            
        except Exception as e:
             logger.warning(f"Underthesea tokenization failed: {e}")
             # Absolute fallback
             tokens.extend(text_for_segmentation.lower().split())

        return [t for t in tokens if t.strip()]

    def build_bm25_index(self, chunks: list[dict[str, Any]]):
        self.chunks = chunks
        corpus_tokens = [self._tokenize(str(chunk.get("content") or "")) for chunk in self.chunks]
        self.bm25_index = BM25Okapi(corpus_tokens)
        logger.info(f"BM25 index built with {len(self.chunks)} chunks.")

    def search_bm25(self, query: str, top_k: int = 24) -> list[tuple[float, dict[str, Any]]]:
        if not self.bm25_index or not self.chunks:
            return []

        query_tokens = self._tokenize(query)
        scores = self.bm25_index.get_scores(query_tokens)
        
        # Pair scores with chunks
        scored_chunks = [(float(score), dict(chunk)) for score, chunk in zip(scores, self.chunks)]
        
        # Filter zero scores and sort
        scored_chunks = [sc for sc in scored_chunks if sc[0] > 0.0]
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        return scored_chunks[:top_k]

# Global instance for legacy pipeline compat
_global_bm25_retriever = None

def get_bm25_retriever():
    global _global_bm25_retriever
    if _global_bm25_retriever is None:
        _global_bm25_retriever = BM25Retriever()
    return _global_bm25_retriever
