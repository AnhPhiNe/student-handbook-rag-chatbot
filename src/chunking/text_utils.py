import re


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
