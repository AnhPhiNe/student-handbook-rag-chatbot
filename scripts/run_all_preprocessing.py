from __future__ import annotations

import subprocess
import sys


STEPS = [
    ("extract PDF pages", ["-m", "scripts.extract_pdf_pages"]),
    ("parse structured sections", ["-m", "scripts.parse_structure"]),
    ("extract structured data", ["-m", "scripts.extract_structured_data"]),
    ("build chunks", ["-m", "scripts.build_chunks"]),
    ("build vectorstore", ["-m", "scripts.build_vectorstore"]),
    ("run retrieval batch report", ["-m", "scripts.evaluate_retrieval_batch"]),
]


def main() -> None:
    for label, command in STEPS:
        print(f"\n==> {label}")
        subprocess.run([sys.executable, *command], check=True)

    print("\nPreprocessing pipeline completed.")


if __name__ == "__main__":
    main()
