from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any, Callable, Iterable


def safe_mean(values: Iterable[float]) -> float | None:
    items = [float(value) for value in values]
    return sum(items) / len(items) if items else None


def percentile(values: Iterable[float], percentile_value: float) -> float | None:
    items = sorted(float(value) for value in values)
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    position = (len(items) - 1) * percentile_value
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return items[lower]
    weight = position - lower
    return items[lower] * (1.0 - weight) + items[upper] * weight


def wilson_interval(
    successes: int, total: int, z: float = 1.96
) -> dict[str, float | None]:
    if total <= 0:
        return {"low": None, "high": None}
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total)
        )
        / denominator
    )
    return {"low": max(0.0, center - margin), "high": min(1.0, center + margin)}


def bootstrap_interval(
    values: list[float],
    *,
    statistic: Callable[[list[float]], float] | None = None,
    samples: int = 2000,
    seed: int = 42,
) -> dict[str, float | None]:
    if not values:
        return {"low": None, "high": None}
    statistic = statistic or (lambda items: sum(items) / len(items))
    generator = random.Random(seed)
    estimates = []
    for _ in range(samples):
        sample = [values[generator.randrange(len(values))] for _ in values]
        estimates.append(float(statistic(sample)))
    estimates.sort()
    return {
        "low": percentile(estimates, 0.025),
        "high": percentile(estimates, 0.975),
    }


def bootstrap_mean_ci(values: list[float]) -> dict[str, float | None]:
    return bootstrap_interval(values)


def retrieval_metrics(grades: list[int], k: int = 5) -> dict[str, float]:
    binary = [grade > 0 for grade in grades]
    first_relevant = next((index for index, hit in enumerate(binary) if hit), None)

    def hit_at(limit: int) -> float:
        return float(any(binary[:limit]))

    dcg = sum(
        (2**grade - 1) / math.log2(index + 2) for index, grade in enumerate(grades[:k])
    )
    ideal = sorted(grades, reverse=True)[:k]
    idcg = sum(
        (2**grade - 1) / math.log2(index + 2) for index, grade in enumerate(ideal)
    )
    return {
        "hit_at_1": hit_at(1),
        "hit_at_3": hit_at(3),
        "hit_at_5": hit_at(5),
        "reciprocal_rank": 0.0
        if first_relevant is None
        else 1.0 / (first_relevant + 1),
        "ndcg_at_5": dcg / idcg if idcg else 0.0,
    }


def summarize_numeric_rows(
    rows: list[dict[str, Any]],
    fields: list[str],
) -> dict[str, Any]:
    summary: dict[str, Any] = {"cases": len(rows)}
    for field in fields:
        values = [
            float(row[field]) for row in rows if isinstance(row.get(field), int | float)
        ]
        summary[field] = round(safe_mean(values) or 0.0, 4) if values else None
        summary[f"{field}_ci95"] = bootstrap_interval(values)
    return summary


def breakdown(
    rows: list[dict[str, Any]],
    group_field: str,
    metric_fields: list[str],
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(group_field) or "unknown")].append(row)
    return {
        name: summarize_numeric_rows(items, metric_fields)
        for name, items in sorted(groups.items())
    }
