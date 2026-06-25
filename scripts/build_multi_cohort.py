import os
import subprocess
import sys
from pathlib import Path
import json
import shutil

def get_cohort_from_filename(filename: str) -> str:
    import re
    match = re.search(r"khoa-(\d+)", filename, re.IGNORECASE)
    if match:
        k = int(match.group(1))
        if k <= 49:
            return "K48-K49"
        else:
            return "K50-K51"
    return "UNKNOWN"

def run_pipeline_for_pdf(pdf_path: Path, cohort: str):
    print(f"\n{'='*50}\n--- RUNNING PIPELINE FOR {pdf_path.name} ({cohort}) ---\n{'='*50}")
    
    STEPS = [
        ("extract PDF pages", ["-m", "scripts.extract_pdf_pages"]),
        ("parse structured sections", ["-m", "scripts.parse_structure"]),
        ("extract structured data", ["-m", "scripts.extract_structured_data"]),
        ("build chunks", ["-m", "scripts.build_chunks"]),
    ]
    
    env = os.environ.copy()
    env["PDF_PATH"] = str(pdf_path)
    env["COHORT"] = cohort
    
    for label, command in STEPS:
        print(f"\n==> {label} ({cohort})")
        subprocess.run([sys.executable, *command], env=env, check=True)

def merge_chunks(cohort_files, output_path):
    all_chunks = []
    for cohort, path in cohort_files.items():
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            chunks = json.load(f)
            for chunk in chunks:
                if "metadata" not in chunk:
                    chunk["metadata"] = {}
                chunk["metadata"]["cohort"] = cohort
                chunk["chunk_id"] = f"{cohort}_{chunk['chunk_id']}"
            all_chunks.extend(chunks)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

def main():
    raw_dir = Path("data/raw")
    pdfs = list(raw_dir.glob("*.pdf"))
    
    if not pdfs:
        print("No PDFs found in data/raw!")
        return

    chunk_dir = Path("data/processed/chunks")
    
    semantic_outputs = {}
    structured_outputs = {}
    tool_outputs = {}

    for pdf in pdfs:
        cohort = get_cohort_from_filename(pdf.name)
        run_pipeline_for_pdf(pdf, cohort)
        
        sem_dest = chunk_dir / f"{cohort}_semantic_chunks.json"
        struc_dest = chunk_dir / f"{cohort}_structured_lookup_chunks.json"
        tool_dest = chunk_dir / f"{cohort}_tool_rule_chunks.json"
        
        shutil.copy(chunk_dir / "semantic_chunks.json", sem_dest)
        shutil.copy(chunk_dir / "structured_lookup_chunks.json", struc_dest)
        shutil.copy(chunk_dir / "tool_rule_chunks.json", tool_dest)
        
        semantic_outputs[cohort] = sem_dest
        structured_outputs[cohort] = struc_dest
        tool_outputs[cohort] = tool_dest

    print(f"\n{'='*50}\n--- MERGING MULTI-COHORT CHUNKS ---\n{'='*50}")
    merge_chunks(semantic_outputs, chunk_dir / "semantic_chunks.json")
    merge_chunks(structured_outputs, chunk_dir / "structured_lookup_chunks.json")
    merge_chunks(tool_outputs, chunk_dir / "tool_rule_chunks.json")
    
    print(f"\n{'='*50}\n--- BUILDING UNIFIED VECTOR STORE ---\n{'='*50}")
    subprocess.run([sys.executable, "-m", "scripts.build_vectorstore"], check=True)
    
    print("\nMulti-cohort preprocessing completed successfully!")

if __name__ == "__main__":
    main()
