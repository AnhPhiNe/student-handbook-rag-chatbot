import os
import sys
import json
from pathlib import Path

# Thêm thư mục gốc vào PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.build_multi_cohort import merge_chunks, merge_docstore
from src.chunking.runner import split_chunks_by_index_mode

def remerge():
    chunk_dir = Path("data/processed/chunks")
    
    def get_outputs(name):
        return {
            "K48-K49": chunk_dir / f"K48-K49_{name}.json",
            "K50": chunk_dir / f"K50_{name}.json",
            "K51": chunk_dir / f"K51_{name}.json",
        }
        
    print("Merging regulation chunks...")
    merge_chunks(get_outputs("regulation_chunks"), chunk_dir / "regulation_chunks.json")
    print("Merging table chunks...")
    merge_chunks(get_outputs("table_chunks"), chunk_dir / "table_chunks.json")
    print("Merging formula chunks...")
    merge_chunks(get_outputs("formula_chunks"), chunk_dir / "formula_chunks.json")
    print("Merging directory chunks...")
    merge_chunks(get_outputs("directory_chunks"), chunk_dir / "directory_chunks.json")
    print("Merging procedure chunks...")
    merge_chunks(get_outputs("procedure_chunks"), chunk_dir / "procedure_chunks.json")
    print("Merging docstore items...")
    merge_docstore(get_outputs("docstore_items"), chunk_dir / "all_docstore_items.json")
    
    # Combine into all_chunks
    print("Combining all chunks...")
    all_chunks = []
    for c in ["regulation_chunks", "table_chunks", "formula_chunks", "directory_chunks", "procedure_chunks"]:
        with open(chunk_dir / f"{c}.json", "r", encoding="utf-8") as f:
            all_chunks.extend(json.load(f))
            
    with open(chunk_dir / "all_chunks.json", "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)
        
    print(f"Total merged chunks: {len(all_chunks)}")
    
    # Split by index mode (for Vector DB vs lookup)
    semantic_chunks, structured_lookup_chunks, tool_rule_chunks = split_chunks_by_index_mode(all_chunks)
    
    with open(chunk_dir / "semantic_chunks.json", "w", encoding="utf-8") as f:
        json.dump(semantic_chunks, f, ensure_ascii=False, indent=2)
        
    with open(chunk_dir / "structured_lookup_chunks.json", "w", encoding="utf-8") as f:
        json.dump(structured_lookup_chunks, f, ensure_ascii=False, indent=2)
        
    with open(chunk_dir / "tool_rule_chunks.json", "w", encoding="utf-8") as f:
        json.dump(tool_rule_chunks, f, ensure_ascii=False, indent=2)
        
    print(f"Semantic chunks: {len(semantic_chunks)}")
    
    # Reload docstore to print size
    with open(chunk_dir / "all_docstore_items.json", "r", encoding="utf-8") as f:
        docstore = json.load(f)
    print(f"Total docstore items: {len(docstore)}")

if __name__ == "__main__":
    remerge()
