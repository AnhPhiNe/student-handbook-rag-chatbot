import os
import sys
from pathlib import Path
import subprocess

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.build_multi_cohort import merge_chunks, merge_docstore
from scripts.derive_foreign_language_policy import derive_foreign_language_policy

def fast_rebuild():
    cohorts = [
        ("K48-K49", "configs/document_sections_k48_k49.yaml"),
        ("K50", "configs/document_sections_k50.yaml"),
        ("K51", "configs/document_sections_k51.yaml")
    ]
    
    # 1. Run build_chunks for each cohort
    for cohort, config_path in cohorts:
        print(f"--- Building chunks for {cohort} ---")
        env = os.environ.copy()
        env["COHORT"] = cohort
        env["CONFIG_PATH"] = config_path
        subprocess.run([sys.executable, "-m", "scripts.build_chunks"], env=env, check=True)
        
        # rename output files to have cohort prefix
        chunk_dir = Path("data/processed/chunks")
        for file in chunk_dir.glob("*.json"):
            if file.name.startswith(f"{cohort}_"):
                continue
            if file.name in ["all_chunks.json", "semantic_chunks.json", "regulation_chunks.json", "directory_chunks.json", "procedure_chunks.json", "all_docstore_items.json", "formula_chunks.json", "table_chunks.json"]:
                dest = chunk_dir / f"{cohort}_{file.name}"
                if file.name == "all_docstore_items.json":
                    dest = chunk_dir / f"{cohort}_docstore_items.json"
                file.replace(dest)

    # 2. Merge them
    print("--- Merging chunks ---")
    chunk_dir = Path("data/processed/chunks")
    
    def get_outputs(name):
        return {
            "K48-K49": chunk_dir / f"K48-K49_{name}.json",
            "K50": chunk_dir / f"K50_{name}.json",
            "K51": chunk_dir / f"K51_{name}.json",
        }
        
    merge_chunks(get_outputs("regulation_chunks"), chunk_dir / "regulation_chunks.json")
    merge_chunks(get_outputs("table_chunks"), chunk_dir / "table_chunks.json")
    merge_chunks(get_outputs("formula_chunks"), chunk_dir / "formula_chunks.json")
    merge_chunks(get_outputs("directory_chunks"), chunk_dir / "directory_chunks.json")
    merge_chunks(get_outputs("procedure_chunks"), chunk_dir / "procedure_chunks.json")
    merge_docstore(get_outputs("docstore_items"), chunk_dir / "all_docstore_items.json")
    derive_foreign_language_policy(
        chunk_dir / "all_docstore_items.json",
        Path("data/processed/metadata/derived_foreign_language_policy_report.json"),
    )
    
    all_chunks = []
    for c in ["regulation_chunks", "table_chunks", "formula_chunks", "directory_chunks", "procedure_chunks"]:
        import json
        with open(chunk_dir / f"{c}.json", "r", encoding="utf-8") as f:
            all_chunks.extend(json.load(f))
            
    with open(chunk_dir / "all_chunks.json", "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)
        
    print("Fast rebuild completed successfully!")

if __name__ == "__main__":
    fast_rebuild()
