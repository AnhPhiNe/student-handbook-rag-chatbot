import re
from typing import Any


def normalize_text(text: str) -> str:
    """Làm sạch một chuỗi văn bản bằng cách chuẩn hóa các khoảng trắng và ký tự xuống dòng.

    Hàm này thực hiện các bước sau để làm sạch văn bản:
    1. Thay thế ký tự khoảng trắng không ngắt dòng (non-breaking space) bằng khoảng trắng thông thường.
    2. Thay thế nhiều khoảng trắng hoặc tab liên tiếp bằng một khoảng trắng duy nhất.
    3. Giảm số lượng ký tự xuống dòng liên tiếp (nếu có 3 hoặc nhiều hơn) thành hai ký tự xuống dòng.
    4. Xóa bỏ khoảng trắng ở đầu và cuối chuỗi.

    Args:
        text: Chuỗi văn bản đầu vào cần được làm sạch.

    Returns:
        Chuỗi văn bản đã được làm sạch và chuẩn hóa.
    """
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def join_non_empty(parts: list[str], sep: str = "\n") -> str:
    """Nối các chuỗi không rỗng từ một danh sách thành một chuỗi duy nhất.

    Hàm này sẽ duyệt qua danh sách các chuỗi, loại bỏ các chuỗi rỗng hoặc chỉ chứa khoảng trắng,
    sau đó nối các chuỗi còn lại bằng một ký tự phân tách.

    Args:
        parts: Một danh sách các chuỗi (ví dụ: ['phần 1', '', 'phần 2 ']).
        sep: Ký tự hoặc chuỗi dùng để phân tách các phần tử khi nối (mặc định là xuống dòng '\\n').

    Returns:
        Một chuỗi duy nhất được tạo thành từ các phần tử không rỗng trong danh sách,
        được phân tách bởi `sep`.
    """
    return sep.join([part.strip() for part in parts if part and part.strip()])


def format_source_pages(pages: list[int]) -> str:
    """Định dạng một danh sách các số trang thành một chuỗi dễ đọc.

    Hàm này sẽ chuyển đổi một danh sách các số trang thành một định dạng chuỗi thân thiện với người dùng.
    Ví dụ:
    - Nếu danh sách rỗng, trả về "Không rõ trang".
    - Nếu có một trang, trả về "Trang X".
    - Nếu có nhiều trang, trả về "Trang X-Y" (với X là trang nhỏ nhất và Y là trang lớn nhất).

    Args:
        pages: Một danh sách các số nguyên đại diện cho các số trang (ví dụ: [1, 5, 3]).

    Returns:
        Một chuỗi mô tả các trang đã được định dạng (ví dụ: "Trang 1", "Trang 1-5", "Không rõ trang").
    """
    if not pages:
        return "Không rõ trang"

    if len(pages) == 1:
        return f"Trang {pages[0]}"

    return f"Trang {min(pages)}-{max(pages)}"


def source_page_range(start: int, end: int) -> list[int]:
    """Tạo một danh sách các số nguyên đại diện cho một phạm vi trang.

    Hàm này sẽ tạo ra một danh sách các số trang liên tiếp từ trang bắt đầu đến trang kết thúc (bao gồm cả trang kết thúc).

    Args:
        start: Số nguyên đại diện cho trang bắt đầu của phạm vi.
        end: Số nguyên đại diện cho trang kết thúc của phạm vi.

    Returns:
        Một danh sách các số nguyên, bao gồm tất cả các trang từ `start` đến `end`.
        Ví dụ: `source_page_range(1, 3)` sẽ trả về `[1, 2, 3]`.
    """
    return list(range(start, end + 1))


def get_source_pages_from_item(item: dict[str, Any]) -> list[int]:
    """Trích xuất danh sách các số trang từ một đối tượng (thường là một từ điển).

    Hàm này cố gắng tìm thông tin về các số trang trong đối tượng `item` theo thứ tự ưu tiên:
    1. Kiểm tra khóa 'source_pages'.
    2. Nếu không có 'source_pages', kiểm tra các khóa 'page_start' và 'page_end' để tạo phạm vi trang.
    Nếu không tìm thấy thông tin trang nào, hàm sẽ trả về một danh sách rỗng.

    Args:
        item: Một từ điển hoặc đối tượng tương tự từ điển, có thể chứa các khóa
              'source_pages' (danh sách số nguyên) hoặc 'page_start' (số nguyên)
              và 'page_end' (số nguyên).

    Returns:
        Một danh sách các số nguyên đại diện cho các số trang.
        Trả về danh sách rỗng nếu không tìm thấy thông tin trang hợp lệ.
    """
    if "source_pages" in item and item["source_pages"]:
        return item["source_pages"]

    if "page_start" in item and "page_end" in item:
        return source_page_range(item["page_start"], item["page_end"])

    return []