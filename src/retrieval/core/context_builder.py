from typing import Any


def build_context_from_vector_results(
    results: list[dict[str, Any]], max_items: int = 5
) -> str:
    blocks = []

    for idx, item in enumerate(results[:max_items], start=1):
        metadata = item.get("metadata", {})
        title = (
            metadata.get("title")
            or metadata.get("form_name")
            or metadata.get("unit_name")
            or metadata.get("faculty_or_unit_name")
            or metadata.get("program_name")
            or metadata.get("faculty_name")
            or metadata.get("procedure_name")
            or metadata.get("rule_name")
            or item.get("chunk_id")
        )

        blocks.append(
            f"[Nguồn {idx}]\n"
            f"Tiêu đề: {title}\n"
            f"Loại: {metadata.get('chunk_type')}\n"
            f"Trang: {metadata.get('source_pages')}\n"
            f"Nội dung:\n{item.get('content')}"
        )

    return "\n\n---\n\n".join(blocks)


def build_context_from_lookup(lookup_result: dict[str, Any]) -> str:
    if lookup_result.get("lookup_type") == "form_template":
        return build_context_from_form_lookup(lookup_result)
    if lookup_result.get("lookup_type") == "program_directory":
        return build_context_from_program_lookup(lookup_result)
    if lookup_result.get("lookup_type") == "office_directory":
        return build_context_from_office_lookup(lookup_result)

    return (
        f"Kết quả tra cứu bảng: {lookup_result.get('table_name')}\n"
        f"Giá trị đầu vào: {lookup_result.get('input_value')}\n"
        f"Kết quả: {lookup_result.get('result')}\n"
        f"Trang nguồn: {lookup_result.get('source_pages')}"
    )


def build_context_from_program_lookup(lookup_result: dict[str, Any]) -> str:
    programs = lookup_result.get("result") or []
    lines = [
        f"Ket qua tra cuu nganh dao tao: {lookup_result.get('table_name')}",
        f"Cau hoi: {lookup_result.get('input_value')}",
        f"Khoa ap dung: {lookup_result.get('cohort') or 'khong xac dinh'}",
        f"So nganh tim thay: {lookup_result.get('program_count') or len(programs)}",
    ]

    for index, program in enumerate(programs, start=1):
        lines.append(
            f"{index}. {program.get('program_name')} - "
            f"{program.get('faculty_name') or 'Chua xac dinh khoa phu trach'} "
            f"(trang {program.get('source_pages')})"
        )

    return "\n".join(lines)


def build_context_from_form_lookup(lookup_result: dict[str, Any]) -> str:
    forms = lookup_result.get("result") or []
    lines = [
        f"Kết quả tra cứu biểu mẫu: {lookup_result.get('table_name')}",
        f"Câu hỏi: {lookup_result.get('input_value')}",
        f"Khóa áp dụng: {lookup_result.get('cohort') or 'không xác định'}",
    ]

    for index, form in enumerate(forms, start=1):
        fields = form.get("required_fields_detected") or []
        field_text = ", ".join(fields) if fields else "không phát hiện field rõ ràng"
        lines.extend(
            [
                "",
                f"[Biểu mẫu {index}] {form.get('form_name')}",
                f"Trang nguồn: {form.get('source_pages')}",
                f"Thông tin cần điền: {field_text}",
                f"Tóm tắt/đoạn nhận diện: {form.get('summary')}",
            ]
        )

    return "\n".join(lines)


def build_context_from_office_lookup(lookup_result: dict[str, Any]) -> str:
    offices = lookup_result.get("result") or []
    lines = [
        f"Ket qua tra cuu phong ban/lien he: {lookup_result.get('table_name')}",
        f"Cau hoi: {lookup_result.get('input_value')}",
        f"Khoa ap dung: {lookup_result.get('cohort') or 'khong xac dinh'}",
    ]

    for index, office in enumerate(offices, start=1):
        emails = ", ".join(office.get("emails") or []) or "chua co email trong du lieu"
        phones = ", ".join(office.get("phones") or []) or "chua co so dien thoai trong du lieu"
        internal = ", ".join(office.get("internal_numbers") or [])
        websites = ", ".join(office.get("websites") or [])
        responsibilities = office.get("responsibilities") or []

        lines.extend(
            [
                "",
                f"[Phong ban {index}] {office.get('unit_name')}",
                f"Trang nguon: {office.get('source_pages')}",
                f"Email: {emails}",
                f"Dien thoai: {phones}",
            ]
        )
        if internal:
            lines.append(f"So may noi bo: {internal}")
        if websites:
            lines.append(f"Website: {websites}")
        if responsibilities:
            lines.append("Nhiem vu lien quan:")
            lines.extend(f"- {item}" for item in responsibilities[:4])

    return "\n".join(lines)


def build_context_from_tool(tool_result: dict[str, Any]) -> str:
    return (
        f"Kết quả công cụ tính toán: {tool_result.get('tool_name')}\n"
        f"Input: {tool_result.get('inputs')}\n"
        f"Kết quả: {tool_result.get('result')}\n"
        f"Ghi chú: {tool_result.get('note')}"
    )


def build_context_from_formula(formula_result: dict[str, Any]) -> str:
    variables = formula_result.get("variables") or {}
    variable_lines = "\n".join(f"- {key}: {value}" for key, value in variables.items())
    raw_excerpt = formula_result.get("raw_excerpt", "")
    excerpt_text = (
        f"\n\nTrích dẫn quy định chi tiết:\n{raw_excerpt}" if raw_excerpt else ""
    )

    return (
        f"Công thức: {formula_result.get('rule_name')}\n"
        f"Biểu thức: {formula_result.get('formula_text')}\n"
        f"Biến số:\n{variable_lines}\n"
        f"Nguồn: {formula_result.get('source_article')}, trang {formula_result.get('source_pages')}"
        f"{excerpt_text}"
    )
