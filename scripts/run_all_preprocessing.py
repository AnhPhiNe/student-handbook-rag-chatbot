from __future__ import annotations

import subprocess
import sys


STEPS = [
    ("extract structured data", ["-m", "scripts.run_phase4"]),
    ("build chunks", ["-m", "scripts.run_phase5"]),
    ("build vectorstore", ["-m", "scripts.run_phase6"]),
    ("run retrieval batch report", ["-m", "scripts.run_phase7_batch"]),
]


def main() -> None:
    for label, command in STEPS:
        print(f"\n==> {label}")
        subprocess.run([sys.executable, *command], check=True)

    print("\nPreprocessing pipeline completed.")


if __name__ == "__main__":
    main()
