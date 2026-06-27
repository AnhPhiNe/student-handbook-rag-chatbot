import json
from pathlib import Path
from typing import Any

import yaml


def load_json(path: Path) -> Any:
    """Tải dữ liệu từ một tệp JSON.

    Hàm này đọc nội dung của một tệp JSON từ đường dẫn đã cho và chuyển đổi
    nó thành một đối tượng Python (ví dụ: dictionary, list, string, number).
    Nó rất hữu ích khi bạn muốn đọc cấu hình hoặc dữ liệu đã lưu trữ
    từ một tệp JSON.

    Args:
        path (Path): Đường dẫn đến tệp JSON cần đọc.
            Ví dụ: Path("data/config.json").

    Returns:
        Any: Dữ liệu được tải từ tệp JSON. Kiểu dữ liệu cụ thể
            phụ thuộc vào nội dung của tệp JSON (có thể là dict, list, str, int, v.v.).

    Raises:
        FileNotFoundError: Nếu tệp JSON không tồn tại tại đường dẫn đã cung cấp.
    """
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON file: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: Path) -> None:
    """Lưu dữ liệu Python vào một tệp JSON.

    Hàm này nhận một đối tượng Python (ví dụ: dictionary, list) và ghi nó
    vào một tệp JSON tại đường dẫn đã cho. Nếu các thư mục cha của tệp
    chưa tồn tại, hàm sẽ tự động tạo chúng. Dữ liệu sẽ được định dạng
    đẹp mắt với thụt lề 2 khoảng trắng để dễ đọc.

    Args:
        data (Any): Dữ liệu Python cần lưu. Đây có thể là bất kỳ kiểu dữ liệu
            nào mà JSON hỗ trợ (ví dụ: dict, list, str, int, float, bool, None).
        path (Path): Đường dẫn đầy đủ đến tệp JSON sẽ được tạo hoặc ghi đè.
            Ví dụ: Path("output/result.json").

    Returns:
        None: Hàm này không trả về giá trị nào. Nó thực hiện hành động ghi tệp.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_yaml(path: Path) -> dict[str, Any]:
    """Tải dữ liệu từ một tệp YAML.

    Hàm này đọc nội dung của một tệp YAML từ đường dẫn đã cho và chuyển đổi
    nó thành một đối tượng Python, thường là một dictionary. YAML thường
    được sử dụng cho các tệp cấu hình vì cú pháp của nó dễ đọc hơn JSON
    đối với con người.

    Args:
        path (Path): Đường dẫn đến tệp YAML cần đọc.
            Ví dụ: Path("config/settings.yaml").

    Returns:
        dict[str, Any]: Dữ liệu được tải từ tệp YAML, thường là một dictionary
            với các khóa là chuỗi và giá trị có thể là bất kỳ kiểu dữ liệu nào.

    Raises:
        FileNotFoundError: Nếu tệp YAML không tồn tại tại đường dẫn đã cung cấp.
    """
    if not path.exists():
        raise FileNotFoundError(f"Missing YAML file: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)