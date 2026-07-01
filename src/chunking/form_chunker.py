from typing import Any

from .chunk_schema import create_chunk
from .text_utils import format_source_pages, join_non_empty


def fields_to_text(fields: list[str]) -> str:
    """Chuyển đổi một danh sách các tên trường (field) thành một chuỗi văn bản dễ đọc.

    Hàm này nhận vào một danh sách các chuỗi, mỗi chuỗi là tên của một trường thông tin.
    Nếu danh sách rỗng, nó sẽ trả về một thông báo mặc định.
    Nếu không, nó sẽ nối các tên trường lại với nhau bằng dấu phẩy và khoảng trắng.

    Args:
        fields: Một danh sách các chuỗi, mỗi chuỗi là tên của một trường thông tin.
                Ví dụ: `["Họ và tên", "Ngày sinh", "Địa chỉ"]`.

    Returns:
        Một chuỗi văn bản chứa các tên trường được nối lại, hoặc một thông báo
        nếu không có trường nào được cung cấp.
        Ví dụ: "Họ và tên, Ngày sinh, Địa chỉ" hoặc "Không phát hiện field rõ ràng."
    """
    if not fields:
        return "Không phát hiện field rõ ràng."

    return ", ".join(fields)


def infer_form_purpose(form_name: str) -> str:
    """Suy luận mục đích của một biểu mẫu dựa trên tên của nó.

    Hàm này phân tích tên của biểu mẫu (không phân biệt chữ hoa chữ thường)
    để xác định mục đích chính của biểu mẫu đó. Nó tìm kiếm các từ khóa
    nhất định trong tên để đưa ra mô tả mục đích cụ thể.
    Nếu không tìm thấy từ khóa nào, nó sẽ trả về một mục đích chung.

    Args:
        form_name: Một chuỗi chứa tên của biểu mẫu.
                   Ví dụ: "Đơn xin tạm nghỉ học", "Biểu mẫu đăng ký ký túc xá".

    Returns:
        Một chuỗi mô tả mục đích của biểu mẫu một cách dễ hiểu.
        Ví dụ: "Dùng khi sinh viên muốn xin tạm nghỉ học."
        hoặc "Biểu mẫu phục vụ thủ tục sinh viên."
    """
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
    """Xây dựng các "chunk" (đoạn thông tin) từ danh sách các biểu mẫu.

    Hàm này duyệt qua một danh sách các biểu mẫu, mỗi biểu mẫu là một từ điển
    chứa thông tin chi tiết. Với mỗi biểu mẫu, nó sẽ tạo ra một "chunk" thông tin
    đã được định dạng sẵn. Mỗi chunk bao gồm nội dung mô tả biểu mẫu (tên, mục đích,
    các trường phát hiện, nguồn) và các siêu dữ liệu (metadata) liên quan.
    Các chunk này thường được dùng để lưu trữ hoặc tìm kiếm thông tin.

    Args:
        forms: Một danh sách các từ điển, mỗi từ điển đại diện cho một biểu mẫu.
               Mỗi từ điển có thể chứa các khóa như "source_pages", "form_name",
               "required_fields_detected", "form_id", "review_status".
               Ví dụ:
               ```
               [
                   {
                       "form_id": "123",
                       "form_name": "Đơn xin tạm nghỉ học",
                       "source_pages": [1, 2],
                       "required_fields_detected": ["Họ và tên", "Lý do"],
                       "review_status": "approved"
                   },
                   # ... các biểu mẫu khác
               ]
               ```

    Returns:
        Một danh sách các từ điển, mỗi từ điển là một "chunk" thông tin đã được tạo.
        Mỗi chunk sẽ có cấu trúc như sau:
        ```
        {
            "chunk_id": "form_123",
            "chunk_type": "form",
            "index_mode": "semantic",
            "content": "Biểu mẫu: Đơn xin tạm nghỉ học. Mục đích: Dùng khi sinh viên muốn xin tạm nghỉ học. ...",
            "metadata": {
                "source_type": "form_template",
                "form_id": "123",
                "form_name": "Đơn xin tạm nghỉ học",
                "source_pages": [1, 2],
                "review_status": "approved",
                "raw_text_available": True
            }
        }
        ```
    """
    chunks = []

    for form in forms:
        source_pages = form.get("source_pages", [])
        form_name = form.get("form_name", "")

        # Tạo nội dung chính cho chunk, bao gồm tên biểu mẫu, mục đích, các trường và nguồn.
        content = join_non_empty(
            [
                f"Biểu mẫu: {form_name}",
                f"Mục đích: {infer_form_purpose(form_name)}",
                f"Thông tin/field phát hiện: {fields_to_text(form.get('required_fields_detected', []))}",
                f"Nguồn: {format_source_pages(source_pages)}",
                "Ghi chú: raw_text biểu mẫu được lưu riêng để hiển thị khi cần.",
            ]
        )

        # Thêm chunk mới vào danh sách
        chunks.append(
            create_chunk(
                chunk_id=f"form_{form['form_id']}",  # ID duy nhất cho chunk này
                chunk_type="form",  # Loại chunk là "form"
                index_mode="structured",  # Chỉ lookup metadata, không embed toàn văn biểu mẫu
                content=content,  # Nội dung đã tạo ở trên
                metadata={  # Các thông tin bổ sung về biểu mẫu
                    "source_type": "form_template",
                    "content_mode": "structured_only",
                    "form_id": form.get("form_id"),
                    "form_name": form_name,
                    "source_pages": source_pages,
                    "review_status": form.get("review_status"),
                    "raw_text_available": True,  # Cho biết có văn bản gốc của biểu mẫu hay không
                },
            )
        )

    return chunks
