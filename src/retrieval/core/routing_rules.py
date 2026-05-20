from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal runtimes.
    yaml = None


DEFAULT_RULES_PATH = Path("configs/query_routing_rules.yaml")

FALLBACK_RULES: dict[str, list[str]] = {
    "form_signal": ["mẫu đơn", "đơn xin", "biểu mẫu", "phiếu", "form", "mẫu"],
    "regulation_signal": ["điều kiện", "quy định", "thủ tục", "khi nào"],
    "contact_question": ["email", "số điện thoại", "điện thoại", "website", "địa chỉ", "liên hệ", "ở đâu"],
    "ktx_signal": ["ký túc xá", "kí túc xá", "ktx", "nội trú", "vào ở"],
    "faculty_signal": ["khoa", "ngành", "tổ trực thuộc", "chuyên ngành"],
    "explicit_office_entity": ["phòng", "ban", "trung tâm", "thư viện"],
    "calculation_signal": ["tính", "tính giúp", "bao nhiêu nếu"],
    "gpa_signal": ["gpa", "điểm trung bình", "tbc"],
    "scholarship_score_signal": ["điểm học bổng"],
    "ktx_form_signal": ["đơn", "mẫu", "giấy", "hồ sơ"],
    "ktx_procedure_signal": ["quy trình", "tiêu chí", "ưu tiên", "điều kiện", "thủ tục", "xét", "hội đồng"],
    "mixed_form_signal": ["mẫu đơn", "đơn", "biểu mẫu", "giấy xác nhận"],
    "mixed_regulation_signal": ["điều kiện", "quy định", "thủ tục", "cần đáp ứng"],
    "mixed_office_signal": ["liên hệ", "phòng nào", "email", "số điện thoại", "địa chỉ"],
    "pass_fail_regulation_signal": ["qua môn", "đạt học phần", "rớt môn", "trượt môn", "học lại"],
    "score_lookup_signal": ["quy đổi", "xếp loại", "loại gì", "học lực", "thang điểm 4", "thang 4", "rèn luyện", "điểm chữ"],
}


@lru_cache(maxsize=1)
def load_query_routing_rules(path: str | Path = DEFAULT_RULES_PATH) -> dict[str, list[str]]:
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
