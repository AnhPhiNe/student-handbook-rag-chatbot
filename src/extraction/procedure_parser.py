import re
from typing import Any

from .text_utils import get_pages_by_type, normalize_text


def extract_procedures(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    procedures = []

    procedure_types = [
        "ktx_admission_procedure",
        "faculty_student_services",
    ]

    for content_type in procedure_types:
        related_pages = get_pages_by_type(pages, content_type)

        if not related_pages:
            continue

        full_text = "\n\n".join(
            normalize_text(page.get("text", ""))
            for page in related_pages
        )

        source_pages = [page["page_number"] for page in related_pages]

        if content_type == "ktx_admission_procedure":
            procedure_name = "Quy trình xét sinh viên vào ở Ký túc xá"
        else:
            procedure_name = "Một số công việc của các khoa liên quan đến sinh viên"

        steps_detected = []

        for line in full_text.splitlines():
            line = line.strip()

            if re.match(r"^\d+\.", line) or line.startswith("-") or line.startswith("–"):
                steps_detected.append(line)

        procedures.append(
            {
                "procedure_id": content_type,
                "procedure_name": procedure_name,
                "content_type": content_type,
                "source_pages": source_pages,
                "steps_detected": steps_detected,
                "raw_text": full_text,
                "review_status": "auto_extracted",
            }
        )

    return procedures