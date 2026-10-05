"""Which handbook text reached no parent article and no catalog?

Every run of six consecutive words on each PDF page is looked up in the parent
articles of the same cohort, and then in the structured tables and directories.
Words covered by neither are grouped into spans of eight words or more, so that a
reader can tell content left out on purpose (the college regulation, legal
boilerplate, the table of contents) from text lost in extraction.

A table that the build rewrote as sentences, such as the conduct-score frame,
shows as missing here although its values are kept, so a reported span is a lead
to read, not a defect. It reads the committed artefacts and calls no model.

    python -m scripts.audit_pdf_coverage --out data/eval/reports/pdf_coverage.json
"""
import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterator

import fitz

ROOT = Path(__file__).resolve().parents[1]
PDFS = {
    "K48-K49": ROOT / "data/raw/so-tay-sinh-vien-khoa-48-49.pdf",
    "K50": ROOT / "data/raw/so-tay-sinh-vien-khoa-50.pdf",
    "K51": ROOT / "data/raw/so-tay-sinh-vien-khoa-51.pdf",
}
PARENTS = ROOT / "data/processed/chunks/all_docstore_items.json"
CATALOGS = [*sorted((ROOT / "data/processed/tables").glob("*.json")),
            *sorted((ROOT / "data/processed/directories").glob("*.json"))]
N = 6
MIN_SPAN = 8


def words(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text).casefold().replace("­", "")
    return re.findall(r"\w+", re.sub(r"[‐-―−]", "-", text))


def grams(tokens: list[str]) -> set[tuple[str, ...]]:
    return {tuple(tokens[i:i + N]) for i in range(len(tokens) - N + 1)}


def strings(value: Any) -> Iterator[str]:
    """Every string inside a JSON value, so escapes such as \\n never join two words."""

    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def covered(tokens: list[str], known: set[tuple[str, ...]]) -> list[bool]:
    marks = [False] * len(tokens)
    for i in range(len(tokens) - N + 1):
        if tuple(tokens[i:i + N]) in known:
            marks[i:i + N] = [True] * N
    return marks


def audit() -> dict[str, Any]:
    parents = json.loads(PARENTS.read_text(encoding="utf-8"))
    catalog_grams = grams(words("\n".join(
        text for path in CATALOGS for text in strings(json.loads(path.read_text(encoding="utf-8")))
    )))
    report: dict[str, Any] = {}
    for cohort, pdf in PDFS.items():
        parent_grams = grams(words("\n".join(p.get("content") or "" for p in parents if p.get("cohort") == cohort)))
        pages, totals = [], {"words": 0, "in_parents": 0, "in_catalogs_only": 0, "nowhere": 0}
        for number, page in enumerate(fitz.open(pdf), start=1):
            tokens = words(page.get_text("text"))
            if len(tokens) < N:
                continue
            in_parent = covered(tokens, parent_grams)
            in_catalog = covered(tokens, catalog_grams)
            found = [p or c for p, c in zip(in_parent, in_catalog)]
            spans, start = [], None
            for i, hit in enumerate([*found, True]):
                if not hit and start is None:
                    start = i
                elif hit and start is not None:
                    if i - start >= MIN_SPAN:
                        spans.append({"words": i - start, "text": " ".join(tokens[start:i])})
                    start = None
            parent_words = sum(in_parent)
            catalog_words = sum(c and not p for p, c in zip(in_parent, in_catalog))
            totals["words"] += len(tokens)
            totals["in_parents"] += parent_words
            totals["in_catalogs_only"] += catalog_words
            totals["nowhere"] += len(tokens) - parent_words - catalog_words
            pages.append({"page": number, "words": len(tokens),
                          "parent_coverage": round(parent_words / len(tokens), 3), "missing_spans": spans})
        report[cohort] = {"totals": totals, "pages": pages}
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="write per-page spans as JSON")
    args = parser.parse_args()
    report = audit()
    for cohort, result in report.items():
        t = result["totals"]
        print(f"{cohort}: {t['words']} words; in parents {t['in_parents'] / t['words']:.1%}, "
              f"only in tables or directories {t['in_catalogs_only'] / t['words']:.1%}, "
              f"nowhere {t['nowhere'] / t['words']:.1%}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
