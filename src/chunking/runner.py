from pathlib import Path
from typing import Any
import os

from src.common.cohort import DOCUMENT_ID_BY_COHORT
from src.common.io import load_json, load_yaml, save_json
from .image_text import restore_image_text
from .regulation_parents import build_regulation_parents
from .supplementary_parents import build_supplementary_parents


CONFIG_PATH = Path("configs/chunking.yaml")


def attach_cohort_metadata(
    docstore_items: list[dict[str, Any]],
    cohort: str | None,
    document_id: str | None = None,
) -> None:
    """Attach handbook identity metadata to every parent record."""

    if not cohort and not document_id:
        return
    for item in docstore_items:
        if cohort:
            item["cohort"] = cohort
        metadata = item.setdefault("metadata", {})
        if cohort:
            metadata["cohort"] = cohort
        if document_id:
            item.setdefault("document_id", document_id)
            metadata["document_id"] = document_id


def main() -> None:
    """Build one cohort's full parent documents from its parsed sections."""

    config = load_yaml(CONFIG_PATH)
    structured_sections = load_json(Path(config["input"]["structured_sections"]))
    document_id = next(
        (
            section.get("document_id")
            for section in structured_sections
            if section.get("document_id")
        ),
        None,
    )
    docstore_items = build_regulation_parents(structured_sections)
    cohort = os.environ.get("COHORT")
    # Content printed as an image (the GPA formula) is written back as text.
    restore_image_text(docstore_items, cohort)
    # Notices, guides, procedures, link pages, the conduct score framework and
    # forms have no articles; they are read from the PDF by page range.
    pdf_path = os.environ.get("PDF_PATH")
    if cohort and pdf_path:
        docstore_items += build_supplementary_parents(cohort, pdf_path)
    attach_cohort_metadata(
        docstore_items,
        cohort=cohort,
        document_id=document_id or DOCUMENT_ID_BY_COHORT.get(cohort),
    )
    save_json(docstore_items, Path(config["output"]["docstore_items"]))
    print(f"Docstore items saved: {len(docstore_items)}")


if __name__ == "__main__":
    main()
