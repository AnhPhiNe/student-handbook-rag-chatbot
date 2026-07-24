from __future__ import annotations

from functools import lru_cache
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal runtimes.
    yaml = None


DEFAULT_RULES_PATH = Path("configs/query_routing_rules.yaml")

FALLBACK_RULES: dict[str, list[str]] = {
    "document_requirement_signal": ["mau don", "don xin", "bieu mau", "phieu", "mau"],
    "regulation_signal": [
        "dieu kien",
        "quy dinh",
        "thu tuc",
        "khi nao",
        "chuyen truong",
        "chuyen nganh",
    ],
    "contact_question": [
        "email",
        "so dien thoai",
        "dien thoai",
        "website",
        "dia chi",
        "lien he",
        "o dau",
    ],
    "ktx_signal": ["ky tuc xa", "ki tuc xa", "ktx", "noi tru", "vao o"],
    "faculty_signal": ["khoa", "nganh", "to truc thuoc", "chuyen nganh"],
    "explicit_office_entity": ["phong", "ban", "trung tam", "thu vien"],
    "formula_signal": [
        "cong thuc",
        "cach tinh",
        "tinh kieu",
        "tinh kieu gi",
        "tinh nhu the nao",
        "tinh ra sao",
    ],
    "gpa_signal": ["gpa", "diem trung binh", "tbc", "tb"],
    "scholarship_score_signal": ["diem hoc bong"],
    "ktx_document_signal": ["don", "mau", "giay", "ho so"],
    "ktx_regulation_signal": [
        "quy trinh",
        "tieu chi",
        "uu tien",
        "dieu kien",
        "thu tuc",
        "xet",
        "hoi dong",
    ],
    "mixed_document_signal": ["mau don", "don", "bieu mau", "giay xac nhan", "ho so"],
    "mixed_regulation_signal": [
        "dieu kien",
        "quy dinh",
        "thu tuc",
        "can dap ung",
        "chuyen truong",
        "chuyen nganh",
    ],
    "mixed_office_signal": [
        "lien he",
        "phong nao",
        "email",
        "so dien thoai",
        "dia chi",
    ],
    "pass_fail_regulation_signal": [
        "qua mon",
        "dat hoc phan",
        "rot mon",
        "truot mon",
        "hoc lai",
    ],
    "score_lookup_signal": [
        "quy doi",
        "xep loai",
        "loai gi",
        "hoc luc",
        "thang diem 4",
        "thang 4",
        "ren luyen",
        "diem chu",
    ],
}


@lru_cache(maxsize=1)
def load_query_routing_rules(
    path: str | Path = DEFAULT_RULES_PATH,
) -> dict[str, list[str]]:
    rules_path = Path(path)
    if yaml is None or not rules_path.exists():
        return FALLBACK_RULES

    with rules_path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}

    if not isinstance(loaded, dict):
        return FALLBACK_RULES

    rules: dict[str, list[str]] = {}
    for key, fallback_values in FALLBACK_RULES.items():
        values = loaded.get(key, fallback_values)
        if not isinstance(values, list):
            values = fallback_values
        rules[key] = [str(value).strip() for value in values if str(value).strip()]

    return rules
