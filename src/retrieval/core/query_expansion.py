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
    q = normalize_text(query)
    additions = []

    for rule in expansion_rules:
        triggers = [normalize_text(t) for t in rule.get("trigger", [])]

        if any(contains_trigger(q, trigger) for trigger in triggers):
            additions.extend(rule.get("expand_to", []))

    additions = list(dict.fromkeys(additions))

    if not additions:
        return query

    return query + " " + " ".join(additions)
