"""Find the catalog records a student names: an exact name first, else an LLM
choosing from the cohort's closed list.

The LLM answers without thinking, which is fast and has never picked a wrong
record on the development cases, but it misses needs worded far from the
catalog ("in bảng điểm" for "cấp các loại giấy chứng nhận điểm"). When it
finds nothing, the same prompt is asked once more with thinking on; that
second look found those needs and still found nothing for needs the catalog
does not list (2026-09-29, docs/DESIGN_DECISIONS.md).

The LLM only returns ids from the list it was shown; every contact detail and
program fact still comes from the catalog record. A reply that is malformed,
names an unknown id or never arrives becomes "unavailable", which the lookups
turn into a clarification, never a guess.

Measured on the labeled development cases in data/eval/development/*_matching_cases.yaml
with scripts/eval_directory_matching.py.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from src.common.text import fold_text
from src.common.usage_tracker import current_tracker, utc_now

logger = logging.getLogger("student_handbook_rag.retrieval.directory_selector")

SELECTOR_PROMPT_VERSION = "directory-selector-v2-whole-question"

MATCH = "match"
AMBIGUOUS = "ambiguous"
NONE = "none"
UNAVAILABLE = "unavailable"

_NAME_RULE = (
    "Sinh viên thường gọi tên ngắn gọn: bỏ bớt chữ trong tên, dùng chữ viết tắt, hoặc gọi theo việc "
    "đơn vị phụ trách. Cách gọi chỉ hợp với một mục thì chọn mục đó; hợp với nhiều mục thì chọn "
    "ambiguous; chỉ chọn none khi không mục nào hợp với cách gọi. Không đoán điều danh sách không ghi."
)

_SERVICE_DECISIONS = """- "match": có một mục trong danh sách khớp. ids gồm đúng 1 mã, là mục sát nhất.
- "ambiguous": nhiều mục thuộc các đơn vị khác nhau đều khớp, và nội dung không cho biết là mục nào. ids gồm 2 hoặc 3 mã sát nhất.
- "none": không mục nào trong danh sách khớp. ids rỗng."""

_NAME_DECISIONS = """- "match": ids gồm mã của từng đơn vị sinh viên nhắc tới. Thường là 1 mã; gọi tên vài đơn vị thì mỗi đơn vị 1 mã.
- "ambiguous": sinh viên muốn nói một đơn vị nhưng nhiều đơn vị đều hợp, và nội dung không cho biết là đơn vị nào. ids gồm 2 hoặc 3 mã sát nhất.
- "none": không đơn vị nào trong danh sách hợp. ids rỗng."""

_PROGRAM_DECISIONS = """- "match": ids gồm mọi ngành sinh viên nhắc tới. Gọi tên một ngành thì 1 mã; gọi tên vài ngành thì các mã đó; hỏi theo một khoa hoặc một nhóm ngành thì đủ mọi ngành thuộc khoa hoặc nhóm đó.
- "ambiguous": sinh viên muốn nói một ngành nhưng nhiều ngành đều hợp, và nội dung không cho biết là ngành nào. ids gồm 2 hoặc 3 mã sát nhất.
- "none": không ngành nào trong danh sách hợp. ids rỗng."""

_PROMPT = """{task} Chỉ dựa vào danh sách dưới đây, trích từ sổ tay sinh viên.

Danh sách ({columns}):
{catalog}

Nội dung ghi ở cuối có thể là một tên gọi hoặc cả câu hỏi của sinh viên. Chỉ cần chọn mục được nhắc tới, không cần trả lời câu hỏi, nên danh sách không cần có email, số điện thoại hay địa chỉ. Với nội dung đó, trả về JSON dạng {{"decision": "...", "ids": [...]}}:
{decisions}

{rule}

{input_label}: "{value}"
"""


def _unit(record: dict[str, Any]) -> str:
    return str(record.get("unit_name") or record.get("unit") or "").strip()


def _aliases(record: dict[str, Any]) -> str:
    seen = {fold_text(_unit(record))}
    aliases = []
    for alias in record.get("aliases") or []:
        if fold_text(alias) not in seen:
            seen.add(fold_text(alias))
            aliases.append(str(alias))
    return ", ".join(aliases) or "-"


@dataclass(frozen=True)
class LookupSpec:
    """What differs between lookups: the catalog lines and the task wording."""

    task: str
    columns: str
    line: Callable[[dict[str, Any]], str]
    input_label: str
    rule: str
    decisions: str
    names: Callable[[dict[str, Any]], list[str]]
    entity: Callable[[dict[str, Any]], str]
    many: bool = False  # one text may name several entities (two offices, a faculty's programs)


LOOKUPS: dict[str, LookupSpec] = {
    "student_service": LookupSpec(
        task="Tìm công việc trong danh sách trực tiếp giải quyết nhu cầu của sinh viên.",
        columns="mã | đơn vị | công việc đơn vị làm cho sinh viên",
        line=lambda r: f"{_unit(r)} | {r.get('service')}",
        input_label="Nội dung sinh viên viết",
        rule="Không chọn một công việc chỉ vì trùng vài từ với nhu cầu, và không đoán việc mà danh sách không ghi.",
        decisions=_SERVICE_DECISIONS,
        names=lambda r: [_unit(r), str(r.get("service") or ""), *map(str, r.get("aliases") or [])],
        entity=_unit,
    ),
    "office": LookupSpec(
        task="Tìm đơn vị trong danh sách mà sinh viên đang gọi tên, bằng tên đầy đủ, tên viết tắt hoặc cách gọi khác.",
        columns="mã | tên đơn vị | tên gọi khác | việc đơn vị phụ trách",
        line=lambda r: f"{_unit(r)} | {_aliases(r)} | {'; '.join(r.get('services') or []) or '-'}",
        input_label="Nội dung sinh viên viết",
        rule=_NAME_RULE,
        decisions=_NAME_DECISIONS,
        names=lambda r: [_unit(r), *map(str, r.get("aliases") or [])],
        entity=_unit,
        many=True,
    ),
    "faculty": LookupSpec(
        task="Tìm khoa hoặc tổ trong danh sách mà sinh viên đang gọi tên, bằng tên đầy đủ, tên viết tắt hoặc cách gọi khác.",
        columns="mã | tên khoa hoặc tổ | tên gọi khác",
        line=lambda r: f"{_unit(r)} | {_aliases(r)}",
        input_label="Nội dung sinh viên viết",
        rule=_NAME_RULE,
        decisions=_NAME_DECISIONS,
        names=lambda r: [_unit(r), *map(str, r.get("aliases") or [])],
        entity=_unit,
        many=True,
    ),
    "program": LookupSpec(
        task="Tìm các ngành trong danh sách mà sinh viên đang nhắc tới.",
        columns="mã | ngành | khoa phụ trách",
        line=lambda r: f"{r.get('program_name')} | {r.get('faculty_name')}",
        input_label="Nội dung sinh viên viết",
        rule=('Sinh viên thường gọi tên ngắn gọn: bỏ bớt chữ trong tên, dùng chữ viết tắt như "SP" cho sư phạm, '
              "hoặc gọi theo khoa. Chỉ chọn none khi không ngành nào hợp với cách gọi. "
              "Không đoán điều danh sách không ghi."),
        decisions=_PROGRAM_DECISIONS,
        names=lambda r: [str(r.get("program_name") or "")],
        entity=lambda r: fold_text(r.get("program_name")),
        many=True,
    ),
}


@dataclass(frozen=True)
class Selection:
    """The records a text names, and how they were found (kept in results for logs)."""

    status: str  # match | ambiguous | none | unavailable
    records: list[dict[str, Any]] = field(default_factory=list)
    method: str = "catalog_exact"  # catalog_exact | llm_selector | llm_selector_thinking
    reply: str | None = None  # the raw LLM reply, for logs

    def trace(self) -> dict[str, Any]:
        trace = {"status": self.status, "method": self.method, "prompt_version": SELECTOR_PROMPT_VERSION}
        if self.reply is not None:
            trace["reply"] = self.reply
        return trace


def render_prompt(lookup_type: str, value: str, records: list[dict[str, Any]]) -> tuple[str, dict[str, dict[str, Any]]]:
    """The selector prompt and the id -> record map it shows."""
    spec = LOOKUPS[lookup_type]
    ids = {f"S{index + 1:02d}": record for index, record in enumerate(records)}
    prompt = _PROMPT.format(
        task=spec.task, columns=spec.columns,
        catalog="\n".join(f"{record_id} | {spec.line(record)}" for record_id, record in ids.items()),
        decisions=spec.decisions, rule=spec.rule, input_label=spec.input_label, value=value,
    )
    return prompt, ids


def exact_matches(lookup_type: str, value: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Records of the one entity whose name or alias equals the text (after folding).

    A text equal to names of several entities (a shared alias) is not exact.
    """
    spec = LOOKUPS[lookup_type]
    folded = fold_text(value)
    if not folded:
        return []
    hits = [r for r in records if folded in {fold_text(name) for name in spec.names(r) if name}]
    return hits if len({spec.entity(r) for r in hits}) == 1 else []


def _reply_object(reply: str) -> dict[str, Any] | None:
    """The first JSON object in the reply that carries a decision.

    With thinking on, DeepSeek sometimes writes the requested format,
    {"type": "json_object"}, before the answer itself.
    """
    decoder = json.JSONDecoder()
    start = reply.find("{")
    while start != -1:
        try:
            value, end = decoder.raw_decode(reply, start)
        except ValueError:
            end = start + 1
        else:
            if isinstance(value, dict) and "decision" in value:
                return value
        start = reply.find("{", end)
    return None


def parse_reply(
    lookup_type: str, reply: str, ids: dict[str, dict[str, Any]], method: str = "llm_selector"
) -> Selection:
    """Validate the LLM reply against the ids it was shown."""
    spec = LOOKUPS[lookup_type]
    unavailable = Selection(UNAVAILABLE, method=method, reply=reply)
    parsed = _reply_object(reply)
    if parsed is None:
        return unavailable
    decision, chosen = parsed.get("decision"), parsed.get("ids")
    if not isinstance(chosen, list) or any(not isinstance(c, str) or c not in ids for c in chosen):
        return unavailable
    records = list({c: ids[c] for c in chosen}.values())
    entities = {spec.entity(r) for r in records}
    if decision == NONE and not records:
        return Selection(NONE, method=method, reply=reply)
    if decision == MATCH and records and (spec.many or len(entities) == 1):
        return Selection(MATCH, records, method=method, reply=reply)
    if decision == AMBIGUOUS and len(records) >= 2:
        status = MATCH if len(entities) == 1 else AMBIGUOUS
        return Selection(status, records, method=method, reply=reply)
    return unavailable


class DirectorySelector:
    """Exact name first; otherwise an LLM call over the cohort's closed list,
    asked again with thinking on when it finds nothing.

    Each client's `generate(prompt)` returns {"ok": bool, "text": str, ...}, as
    the composer clients do; both should be configured to return one JSON
    object. Without `thinking_client` a "none" is final.
    """

    def __init__(self, client: Any, thinking_client: Any | None = None) -> None:
        self.client = client
        self.thinking_client = thinking_client

    def select(self, lookup_type: str, value: str, records: list[dict[str, Any]]) -> Selection:
        exact = exact_matches(lookup_type, value, records)
        if exact:
            return Selection(MATCH, exact)
        if not records or not fold_text(value):
            return Selection(NONE)
        prompt, ids = render_prompt(lookup_type, value, records)
        selection = _ask(self.client, lookup_type, prompt, ids, "llm_selector")
        if selection.status != NONE or self.thinking_client is None:
            return selection
        second = _ask(self.thinking_client, lookup_type, prompt, ids, "llm_selector_thinking")
        if second.status == UNAVAILABLE:
            # A failed second look leaves the first answer, as before it existed.
            logger.warning("directory_selector_thinking_failed", extra={"reply": second.reply})
            return selection
        return second


def _ask(client: Any, lookup_type: str, prompt: str, ids: dict[str, dict[str, Any]], method: str) -> Selection:
    started = utc_now()
    response: dict[str, Any] = {}
    try:
        response = client.generate(prompt)
    except Exception as exc:  # noqa: BLE001 - any failure asks the student instead
        selection = Selection(UNAVAILABLE, method=method, reply=f"error: {type(exc).__name__}")
    else:
        if not response.get("ok"):
            message = response.get("error_message")
            reply = f"error: {response.get('error_type')}" + (f": {message}" if message else "")
            selection = Selection(UNAVAILABLE, method=method, reply=reply)
        else:
            selection = parse_reply(lookup_type, str(response.get("text") or ""), ids, method)
    _record_call(client, response, started, lookup_type, selection)
    return selection


def _record_call(
    client: Any, response: dict[str, Any], started: str, lookup_type: str, selection: Selection,
) -> None:
    """Add this LLM call to the current request's usage, for tracing and cost."""
    tracker = current_tracker()
    if tracker is None:
        return
    thinking = selection.method == "llm_selector_thinking"
    tracker.record_call(
        "Directory Selector (thinking)" if thinking else "Directory Selector",
        model=str(response.get("model_used") or getattr(client, "model_name", "") or ""),
        usage=response.get("usage"),
        start_time=started,
        end_time=utc_now(),
        metadata={
            "provider": str(getattr(client, "provider_label", "") or "").lower() or None,
            "key_fingerprint": response.get("key_fingerprint"),
            "lookup_type": lookup_type,
            "decision": selection.status,
            "chosen": sorted({LOOKUPS[lookup_type].entity(r) for r in selection.records})[:3],
            "reply": selection.reply,
            "prompt_version": SELECTOR_PROMPT_VERSION,
        },
    )


def select_records(
    selector: DirectorySelector | None, lookup_type: str, value: str, records: list[dict[str, Any]]
) -> Selection:
    """Select with the LLM when configured; without one only exact names match."""
    if selector is not None:
        return selector.select(lookup_type, value, records)
    if not records:
        return Selection(NONE)
    exact = exact_matches(lookup_type, value, records)
    return Selection(MATCH, exact) if exact else Selection(UNAVAILABLE)
