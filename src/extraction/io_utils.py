import json
from pathlib import Path
from typing import Any

import yaml


def load_json(path: Path) -> Any:
    """Tải dữ liệu từ một tệp JSON.

    Hàm này đọc và phân tích cú pháp (parse) nội dung của một tệp JSON
    tại đường dẫn được cung cấp, sau đó trả về dữ liệu đó.

    Args:
        path: Đối tượng Path chỉ định đường dẫn đến tệp JSON cần tải.

    Returns:
        Nội dung của tệp JSON. Kiểu dữ liệu trả về có thể là dictionary, list,
        chuỗi, số, boolean hoặc None, tùy thuộc vào nội dung của tệp JSON.

    Raises:
        FileNotFoundError: Nếu tệp JSON không tồn tại tại đường dẫn đã cho.
    """
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON file: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: Path) -> None:
    """Lưu dữ liệu vào một tệp JSON.

    Hàm này ghi dữ liệu được cung cấp vào một tệp JSON tại đường dẫn đã chỉ định.
    Nếu các thư mục cha của tệp chưa tồn tại, chúng sẽ được tạo tự động.
    Dữ liệu sẽ được định dạng đẹp (indent=2) và không mã hóa ký tự ASCII.

    Args:
        data: Dữ liệu bất kỳ (ví dụ: dictionary, list) cần lưu vào tệp JSON.
        path: Đối tượng Path chỉ định đường dẫn đầy đủ đến tệp JSON sẽ được tạo
              hoặc ghi đè.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_yaml(path: Path) -> dict[str, Any]:
    """Tải dữ liệu cấu hình từ một tệp YAML.

    Hàm này đọc và phân tích cú pháp (parse) nội dung của một tệp YAML
    tại đường dẫn được cung cấp, sau đó trả về dữ liệu đó dưới dạng một dictionary.

    Args:
        path: Đối tượng Path chỉ định đường dẫn đến tệp YAML cần tải.

    Returns:
        Một dictionary chứa nội dung của tệp YAML. Các khóa (keys) sẽ là chuỗi
        và giá trị (values) có thể là bất kỳ kiểu dữ liệu nào.

    Raises:
        FileNotFoundError: Nếu tệp YAML không tồn tại tại đường dẫn đã cho.
    """
    if not path.exists():
        raise FileNotFoundError(f"Missing YAML config: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)