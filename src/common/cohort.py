import re


COHORT_GROUPS = {
    "K48": "K48-K49",
    "K49": "K48-K49",
    "K50": "K50-K51",
    "K51": "K50-K51",
}


def normalize_cohort(cohort: str | None) -> str | None:
    if not cohort:
        return None

    value = cohort.strip().upper().replace("_", "-")
    if value in {"K48-K49", "K50-K51"}:
        return value

    compact = value.replace(" ", "")
    if compact in {"48-49", "K48K49"}:
        return "K48-K49"
    if compact in {"50-51", "K50K51"}:
        return "K50-K51"

    return COHORT_GROUPS.get(value, value)


def resolve_cohort_from_query(query: str, fallback: str | None = None) -> str | None:
    cohort = normalize_cohort(fallback)
    match = re.search(r"(?i)\bk(?:h[oó][aá])?[\s:._-]*k?[\s:._-]*(\d{2})\b", query)
    if match:
        return normalize_cohort(f"K{match.group(1)}")
    return cohort
