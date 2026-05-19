from typing import Any

from .chunk_schema import create_chunk
from .text_utils import format_source_pages, join_non_empty


def fields_to_text(fields: list[str]) -> str:
    if not fields:
        return "Không phát hiện field rõ ràng."

    return ", ".join(fields)


def infer_form_purpose(form_name: str) -> str:
    lower = form_name.lower()

    if "tạm nghỉ" in lower:
        return "Dùng khi sinh viên muốn xin tạm nghỉ học."
    if "học lại" in lower:
        return "Dùng khi sinh viên muốn xin quay lại học sau thời gian tạm nghỉ."
    if "thôi học" in lower:
        return "Dùng khi sinh viên muốn xin thôi học."
    if "ký túc xá" in lower:
        return "Dùng khi sinh viên muốn xin vào ở ký túc xá."
    if "trợ cấp" in lower:
        return "Dùng khi sinh viên xin trợ cấp xã hội."
    if "miễn, giảm học phí" in lower:
        return "Dùng khi sinh viên đề nghị miễn, giảm học phí."

    return "Biểu mẫu phục vụ thủ tục sinh viên."


def build_form_chunks(forms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks = []

    for form in forms:
        source_pages = form.get("source_pages", [])
        form_name = form.get("form_name", "")

        content = join_non_empty(
            [
                f"Biểu mẫu: {form_name}",
                f"Mục đích: {infer_form_purpose(form_name)}",
                f"Thông tin/field phát hiện: {fields_to_text(form.get('required_fields_detected', []))}",
                f"Nguồn: {format_source_pages(source_pages)}",
                "Ghi chú: raw_text biểu mẫu được lưu riêng để hiển thị khi cần.",
            ]
        )

        chunks.append(
            create_chunk(
                chunk_id=f"form_{form['form_id']}",
                chunk_type="form",
                index_mode="semantic",
                content=content,
                metadata={
                    "source_type": "form_template",
                    "form_id": form.get("form_id"),
                    "form_name": form_name,
                    "source_pages": source_pages,
                    "review_status": form.get("review_status"),
                    "raw_text_available": True,
                },
            )
        )

    return chunks