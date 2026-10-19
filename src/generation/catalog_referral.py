"""Refer the parts of an answer that have no evidence to a unit from the student-service catalog.

The composer lists, on one machine-read line at the end of its answer, the task
ids whose asked point it found no evidence for (prompt v3.44). That line is
removed before the student sees the answer. For each listed task the existing
directory selector picks, from the cohort's closed service catalog, the unit
that does the asked work; the referral is appended as a separate, labelled
block whose contact details come from the catalog record, never from the
composer. The selector is asked once, without its thinking retry, while the
composer writes, so the referral adds no wait. Anything but a match (ambiguous,
none, unavailable) gives no referral and no clarification.

The task coverage signal cannot drive this: a task is "uncovered" only when
retrieval returns nothing, which happened for 0 of 355 composed units on
official_v4 run Q, while the parts this is for are covered by passages that do
not answer them (data/eval/official_v4/SPEC.md, run S).
"""
from __future__ import annotations

import contextvars
import json
import re
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from src.common.cohort import is_validated_source_applicable, normalize_cohort
from src.retrieval.core.directory_selector import MATCH, DirectorySelector, _ask, render_prompt

UNSUPPORTED_MARKER = re.compile(r"\[\[\s*CHUA_CAN_CU\s*:([^\]]*)\]\]")
# The start of a marker the stream must hold back until it is complete, and a
# marker the stream ended inside of.
MARKER_OPENING = "[["
UNCLOSED_MARKER = re.compile(r"\[\[[^\]\n]*\]?\s*$")

_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="catalog-referral")


def take_unsupported_marker(text: str) -> tuple[str, list[str]]:
    """The text with every complete marker removed, and the task ids they list (in order, once).

    Whitespace is left as it is, so a streamed fragment keeps its spacing.
    """
    task_ids: list[str] = []
    for match in UNSUPPORTED_MARKER.finditer(text):
        for task_id in match.group(1).split(","):
            task_id = task_id.strip()
            if task_id and task_id not in task_ids:
                task_ids.append(task_id)
    return UNSUPPORTED_MARKER.sub("", text), task_ids


def split_unsupported_marker(text: str) -> tuple[str, list[str]]:
    """The whole answer without its marker lines, and the task ids they list."""
    cleaned, task_ids = take_unsupported_marker(text)
    cleaned = UNCLOSED_MARKER.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip(), task_ids


def referable_tasks(retrieval_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Tasks answered from regulation text in at least one cohort, with that cohort."""
    tasks = []
    for task in (retrieval_result or {}).get("task_results") or []:
        modes = task.get("execution_mode_by_cohort") or {}
        cohort = next((c for c, mode in modes.items() if mode == "rag"), None)
        if cohort is None and task.get("mode") == "rag":
            cohort = next(iter(task.get("cohorts") or []), None)
        if cohort is not None and task.get("task_id") and task.get("question"):
            tasks.append({"task_id": str(task["task_id"]), "question": str(task["question"]), "cohort": cohort})
    return tasks


def select_referral(
    selector: DirectorySelector, catalog: list[dict[str, Any]], *, task_question: str, query: str, cohort: str,
) -> dict[str, Any]:
    """Ask the selector once which unit is in charge of the asked matter (its referral wording)."""
    normalized = normalize_cohort(cohort)
    records = [item for item in catalog if is_validated_source_applicable(item, normalized)]
    if not records:
        return {"status": "none", "reason": "empty_catalog"}
    question = json.dumps({"câu hỏi gốc": query, "ý chưa có căn cứ": task_question}, ensure_ascii=False)
    prompt, ids = render_prompt("service_referral", task_question, records, question=question)
    selection = _ask(selector.client, "service_referral", prompt, ids, "llm_selector")
    if selection.status != MATCH or not selection.records:
        return {"status": selection.status, "reply": selection.reply, "cohort": cohort}
    record = selection.records[0]
    return {"status": MATCH, "service_id": record.get("service_id"), "unit_name": record.get("unit_name"),
            "record": record, "reply": selection.reply, "cohort": cohort}


def start_referrals(
    selector: DirectorySelector | None, catalog: list[dict[str, Any]], retrieval_result: dict[str, Any] | None,
    query: str,
) -> dict[str, Future]:
    """Start one selector call per referable task; the futures are read after the composer."""
    if selector is None:
        return {}
    futures = {}
    for task in referable_tasks(retrieval_result):
        context = contextvars.copy_context()  # keeps the request's usage tracker
        futures[task["task_id"]] = _POOL.submit(
            context.run, select_referral, selector, catalog,
            task_question=task["question"], query=query, cohort=task["cohort"],
        )
    return futures


def collect_referrals(futures: dict[str, Future], task_ids: list[str], timeout: float = 20.0) -> list[dict[str, Any]]:
    """The decisions for the flagged tasks; a task the selector could not decide gets none."""
    decisions = []
    for task_id in task_ids:
        future = futures.get(task_id)
        if future is None:
            decisions.append({"task_id": task_id, "status": "not_referable"})
            continue
        try:
            decision = future.result(timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - a failed lookup only means no referral
            decision = {"status": "unavailable", "reason": type(exc).__name__}
        decisions.append({"task_id": task_id, **decision})
    return decisions


def _contact_lines(record: dict[str, Any]) -> list[str]:
    phones = list(record.get("phones") or [])
    internal = list(record.get("internal_numbers") or [])
    lines = []
    if phones:
        phone = ", ".join(phones)
        if internal:
            phone += ", số máy nội bộ " + ", ".join(internal)
        lines.append(f"- Điện thoại: {phone}")
    if record.get("emails"):
        lines.append("- Email: " + ", ".join(record["emails"]))
    if record.get("websites"):
        lines.append("- Website: " + ", ".join(record["websites"]))
    if record.get("office"):
        lines.append(f"- Văn phòng: {str(record['office']).strip()}")
    return lines


def render_referrals(decisions: list[dict[str, Any]]) -> str:
    """One labelled block per unit the selector matched; "" when none."""
    blocks, seen = [], set()
    for decision in decisions:
        record = decision.get("record")
        if decision.get("status") != MATCH or not record or decision.get("unit_name") in seen:
            continue
        seen.add(decision.get("unit_name"))
        lines = [f"**Gợi ý nơi liên hệ:** Sổ tay không quy định về ý này; bạn có thể liên hệ "
                 f"**{record.get('unit_name')}** (phụ trách: {str(record.get('service') or '').strip()})."]
        blocks.append("\n".join(lines + _contact_lines(record)))
    return "\n\n".join(blocks)


def composed_task_ids(context_used: str) -> list[str]:
    """The task ids of every unit the composer was given (any mode), in packet order."""
    try:
        units = json.loads(context_used or "{}").get("units") or []
    except (ValueError, AttributeError):
        return []
    task_ids: list[str] = []
    for unit in units:
        task_id = str(unit.get("task_id") or "")
        if task_id and task_id not in task_ids:
            task_ids.append(task_id)
    return task_ids


def template_applies(composed: list[str], unsupported: list[str], decisions: list[dict[str, Any]]) -> bool:
    """True when the composer marked every task it composed and each has a catalog match.

    Then nothing in the composed answer is supported, and the fixed template
    replaces it (owner, 2026-10-19): passages that were retrieved but do not
    answer still carried other units' contacts into the body.
    """
    if not composed or not set(composed) <= set(unsupported):
        return False
    matched = {d.get("task_id") for d in decisions if d.get("status") == MATCH and d.get("record")}
    return set(composed) <= matched


def template_possible(futures: dict[str, Future], composed: list[str], timeout: float = 20.0) -> bool:
    """Whether the template could apply once the composer finishes: every composed task has a match.

    The stream asks this before releasing any text, so a body the template
    would replace is never shown.
    """
    if not composed or any(task_id not in futures for task_id in composed):
        return False
    decisions = collect_referrals(futures, composed, timeout=timeout)
    return all(d.get("status") == MATCH and d.get("record") for d in decisions)


def render_template(decisions: list[dict[str, Any]]) -> str:
    """The whole answer when no composed task has evidence: the handbook, then one block per unit."""
    from .prompt_builder import handbook_label

    matched = [d for d in decisions if d.get("status") == MATCH and d.get("record")]
    cohort = str(matched[0].get("cohort") or "") if matched else ""
    handbook = handbook_label(cohort) or "Sổ tay sinh viên"
    blocks, seen = [f"{handbook} không quy định về việc này."], set()
    for decision in matched:
        record = decision["record"]
        if record.get("unit_name") in seen:
            continue
        seen.add(record.get("unit_name"))
        lines = [f"Bạn có thể liên hệ **{record.get('unit_name')}** "
                 f"(phụ trách: {str(record.get('service') or '').strip()}):"]
        blocks.append("\n".join(lines + _contact_lines(record)))
    return "\n\n".join(blocks)


def public_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The decisions without the catalog record, for the response and the trace."""
    return [{key: value for key, value in decision.items() if key != "record"} for decision in decisions]
