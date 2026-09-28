"""Re-anchor reviewed table regions after a parent's text changed outside them.

The table-separation review (data/curated/regulation_table_regions.json) binds
each reviewed parent by its content hash and each table region by character
offsets. When a parser fix changes a parent's text elsewhere (for example it
drops a signature block), the reviewed table text itself is unchanged but its
offsets and the parent hash are not. This script moves each region to the one
place its reviewed source_text occurs in the rebuilt parent and records the
new hash; it also drops source-page corrections that the rebuilt parent now
satisfies by itself. It refuses when a region's text is missing or ambiguous,
so any change inside a reviewed table still needs a manual review.

    python -m scripts.reanchor_table_regions            # report only
    python -m scripts.reanchor_table_regions --write    # update the review file
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "data/curated/regulation_table_regions.json"
PARENTS = ROOT / "data/processed/chunks/all_docstore_items.json"


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def reanchor(review: dict, parents: dict[str, dict]) -> list[str]:
    """Update stale entries in place; return the parent ids that moved."""
    moved = []
    for entry in review["parents"]:
        content = parents[entry["parent_id"]]["content"]
        if text_hash(content) == entry["content_sha256"]:
            continue
        for region in entry["regions"]:
            count = content.count(region["source_text"])
            if count != 1:
                raise ValueError(
                    f"{entry['parent_id']}: reviewed region text occurs {count} times; review it again"
                )
            region["start"] = content.index(region["source_text"])
            region["end"] = region["start"] + len(region["source_text"])
        entry["content_sha256"] = text_hash(content)
        moved.append(entry["parent_id"])
    return moved


def drop_resolved_page_corrections(review: dict, parents: dict[str, dict]) -> list[str]:
    """Drop page corrections the rebuilt parent already satisfies on its own."""
    kept, dropped = [], []
    for entry in review.get("source_page_corrections", []):
        if parents[entry["parent_id"]]["metadata"].get("source_pages") == entry["source_pages"]:
            dropped.append(entry["parent_id"])
        else:
            kept.append(entry)
    review["source_page_corrections"] = kept
    return dropped


def dump(review: dict) -> str:
    return json.dumps(review, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Save the updated review file.")
    args = parser.parse_args()
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    parents = {p["_id"]: p for p in json.loads(PARENTS.read_text(encoding="utf-8"))}
    dropped = drop_resolved_page_corrections(review, parents)
    moved = reanchor(review, parents)
    print(f"Page corrections no longer needed: {dropped}")
    print(f"Re-anchored {len(moved)} reviewed parents: {moved}")
    if args.write and (moved or dropped):
        REVIEW.write_text(dump(review), encoding="utf-8")
        print(f"Updated {REVIEW.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
