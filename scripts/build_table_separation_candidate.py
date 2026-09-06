"""Historical experiment entry point; implementation lives in the official builder."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.build_parent_child_artifacts import (  # noqa: E402,F401
    POLICY,
    digest,
    main,
    separate_tables,
    text_hash,
    verify_mongo_parents,
)

if __name__ == "__main__":
    main()
