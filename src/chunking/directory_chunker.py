from typing import Any

from .chunk_schema import create_chunk
from .text_utils import format_source_pages, join_non_empty, normalize_text
from .token_utils import count_tokens_approx, split_text_by_paragraph


def build_directory_content(
    title: str,
    raw_text: str,
    source_pages: list[int],
) -> str:
    """Tạo một chuỗi nội dung hoàn chỉnh cho mục thư mục.

    Hàm này kết hợp tiêu đề, văn bản thô đã được chuẩn hóa và thông tin trang nguồn
    thành một chuỗi duy nhất, dễ đọc.

    Args:
        title: Tiêu đề của mục thư mục (ví dụ: "Đơn vị/phòng ban: Tên đơn vị").
        raw_text: Văn bản thô chưa được xử lý của mục thư mục.
        source_pages: Một danh sách các số nguyên biểu thị các trang nguồn
            mà thông tin này được lấy từ đó.

    Returns:
        Một chuỗi (string) chứa toàn bộ nội dung đã được định dạng,
        bao gồm tiêu đề, văn bản và thông tin nguồn.
    """
    return join_non_empty(
        [
            title,
            "Thông tin liên quan:",
            normalize_text(raw_text),
            f"Nguồn: {format_source_pages(source_pages)}",
        ]
    )


def split_long_directory_content(
    content: str,
    max_tokens: int,
) -> list[str]:
    """Chia nhỏ nội dung thư mục dài thành các phần nhỏ hơn.

    Nếu nội dung vượt quá số lượng token tối đa cho phép, hàm này sẽ chia nội dung
    thành nhiều phần dựa trên các đoạn văn, đảm bảo mỗi phần không vượt quá
    giới hạn token. Điều này giúp xử lý các đoạn văn bản quá dài.

    Args:
        content: Chuỗi nội dung cần được kiểm tra và chia nhỏ.
        max_tokens: Số lượng token tối đa cho phép trong mỗi phần nội dung.

    Returns:
        Một danh sách các chuỗi (list of strings), trong đó mỗi chuỗi là một phần
        của nội dung gốc. Nếu nội dung không quá dài, danh sách sẽ chỉ chứa
        một phần tử là toàn bộ nội dung gốc.
    """
    if count_tokens_approx(content) <= max_tokens:
        return [content]

    return split_text_by_paragraph(
        text=content,
        max_tokens=max_tokens,
        overlap_tokens=0,
    )


def build_office_chunks(
    office_records: list[dict[str, Any]],
    max_tokens: int = 350,
) -> list[dict[str, Any]]:
    """Tạo các "chunk" (khối thông tin) từ danh sách các bản ghi văn phòng/phòng ban.

    Hàm này duyệt qua từng bản ghi văn phòng, tạo nội dung hoàn chỉnh cho mỗi bản ghi,
    sau đó chia nhỏ nội dung nếu nó quá dài. Mỗi phần nội dung sẽ được chuyển đổi
    thành một "chunk" có cấu trúc, chứa nội dung và các thông tin mô tả (metadata)
    liên quan.

    Args:
        office_records: Một danh sách các từ điển (list of dicts), mỗi từ điển
            đại diện cho một bản ghi thông tin về văn phòng hoặc phòng ban.
            Mỗi bản ghi cần có ít nhất 'record_id', 'unit_name', 'raw_text',
            và 'source_pages'.
        max_tokens: Số lượng token tối đa cho phép trong mỗi "chunk" nội dung.
            Mặc định là 350.

    Returns:
        Một danh sách các từ điển (list of dicts), trong đó mỗi từ điển là một "chunk"
        thông tin đã được tạo. Mỗi "chunk" bao gồm 'chunk_id', 'chunk_type',
        'index_mode', 'content', và 'metadata'.
    """
    chunks = []

    for record in office_records:
        source_pages = record.get("source_pages", [])
        unit_name = record.get("unit_name", "")

        content = build_directory_content(
            title=f"Đơn vị/phòng ban: {unit_name}",
            raw_text=record.get("raw_text", ""),
            source_pages=source_pages,
        )

        parts = split_long_directory_content(content, max_tokens=max_tokens)

        for idx, part in enumerate(parts, start=1):
            suffix = f"_part_{idx}" if len(parts) > 1 else ""

            chunks.append(
                create_chunk(
                    chunk_id=f"office_{record['record_id']}{suffix}",
                    chunk_type="office_directory",
                    index_mode="semantic",
                    content=part,
                    metadata={
                        "source_type": "office_directory",
                        "record_id": record.get("record_id"),
                        "unit_name": unit_name,
                        "source_pages": source_pages,
                        "needs_manual_review": record.get("needs_manual_review"),
                        "split_from_record": len(parts) > 1,
                        "part_index": idx,
                        "total_parts": len(parts),
                    },
                )
            )

    return chunks


def build_faculty_chunks(
    faculty_records: list[dict[str, Any]],
    max_tokens: int = 350,
) -> list[dict[str, Any]]:
    """Tạo các "chunk" (khối thông tin) từ danh sách các bản ghi khoa/tổ.

    Hàm này tương tự như `build_office_chunks` nhưng được thiết kế để xử lý
    thông tin về các khoa hoặc tổ. Nó duyệt qua từng bản ghi khoa, tạo nội dung
    hoàn chỉnh, chia nhỏ nếu cần, và chuyển đổi thành các "chunk" có cấu trúc
    với metadata phù hợp.

    Args:
        faculty_records: Một danh sách các từ điển (list of dicts), mỗi từ điển
            đại diện cho một bản ghi thông tin về khoa hoặc tổ.
            Mỗi bản ghi cần có ít nhất 'record_id', 'faculty_or_unit_name',
            'raw_text', và 'source_pages'.
        max_tokens: Số lượng token tối đa cho phép trong mỗi "chunk" nội dung.
            Mặc định là 350.

    Returns:
        Một danh sách các từ điển (list of dicts), trong đó mỗi từ điển là một "chunk"
        thông tin đã được tạo. Mỗi "chunk" bao gồm 'chunk_id', 'chunk_type',
        'index_mode', 'content', và 'metadata'.
    """
    chunks = []

    for record in faculty_records:
        source_pages = record.get("source_pages", [])
        faculty_name = record.get("faculty_or_unit_name", "")

        content = build_directory_content(
            title=f"Khoa/Tổ: {faculty_name}",
            raw_text=record.get("raw_text", ""),
            source_pages=source_pages,
        )

        parts = split_long_directory_content(content, max_tokens=max_tokens)

        for idx, part in enumerate(parts, start=1):
            suffix = f"_part_{idx}" if len(parts) > 1 else ""

            chunks.append(
                create_chunk(
                    chunk_id=f"faculty_{record['record_id']}{suffix}",
                    chunk_type="faculty_program_directory",
                    index_mode="semantic",
                    content=part,
                    metadata={
                        "source_type": "faculty_program_directory",
                        "record_id": record.get("record_id"),
                        "faculty_or_unit_name": faculty_name,
                        "source_pages": source_pages,
                        "needs_manual_review": record.get("needs_manual_review"),
                        "split_from_record": len(parts) > 1,
                        "part_index": idx,
                        "total_parts": len(parts),
                    },
                )
            )

    return chunks


def build_reference_chunks(
    reference_records: list[dict[str, Any]],
    max_tokens: int = 350,
) -> list[dict[str, Any]]:
    """Tạo các "chunk" (khối thông tin) từ danh sách các bản ghi tham khảo.

    Hàm này tương tự như các hàm `build_office_chunks` và `build_faculty_chunks`,
    nhưng được sử dụng cho các bản ghi thông tin tham khảo chung. Nó xử lý từng
    bản ghi, tạo nội dung, chia nhỏ nếu cần, và chuyển đổi thành các "chunk"
    có cấu trúc với metadata phù hợp.

    Args:
        reference_records: Một danh sách các từ điển (list of dicts), mỗi từ điển
            đại diện cho một bản ghi thông tin tham khảo.
            Mỗi bản ghi cần có ít nhất 'record_id', 'name', 'raw_text',
            và 'source_pages'.
        max_tokens: Số lượng token tối đa cho phép trong mỗi "chunk" nội dung.
            Mặc định là 350.

    Returns:
        Một danh sách các từ điển (list of dicts), trong đó mỗi từ điển là một "chunk"
        thông tin đã được tạo. Mỗi "chunk" bao gồm 'chunk_id', 'chunk_type',
        'index_mode', 'content', và 'metadata'.
    """
    chunks = []

    for record in reference_records:
        source_pages = record.get("source_pages", [])

        content = build_directory_content(
            title=f"Trang tham khảo: {record.get('name')}",
            raw_text=record.get("raw_text", ""),
            source_pages=source_pages,
        )

        parts = split_long_directory_content(content, max_tokens=max_tokens)

        for idx, part in enumerate(parts, start=1):
            suffix = f"_part_{idx}" if len(parts) > 1 else ""

            chunks.append(
                create_chunk(
                    chunk_id=f"reference_{record['record_id']}{suffix}",
                    chunk_type="reference_directory",
                    index_mode="semantic",
                    content=part,
                    metadata={
                        "source_type": "reference_directory",
                        "record_id": record.get("record_id"),
                        "name": record.get("name"),
                        "source_pages": source_pages,
                        "split_from_record": len(parts) > 1,
                        "part_index": idx,
                        "total_parts": len(parts),
                    },
                )
            )

    return chunks


def build_directory_chunks(
    office_records: list[dict[str, Any]],
    faculty_records: list[dict[str, Any]],
    reference_records: list[dict[str, Any]],
    directory_max_tokens: int = 350,
) -> list[dict[str, Any]]:
    """Tạo tất cả các "chunk" thư mục từ các loại bản ghi khác nhau.

    Hàm này là một hàm tổng hợp, gọi các hàm tạo "chunk" riêng biệt
    cho các bản ghi văn phòng, khoa/tổ và tham khảo. Sau đó, nó kết hợp
    tất cả các "chunk" đã tạo thành một danh sách duy nhất.

    Args:
        office_records: Một danh sách các từ điển (list of dicts) chứa
            thông tin về các văn phòng/phòng ban.
        faculty_records: Một danh sách các từ điển (list of dicts) chứa
            thông tin về các khoa/tổ.
        reference_records: Một danh sách các từ điển (list of dicts) chứa
            thông tin tham khảo chung.
        directory_max_tokens: Số lượng token tối đa cho phép trong mỗi "chunk"
            nội dung cho tất cả các loại thư mục. Mặc định là 350.

    Returns:
        Một danh sách các từ điển (list of dicts) chứa tất cả các "chunk"
        đã được tạo từ cả ba loại bản ghi (văn phòng, khoa/tổ, tham khảo).
    """
    return (
        build_office_chunks(office_records, max_tokens=directory_max_tokens)
        + build_faculty_chunks(faculty_records, max_tokens=directory_max_tokens)
        + build_reference_chunks(reference_records, max_tokens=directory_max_tokens)
    )