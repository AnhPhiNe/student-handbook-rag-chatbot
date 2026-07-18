from typing import Any


def _legacy_build_context_from_vector_results(
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


def build_context_from_vector_results(
    results: list[dict[str, Any]],
    max_items: int = 5,
    *,
    related_items: list[dict[str, Any]] | None = None,
) -> str:
    primary_blocks = []

    for idx, item in enumerate(results[:max_items], start=1):
        metadata = item.get("metadata", {})
        title = _context_item_title(item, metadata)
        primary_blocks.append(
            f"[{idx}]\n"
            f"Title: {title}\n"
            f"Type: {metadata.get('chunk_type')}\n"
            f"Pages: {metadata.get('source_pages')}\n"
            f"Content:\n{item.get('content')}"
        )

    related_blocks = []
    for idx, item in enumerate((related_items or [])[:max_items], start=1):
        metadata = item.get("metadata", {})
        title = _context_item_title(item, metadata)
        related_blocks.append(
            f"[R{idx}]\n"
            f"Title: {title}\n"
            f"Type: {metadata.get('chunk_type')}\n"
            f"Graph depth: {metadata.get('related_graph_depth')}\n"
            f"Linked from primary: {metadata.get('related_source_primary_id')}\n"
            f"Pages: {metadata.get('source_pages')}\n"
            f"Content:\n{item.get('content')}"
        )

    sections = []
    if primary_blocks:
        sections.append("PRIMARY SOURCES\n\n" + "\n\n---\n\n".join(primary_blocks))
    if related_blocks:
        sections.append("RELATED SOURCES\n\n" + "\n\n---\n\n".join(related_blocks))
    return "\n\n===\n\n".join(sections)


def _context_item_title(item: dict[str, Any], metadata: dict[str, Any]) -> str:
    return str(
        metadata.get("title")
        or metadata.get("article")
        or metadata.get("form_name")
        or metadata.get("unit_name")
        or metadata.get("faculty_or_unit_name")
        or metadata.get("program_name")
        or metadata.get("faculty_name")
        or metadata.get("procedure_name")
        or metadata.get("rule_name")
        or item.get("chunk_id")
        or "Source"
    )


def build_context_from_lookup(lookup_result: dict[str, Any]) -> str:
    if lookup_result.get("lookup_type") == "structured_context":
        return build_context_from_structured_context(lookup_result)
    if lookup_result.get("lookup_type") == "form_template":
        return build_context_from_form_lookup(lookup_result)
    if lookup_result.get("lookup_type") == "program_directory":
        return build_context_from_program_lookup(lookup_result)
    if lookup_result.get("lookup_type") == "office_directory":
        return build_context_from_office_lookup(lookup_result)
    if lookup_result.get("lookup_type") == "foreign_language_equivalency":
        return build_context_from_foreign_language_lookup(lookup_result)
    if lookup_result.get("lookup_type") == "study_duration":
        return build_context_from_study_duration_lookup(lookup_result)
    if lookup_result.get("lookup_type") == "scholarship_classification":
        return build_context_from_scholarship_lookup(lookup_result)

    return (
        f"Kết quả tra cứu bảng: {lookup_result.get('table_name')}\n"
        f"Giá trị đầu vào: {lookup_result.get('input_value')}\n"
        f"Kết quả: {lookup_result.get('result')}\n"
        f"Trang nguồn: {lookup_result.get('source_pages')}"
    )


def build_context_from_structured_context(lookup_result: dict[str, Any]) -> str:
    lines = [
        "Structured table context",
        f"Lookup type: {lookup_result.get('source_lookup_type')}",
        f"Cohort: {lookup_result.get('cohort')}",
    ]
    for table_index, table in enumerate(lookup_result.get("items") or [], start=1):
        columns = [str(column) for column in table.get("columns") or []]
        lines.extend(
            [
                "",
                f"[Table {table_index}] {table.get('table_name') or table.get('table_id')}",
                f"Table ID: {table.get('table_id')}",
                f"Table type: {table.get('table_type')}/{table.get('table_subtype')}",
                f"Applicability: {table.get('applicability')}",
                f"Source parent: {table.get('source_parent_id')}",
                f"Pages: {table.get('source_pages')}",
                f"Columns: {', '.join(columns)}",
            ]
        )
        for row_index, row in enumerate(table.get("rows") or [], start=1):
            if not isinstance(row, dict):
                continue
            if columns:
                values = [f"{column}={row.get(column)}" for column in columns]
            else:
                values = [f"{key}={value}" for key, value in row.items()]
            lines.append(f"- Row {row_index}: " + "; ".join(values))
    return "\n".join(lines)


def build_context_from_foreign_language_lookup(lookup_result: dict[str, Any]) -> str:
    result = lookup_result.get("result") or {}
    items = lookup_result.get("items") or []
    rows = items if items else result.get("rows") if isinstance(result, dict) else []
    if isinstance(result, dict) and not rows:
        rows = [result]

    lines = [
        f"Bang quy doi chuan dau ra ngoai ngu: {lookup_result.get('table_name')}",
        f"Cohort: {lookup_result.get('cohort')}",
        f"Source section: {lookup_result.get('source_section')}",
        f"Input: {lookup_result.get('input_value')}",
    ]
    for row in rows:
        parts = [
            f"language={row.get('language')}",
            f"certificate={row.get('certificate')}",
            f"level_or_scale={row.get('level_or_scale')}",
            f"bac_3={row.get('equivalent_level_3')}",
            f"bac_4={row.get('equivalent_level_4')}",
            f"matched_level={row.get('matched_level')}",
        ]
        lines.append(
            "- "
            + "; ".join(
                part for part in parts if part.split("=", 1)[1] not in {"", "None"}
            )
        )
    return "\n".join(lines)


def build_context_from_study_duration_lookup(lookup_result: dict[str, Any]) -> str:
    result = lookup_result.get("result") or {}
    tables = result.get("tables") or lookup_result.get("items") or []
    lines = [
        f"Bang thoi gian hoc tap: {lookup_result.get('table_name')}",
        f"Cohort: {lookup_result.get('cohort')}",
        f"Source section: {lookup_result.get('source_section')}",
        f"Input: {lookup_result.get('input_value')}",
    ]
    for table in tables:
        lines.append(f"- mode={table.get('training_mode')}; table={table.get('table_id')}")
        for row in table.get("rows") or []:
            lines.append(
                "  + "
                f"program={row.get('Chương trình đào tạo')}; "
                f"standard={row.get('Thời gian học tập chuẩn')}; "
                f"maximum={row.get('Thời gian học tập tối đa')}"
            )
    return "\n".join(lines)


def build_context_from_scholarship_lookup(lookup_result: dict[str, Any]) -> str:
    rows = lookup_result.get("items") or []
    lines = [
        f"Bang xep loai hoc bong: {lookup_result.get('table_name')}",
        f"Cohort: {lookup_result.get('cohort')}",
        f"Source section: {lookup_result.get('source_section')}",
        f"Input: {lookup_result.get('input_value')}",
    ]
    for row in rows:
        lines.append(
            "- "
            f"label={row.get('label')}; "
            f"scholarship_score={row.get('scholarship_score_range')}; "
            f"academic_score={row.get('academic_score_range')}; "
            f"conduct={row.get('conduct_score_condition')}"
        )
    return "\n".join(lines)


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
