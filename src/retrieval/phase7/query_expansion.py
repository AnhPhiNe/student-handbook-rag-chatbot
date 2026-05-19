import re
from typing import Any


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("–", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def expand_query(
    query: str,
    expansion_rules: list[dict[str, Any]],
) -> str:
    q = normalize_text(query)
    additions = []

    for rule in expansion_rules:
        triggers = [normalize_text(t) for t in rule.get("trigger", [])]

        if any(trigger in q for trigger in triggers):
            additions.extend(rule.get("expand_to", []))

    additions = list(dict.fromkeys(additions))

    if not additions:
        return query

    return query + " " + " ".join(additions)