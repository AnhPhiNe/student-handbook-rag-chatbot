import re
from typing import Any


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("–", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def contains_trigger(text: str, trigger: str) -> bool:
    if not trigger:
        return False
    starts_word = trigger[0].isalnum() or trigger[0] == "_"
    ends_word = trigger[-1].isalnum() or trigger[-1] == "_"
    prefix = r"(?<!\w)" if starts_word else ""
    suffix = r"(?!\w)" if ends_word else ""
    return re.search(prefix + re.escape(trigger) + suffix, text) is not None


def expand_query(
    query: str,
    expansion_rules: list[dict[str, Any]],
) -> str:
    expanded_query = query

    for rule in expansion_rules:
        triggers = [t for t in rule.get("trigger", [])]
        expand_to = rule.get("expand_to", [])
        
        if not expand_to:
            continue
            
        # Lấy từ khóa chuẩn đầu tiên để làm từ thay thế
        replacement = expand_to[0]

        for trigger in triggers:
            if not trigger:
                continue
            
            # Cấu trúc Regex để thay thế độc lập từ (case-insensitive)
            starts_word = trigger[0].isalnum() or trigger[0] == "_"
            ends_word = trigger[-1].isalnum() or trigger[-1] == "_"
            prefix = r"(?<!\w)" if starts_word else ""
            suffix = r"(?!\w)" if ends_word else ""
            
            pattern = re.compile(prefix + re.escape(trigger) + suffix, re.IGNORECASE)
            
            # Thực hiện thay thế trực tiếp vào câu hỏi
            expanded_query = pattern.sub(replacement, expanded_query)

    # Dọn dẹp khoảng trắng thừa có thể sinh ra trong quá trình replace
    expanded_query = re.sub(r"\s+", " ", expanded_query).strip()

    return expanded_query
