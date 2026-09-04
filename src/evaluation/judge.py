from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable


PINNED_JUDGE_MODEL = "openai/gpt-oss-120b"
JUDGE_METRICS = (
    "faithfulness",
    "answer_relevancy",
    "answer_correctness",
    "context_precision",
    "context_recall",
    "citation_correctness",
)


def key_fingerprint(key: str) -> str:
    """Return a non-secret identifier for one provider API key."""

    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]


def estimate_tokens(text: str) -> int:
    # Conservative for Vietnamese and JSON prompts.
    """Estimate prompt tokens for local quota accounting."""

    return max(1, math.ceil(len(text) / 3))


@dataclass(frozen=True)
class JudgeConfig:
    """Define model and quota settings for automated answer judging."""

    model_name: str = PINNED_JUDGE_MODEL
    temperature: float = 0.0
    max_output_tokens: int = 1536
    max_retries: int = 2
    request_timeout_seconds: float = 45.0
    rpm_limit_per_key: int = 30
    tpm_limit_per_key: int = 8_000
    tpd_limit_per_key: int = 200_000
    cooldown_seconds: float = 65.0
    max_quota_wait_seconds: float = 70.0
    state_path: Path = Path("data/cache/groq_judge_key_state.json")

    def __post_init__(self) -> None:
        if self.model_name != PINNED_JUDGE_MODEL:
            raise ValueError(f"V8 Judge must use exactly {PINNED_JUDGE_MODEL}")


class JudgeQuotaPool:
    """Local quota-aware LRU pool. It never stores or logs raw API keys."""

    def __init__(self, keys: list[str], config: JudgeConfig) -> None:
        if not keys:
            raise ValueError("Missing GROQ_API_KEYS for the generated-answer Judge")
        self.keys = list(dict.fromkeys(key.strip() for key in keys if key.strip()))
        self.config = config
        self._lock = threading.Lock()
        self._state = self._load_state()
        for key in self.keys:
            self._state.setdefault(key_fingerprint(key), self._new_state())
        self._save_state()

    @classmethod
    def from_environment(cls, config: JudgeConfig) -> "JudgeQuotaPool":
        """Build the judge key pool from environment configuration."""

        raw = os.environ.get("GROQ_API_KEYS") or ""
        return cls([item.strip() for item in raw.split(",") if item.strip()], config)

    def acquire(self, estimated_input_tokens: int) -> tuple[str, str]:
        """Acquire the next eligible judge API key under quota limits."""

        if estimated_input_tokens > self.config.tpm_limit_per_key:
            raise RuntimeError("judge_request_exceeds_per_key_tpm_limit")
        deadline = time.monotonic() + self.config.max_quota_wait_seconds
        while True:
            with self._lock:
                now = time.time()
                candidates: list[tuple[int, float, str, str]] = []
                daily_exhausted = 0
                next_ready: list[float] = []
                for key in self.keys:
                    fingerprint = key_fingerprint(key)
                    state = self._refresh(fingerprint, now)
                    if (
                        state["daily_tokens"] + estimated_input_tokens
                        > self.config.tpd_limit_per_key
                    ):
                        daily_exhausted += 1
                        continue
                    if state["cooldown_until"] > now:
                        next_ready.append(state["cooldown_until"] - now)
                        continue
                    requests = state["requests"]
                    recent_tokens = sum(item[1] for item in requests)
                    if len(requests) >= self.config.rpm_limit_per_key:
                        next_ready.append(max(0.05, 60 - (now - requests[0][0])))
                        continue
                    if (
                        recent_tokens + estimated_input_tokens
                        > self.config.tpm_limit_per_key
                    ):
                        next_ready.append(max(0.05, 60 - (now - requests[0][0])))
                        continue
                    candidates.append(
                        (recent_tokens, state["last_used_at"], key, fingerprint)
                    )

                if candidates:
                    _, _, key, fingerprint = min(
                        candidates, key=lambda item: (item[0], item[1])
                    )
                    state = self._state[fingerprint]
                    state["requests"].append([now, estimated_input_tokens])
                    state["daily_tokens"] += estimated_input_tokens
                    state["last_used_at"] = now
                    self._save_state()
                    return key, fingerprint
                if daily_exhausted == len(self.keys):
                    raise RuntimeError(
                        "all_groq_judge_keys_daily_token_quota_exhausted"
                    )
                wait_seconds = min(next_ready or [1.0])

            if time.monotonic() + wait_seconds > deadline:
                raise RuntimeError("all_groq_judge_keys_temporarily_limited")
            time.sleep(wait_seconds)

    def record_success(self, fingerprint: str, output_tokens: int) -> None:
        """Record successful judge usage for quota accounting."""

        with self._lock:
            state = self._state[fingerprint]
            state["failure_count"] = 0
            self._save_state()

    def record_failure(self, fingerprint: str, *, rate_limited: bool) -> None:
        """Record a failed judge request and apply cooldown."""

        with self._lock:
            state = self._state[fingerprint]
            state["failure_count"] += 1
            if rate_limited:
                state["cooldown_until"] = time.time() + self.config.cooldown_seconds
            self._save_state()

    def _refresh(self, fingerprint: str, now: float) -> dict[str, Any]:
        state = self._state.setdefault(fingerprint, self._new_state())
        state["requests"] = [
            item for item in state["requests"] if now - float(item[0]) < 60
        ]
        today = date.today().isoformat()
        if state["daily_date"] != today:
            state.update(self._new_state())
        return state

    @staticmethod
    def _new_state() -> dict[str, Any]:
        return {
            "requests": [],
            "daily_tokens": 0,
            "daily_date": date.today().isoformat(),
            "cooldown_until": 0.0,
            "last_used_at": 0.0,
            "failure_count": 0,
        }

    def _load_state(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self.config.state_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_state(self) -> None:
        self.config.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.state_path.write_text(
            json.dumps(self._state, ensure_ascii=True, indent=2), encoding="utf-8"
        )


def compact_judge_packet(
    case: dict[str, Any],
    answer_record: dict[str, Any],
    *,
    max_input_tokens: int = 5_000,
) -> dict[str, Any]:
    """Build a bounded packet while preserving required facts when available."""
    actual_citations = (
        answer_record.get("citations_used") or answer_record.get("citations") or []
    )
    citation_context = "\n".join(
        str(citation.get("content") or "")
        for citation in actual_citations[:10]
        if isinstance(citation, dict)
    )
    structured_context = _build_structured_judge_context(answer_record)
    raw_context = str(answer_record.get("context_used") or "").strip()
    # Prefer the exact authorized packet sent to Composer. Public citations are
    # capped independently and can omit task/cohort evidence in compound cases.
    authorized_packet_units = _authorized_packet_evidence_units(raw_context)
    legacy_composer_context = (
        raw_context
        if "PRIMARY SOURCES" in raw_context
        and str(case.get("cohort") or "").lower() == "general"
        else ""
    )
    fallback_context = citation_context or raw_context
    required = [str(item) for item in case.get("required_facts") or []]
    query_terms = set(re.findall(r"\w+", str(case.get("query") or "").lower()))
    answer_terms = set(
        re.findall(r"\w+", str(answer_record.get("answer") or "").lower())
    )
    sentences = _split_evidence_units(structured_context)
    if authorized_packet_units:
        sentences.extend(authorized_packet_units)
    elif legacy_composer_context:
        sentences.extend(_source_aware_composer_units(legacy_composer_context))
    else:
        sentences.extend(_split_evidence_units(fallback_context))

    selected: list[str] = []
    for fact in required:
        fact_norm = " ".join(fact.lower().split())
        match = next(
            (
                line
                for line in sentences
                if _fact_matches_context(fact_norm, " ".join(line.lower().split()))
            ),
            None,
        )
        if match and match not in selected:
            selected.append(match)

    ranked = sorted(
        sentences,
        key=lambda line: (
            bool(re.search(r"\d", line)),
            len(query_terms & set(re.findall(r"\w+", line.lower()))),
            len(answer_terms & set(re.findall(r"\w+", line.lower()))),
        ),
        reverse=True,
    )
    selected.extend(line for line in ranked if line not in selected)
    compact_citations = [
        {
            key: citation.get(key)
            for key in (
                "parent_section_id",
                "chunk_id",
                "title",
                "cohort",
                "document_id",
                "source_section",
                "chunk_type",
            )
            if citation.get(key) is not None
        }
        for citation in actual_citations[:10]
        if isinstance(citation, dict)
    ]
    packet = {
        "case_id": case["id"],
        "query": case["query"],
        "cohort": case.get("cohort"),
        "answerability": case.get("answerability"),
        "question_style": case.get("question_style"),
        "question_specificity": case.get("question_specificity"),
        "expected_answer_behavior": case.get("expected_answer_behavior"),
        "ground_truth": str(case.get("ground_truth") or "")[:4_000],
        "required_facts": required,
        "forbidden_claims": case.get("forbidden_claims") or [],
        "expected_citations": [
            {
                key: citation.get(key)
                for key in (
                    "parent_section_id",
                    "cohort",
                    "document_id",
                    "content_type",
                )
                if citation.get(key) is not None
            }
            for citation in (case.get("expected_citations") or [])[:5]
        ],
        "answer": str(answer_record.get("answer") or "")[:5_000],
        "citations": compact_citations,
        "retrieved_context": "",
    }
    max_packet_chars = max_input_tokens * 3 - 700
    fixed_chars = len(json.dumps(packet, ensure_ascii=False, separators=(",", ":")))
    budget_chars = max(900, max_packet_chars - fixed_chars)
    compact: list[str] = []
    used = 0
    for line in selected:
        if used + len(line) + 1 > budget_chars:
            remaining = budget_chars - used - 1
            if remaining >= 180:
                compact.append(line[:remaining].rsplit(" ", 1)[0])
                used = budget_chars
            continue
        compact.append(line)
        used += len(line) + 1

    packet["retrieved_context"] = "\n".join(compact)
    packet["required_facts_present_in_packet"] = [
        fact
        for fact in required
        if _fact_matches_context(
            " ".join(fact.lower().split()),
            " ".join(packet["retrieved_context"].lower().split()),
        )
    ]
    return packet


def _split_evidence_units(text: str) -> list[str]:
    return [
        part.strip() for part in re.split(r"(?<=[.!?;])\s+|\n+", text) if part.strip()
    ]


def _source_aware_composer_units(context: str) -> list[str]:
    """Keep each Composer evidence sentence attached to its source identity."""
    blocks = re.split(
        r"\n\s*---\s*\n|\n{2,}(?=\[\d+\]\s*\n)",
        context,
    )
    units: list[str] = []
    for block in blocks:
        block = block.strip()
        if not block or block == "PRIMARY SOURCES":
            continue
        source_number = re.search(r"(?m)^\[(\d+)\]\s*$", block)
        metadata: list[str] = []
        if source_number:
            metadata.append(f"Source: {source_number.group(1)}")
        for label in ("Cohort", "Title", "Document", "Pages"):
            match = re.search(rf"(?m)^{label}:\s*(.+)$", block)
            if match:
                metadata.append(f"{label}: {match.group(1).strip()}")
        prefix = " | ".join(metadata)
        content_match = re.search(r"(?m)^Content:\s*", block)
        body = block[content_match.end() :] if content_match else block
        for unit in _split_evidence_units(body):
            units.append(f"{prefix} | {unit}" if prefix else unit)
    return units


def _authorized_packet_evidence_units(context: str) -> list[str]:
    """Extract evidence text from the current task-bound Composer packet."""

    try:
        packet = json.loads(context)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(packet, dict) or not isinstance(packet.get("units"), list):
        return []

    units: list[str] = []
    for task_unit in packet["units"]:
        if not isinstance(task_unit, dict):
            continue
        task_id = str(task_unit.get("task_id") or "unknown")
        cohort = str(task_unit.get("cohort") or "default")
        for source in task_unit.get("primary_evidence") or []:
            if not isinstance(source, dict):
                continue
            source_ref = str(source.get("source_ref") or "unknown")
            title = str(source.get("title") or source.get("article_label") or "")
            prefix = f"Task: {task_id} | Cohort: {cohort} | Source: {source_ref}"
            if title:
                prefix += f" | Title: {title}"
            body = str(source.get("content") or "")
            for evidence_unit in _split_evidence_units(body):
                units.append(f"{prefix} | {evidence_unit}")
            resolved_result = source.get("resolved_result")
            if resolved_result is not None:
                units.append(
                    f"{prefix} | Resolved result: "
                    f"{_bounded_json(resolved_result, max_chars=2_000)}"
                )
        for amendment in task_unit.get("applicable_amendments") or []:
            if not isinstance(amendment, dict):
                continue
            amendment_source = str(
                amendment.get("amendment_source")
                or amendment.get("citation_source")
                or "unknown"
            )
            prefix = (
                f"Task: {task_id} | Cohort: {cohort} | Amendment: {amendment_source}"
            )
            for field in ("effective_rule", "replacement_text"):
                value = str(amendment.get(field) or "").strip()
                for evidence_unit in _split_evidence_units(value):
                    units.append(f"{prefix} | {field}: {evidence_unit}")
    return units


def _build_structured_judge_context(answer_record: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, label in (
        ("structured_result", "STRUCTURED_RESULT"),
        ("formula_result", "FORMULA_RESULT"),
        ("tool_result", "TOOL_RESULT"),
    ):
        value = answer_record.get(key)
        if not value:
            continue
        parts.append(f"{label}:\n{_bounded_json(value, max_chars=5_000)}")
    return "\n\n".join(parts)


def _bounded_json(value: Any, *, max_chars: int) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(",", 1)[0] + " ...[truncated]"


def _fact_matches_context(fact_norm: str, context_norm: str) -> bool:
    if not fact_norm or not context_norm:
        return False
    if fact_norm in context_norm:
        return True
    fact_tokens = set(re.findall(r"\w+", fact_norm))
    context_tokens = set(re.findall(r"\w+", context_norm))
    if len(fact_tokens) < 6:
        return False
    return len(fact_tokens & context_tokens) / len(fact_tokens) >= 0.82


def build_judge_prompt(packet: dict[str, Any]) -> str:
    """Build a rubric-grounded prompt for one answer evaluation."""

    return (
        "You are the sole evaluator of a Vietnamese student-handbook RAG answer. "
        "Score only from the supplied packet. Return exactly one compact JSON object, no markdown. "
        "Each metric is a number from 0 to 1. Do not reward fluent wording over factual correctness.\n"
        "Rubric: answer_correctness measures whether the final answer correctly answers the query and required facts. "
        "faithfulness only penalizes material answer claims that are absent from retrieved_context, STRUCTURED_RESULT, FORMULA_RESULT, TOOL_RESULT, or citation metadata. "
        "Treat paraphrases, concise summaries, and natural Vietnamese reformulations as supported when the same meaning is present in the packet. "
        "Do not mark unsupported_claim true merely because the exact wording differs, a harmless explanation is shorter/longer than ground truth, or retrieved_context contains extra noisy sources. "
        "citation_correctness is high when at least one main citation/source in the packet supports the answer; do not require every extra citation to be perfect. "
        "context_precision measures how much retrieved_context is relevant, so noisy extra context should mainly reduce context_precision. "
        "context_recall measures whether retrieved_context contains enough evidence for the required facts. "
        "If question_specificity is broad, do not expect exhaustive coverage; a scoped summary with correct primary citation can be correct. "
        "If expected_answer_behavior is clarify_or_scope, either a clarification request or a clearly scoped answer is acceptable. "
        "If answerability is unanswerable or expected_answer_behavior is abstain, reward a concise refusal or scoped answer that says the handbook/source does not provide enough direct evidence. "
        "For unanswerable cases, do not require a citation that proves non-existence; citation_correctness should not be low solely because the answer abstains without citations. "
        "For unanswerable cases, unsupported_claim is false when the answer only says the evidence is missing or insufficient. "
        "Set unsupported_claim true only when the answer asserts a material positive policy, right, permission, exception, contact detail, numeric value, deadline, or consequence that the packet does not support, or when it applies a related source to the asked case without direct evidence. "
        "critical_false_pass is true only if the answer looks acceptable but contains a dangerous/decisive wrong claim.\n"
        "Use exactly these keys and no extra keys: "
        '{"faithfulness":0.0,"answer_relevancy":0.0,"answer_correctness":0.0,'
        '"context_precision":0.0,"context_recall":0.0,"citation_correctness":0.0,'
        '"unsupported_claim":false,"critical_false_pass":false,"rationale":"max 12 words"}\n'
        "The rationale must be a short phrase, not a paragraph.\n"
        f"PACKET={json.dumps(packet, ensure_ascii=False, separators=(',', ':'))}"
    )


def parse_judge_json(text: str) -> dict[str, Any]:
    """Parse and validate the structured judge response."""

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise ValueError("judge_response_missing_json_object")
    payload = json.loads(match.group(0))
    for metric in JUDGE_METRICS:
        value = float(payload[metric])
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"judge_metric_out_of_range:{metric}")
        payload[metric] = value
    payload["unsupported_claim"] = bool(payload.get("unsupported_claim", False))
    payload["critical_false_pass"] = bool(payload.get("critical_false_pass", False))
    payload["rationale"] = str(payload.get("rationale") or "")[:500]
    return payload


class GroqJudgeClient:
    """Evaluate generated answers through a quota-aware Groq client."""

    def __init__(
        self,
        config: JudgeConfig | None = None,
        *,
        pool: JudgeQuotaPool | None = None,
        request_fn: Callable[[str, str, JudgeConfig], tuple[str, dict[str, int]]]
        | None = None,
    ) -> None:
        self.config = config or JudgeConfig()
        self.pool = pool or JudgeQuotaPool.from_environment(self.config)
        self.request_fn = request_fn or self._request

    def judge(self, packet: dict[str, Any]) -> dict[str, Any]:
        """Judge one answer against its question, evidence, and rubric."""

        prompt = build_judge_prompt(packet)
        last_error = "unknown"
        for attempt in range(1, self.config.max_retries + 2):
            key, fingerprint = self.pool.acquire(
                estimate_tokens(prompt) + self.config.max_output_tokens
            )
            try:
                text, usage = self.request_fn(key, prompt, self.config)
                parsed = parse_judge_json(text)
                self.pool.record_success(
                    fingerprint, int(usage.get("output_tokens", 0))
                )
                return {
                    "ok": True,
                    "model_id": self.config.model_name,
                    "key_fingerprint": fingerprint,
                    "attempts": attempt,
                    "usage": usage,
                    "parse_error": None,
                    "scores": parsed,
                }
            except Exception as exc:
                last_error = str(exc)
                rate_limited = any(
                    token in last_error.lower()
                    for token in ("429", "rate limit", "quota")
                )
                self.pool.record_failure(fingerprint, rate_limited=rate_limited)
        return {
            "ok": False,
            "model_id": self.config.model_name,
            "attempts": self.config.max_retries + 1,
            "error": last_error,
            "parse_error": "json_parse_error" if "json" in last_error.lower() else None,
        }

    @staticmethod
    def _request(
        key: str, prompt: str, config: JudgeConfig
    ) -> tuple[str, dict[str, int]]:
        from groq import Groq

        client = Groq(
            api_key=key, timeout=config.request_timeout_seconds, max_retries=0
        )
        response = client.chat.completions.create(
            model=config.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=config.temperature,
            max_tokens=config.max_output_tokens,
            response_format={"type": "json_object"},
        )
        usage = getattr(response, "usage", None)
        return str(response.choices[0].message.content or ""), {
            "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
            "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
        }
