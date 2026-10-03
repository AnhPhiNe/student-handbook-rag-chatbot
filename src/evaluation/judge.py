from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.common.key_pool import KeyPool, KeyPoolConfig


PINNED_JUDGE_MODEL = "openai/gpt-oss-120b"
JUDGE_PACKET_VERSION = "judge-packet-v2-source-context"
# The same open-weight model served by two providers. Scores from different
# providers are not compared with each other: a run and its baseline are judged
# by one provider (STUDENT_RAG_JUDGE_PROVIDER, default groq).
JUDGE_PROVIDERS = {
    "groq": {"key_env": "GROQ_API_KEYS", "base_url": None},
    "deepinfra": {"key_env": "DEEPINFRA_API_KEY", "base_url": "https://api.deepinfra.com/v1/openai"},
}
JUDGE_METRICS = (
    "faithfulness",
    "answer_relevancy",
    "answer_correctness",
    "context_precision",
    "context_recall",
    "citation_correctness",
)


def estimate_tokens(text: str) -> int:
    # Conservative for Vietnamese and JSON prompts.
    """Estimate prompt tokens for local quota accounting."""

    return max(1, math.ceil(len(text) / 3))


@dataclass(frozen=True)
class JudgeConfig:
    """Define model and quota settings for automated answer judging."""

    model_name: str = PINNED_JUDGE_MODEL
    provider: str = "groq"
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
        if self.provider not in JUDGE_PROVIDERS:
            raise ValueError(f"Unknown judge provider {self.provider!r}")


def judge_key_pool(keys: list[str], config: JudgeConfig) -> KeyPool:
    """Groq key pool for the judge; it waits up to max_quota_wait_seconds for a key."""

    key_env = JUDGE_PROVIDERS[config.provider]["key_env"]
    if not keys:
        raise ValueError(f"Missing {key_env} for the generated-answer Judge")
    # Groq's free tier has per-minute and daily token caps; DeepInfra is paid
    # per token and allows many concurrent requests, so only a loose request
    # rate is kept there.
    groq = config.provider == "groq"
    return KeyPool(
        keys,
        KeyPoolConfig(
            name=f"{config.provider}_judge",
            rpm_limit_per_key=config.rpm_limit_per_key if groq else 600,
            tpm_limit_per_key=config.tpm_limit_per_key if groq else None,
            tpd_limit_per_key=config.tpd_limit_per_key if groq else None,
            cooldown_seconds=config.cooldown_seconds,
            state_path=str(config.state_path if groq else Path("data/cache/deepinfra_judge_key_state.json")),
            wait_when_limited=True,
            max_wait_seconds=config.max_quota_wait_seconds,
        ),
        scope=config.model_name,
    )


def compact_judge_packet(
    case: dict[str, Any],
    answer_record: dict[str, Any],
    *,
    max_input_tokens: int = 5_000,
) -> dict[str, Any]:
    """Compact actual evidence, prioritizing required facts and answer claims.

    Lexical matches only order source text; they do not decide whether an
    answer is correct. Never manufacture evidence from the answer or gold.
    """
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
    if authorized_packet_units is not None:
        # This packet is what Composer was authorized to use. Execution JSON
        # outside it can contain other task/cohort records and is not evidence.
        sentences = authorized_packet_units
    elif legacy_composer_context:
        sentences = _split_evidence_units(structured_context)
        sentences.extend(_source_aware_composer_units(legacy_composer_context))
    else:
        sentences = _split_evidence_units(structured_context)
        sentences.extend(_split_evidence_units(fallback_context))
    sentences = list(dict.fromkeys(sentences))
    unit_terms = {line: set(re.findall(r"\w+", line.lower())) for line in sentences}

    selected: list[str] = []
    # Preserve support for extra conditions actually stated in the answer, not
    # just its main gold fact. Match against source units only, before packing.
    for fact in required:
        fact_norm = " ".join(fact.lower().split())
        match = min(
            (
                line
                for line in sentences
                if _fact_matches_context(fact_norm, " ".join(line.lower().split()))
            ),
            key=len,
            default=None,
        )
        if match and match not in selected:
            selected.append(match)

    # An answer may paraphrase a clause while also naming its handbook/article.
    # Anchor each claim to its closest real source unit, rather than let long
    # sources containing many common answer words crowd out short conditions.
    # This only selects evidence; the judge still checks entailment and numbers.
    for claim in _split_evidence_units(str(answer_record.get("answer") or "")[:5_000]):
        claim_terms = set(re.findall(r"\w+", claim.lower()))
        match = max(
            sentences,
            key=lambda line: len(claim_terms & unit_terms[line]) / max(1, len(claim_terms | unit_terms[line])),
            default=None,
        )
        if match and claim_terms & unit_terms[match] and match not in selected:
            selected.append(match)

    ranked = sorted(
        sentences,
        key=lambda line: (
            len(answer_terms & unit_terms[line]),
            len(query_terms & unit_terms[line]),
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
        "packet_version": JUDGE_PACKET_VERSION,
        "case_id": case["id"],
        "query": case["query"],
        "cohort": case.get("cohort"),
        "answerability": case.get("answerability"),
        "question_style": case.get("question_style"),
        "question_specificity": case.get("question_specificity"),
        "expected_answer_behavior": case.get("expected_answer_behavior"),
        "evaluation_notes": str(case.get("evaluation_notes") or "")[:2_000],
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
            # Cutting a clause can remove its exception/negation or split a
            # table row. Omit the complete unit and expose the omission instead.
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
    packet["evidence_compaction"] = {
        "candidate_units": len(sentences),
        "retained_units": len(compact),
        "omitted_units": len(sentences) - len(compact),
        "partial_units": 0,
    }
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


def _authorized_packet_evidence_units(context: str) -> list[str] | None:
    """Extract the Composer packet, distinguishing empty from legacy evidence."""

    try:
        packet = json.loads(context)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(packet, dict) or not isinstance(packet.get("units"), list):
        return None

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
            article = str(source.get("article_label") or "")
            title = str(source.get("title") or "")
            prefix = f"Task: {task_id} | Cohort: {cohort} | Source: {source_ref}"
            if article:
                prefix += f" | Article: {article}"
            if title and title != article:
                prefix += f" | Title: {title}"
            # The composer may name the article and the document; the judge
            # must see both, or a correct citation reads as unsupported.
            document = str(source.get("document_title") or "")
            if document:
                units.append(f"{prefix} | Document: {document}")
            # The composer names the handbook a source is printed in and repeats
            # its currency note; both reach it through the packet, so a judge
            # without them reads the note as an unsupported claim.
            for field, label in (("printed_in", "Printed in"), ("currency_note", "Currency note")):
                value = str(source.get(field) or "").strip()
                if value:
                    units.append(f"{prefix} | {label}: {value}")
            body = str(source.get("content") or "")
            try:
                structured_body = json.loads(body)
            except ValueError:
                structured_body = None
            if isinstance(structured_body, (dict, list)):
                # Splitting at an address such as 'TP. HCM.' would break a
                # JSON record and can reorder fields from different entities.
                units.append(f"{prefix} | {body}")
            else:
                for evidence_unit in _split_evidence_units(body):
                    units.append(f"{prefix} | {evidence_unit}")
            source_context = str(source.get("source_context") or "").strip()
            if source_context:
                # Keep the source's original scope, qualifiers and table layout
                # together. This is supplied evidence, not a new parent lookup.
                units.append(f"{prefix} | Source context: {source_context}")
            resolved_result = source.get("resolved_result")
            if resolved_result is not None:
                units.append(
                    f"{prefix} | Resolved result: "
                    f"{json.dumps(resolved_result, ensure_ascii=False, default=str)}"
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
        "Apply evaluation_notes as case-scoped grading guidance, not as answer evidence. "
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
    """Evaluate generated answers through a quota-aware client (Groq by default)."""

    def __init__(
        self,
        config: JudgeConfig | None = None,
        *,
        pool: KeyPool | None = None,
        request_fn: Callable[[str, str, JudgeConfig], tuple[str, dict[str, int]]]
        | None = None,
    ) -> None:
        provider = os.environ.get("STUDENT_RAG_JUDGE_PROVIDER") or "groq"
        # DeepInfra counts gpt-oss reasoning in max_tokens: the longest answers
        # (V4-111, V4-117) ran out at 1,536 before writing the JSON and needed
        # about 2,000. Responses that end earlier are unaffected by the cap.
        self.config = config or JudgeConfig(
            provider=provider,
            max_output_tokens=1536 if provider == "groq" else 4096,
        )
        key_env = JUDGE_PROVIDERS[self.config.provider]["key_env"]
        keys = [key.strip() for key in (os.environ.get(key_env) or "").split(",")]
        self.pool = pool or judge_key_pool([key for key in keys if key], self.config)
        self.request_fn = request_fn or self._request

    def judge(self, packet: dict[str, Any]) -> dict[str, Any]:
        """Judge one answer against its question, evidence, and rubric."""

        prompt = build_judge_prompt(packet)
        last_error = "unknown"
        for attempt in range(1, self.config.max_retries + 2):
            key, fingerprint, _ = self.pool.acquire(
                estimate_tokens(prompt) + self.config.max_output_tokens
            )
            try:
                text, usage = self.request_fn(key, prompt, self.config)
                parsed = parse_judge_json(text)
                self.pool.record_success(fingerprint)
                return {
                    "ok": True,
                    "model_id": self.config.model_name,
                    "provider": self.config.provider,
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
                if rate_limited:
                    self.pool.record_rate_limit(fingerprint)
                else:
                    self.pool.record_failure(fingerprint, "judge_error")
        return {
            "ok": False,
            "model_id": self.config.model_name,
            "provider": self.config.provider,
            "attempts": self.config.max_retries + 1,
            "error": last_error,
            "parse_error": "json_parse_error" if "json" in last_error.lower() else None,
        }

    @staticmethod
    def _request(
        key: str, prompt: str, config: JudgeConfig
    ) -> tuple[str, dict[str, int]]:
        if config.provider == "groq":
            from groq import Groq

            client = Groq(
                api_key=key, timeout=config.request_timeout_seconds, max_retries=0
            )
        else:
            from openai import OpenAI

            client = OpenAI(
                api_key=key,
                base_url=JUDGE_PROVIDERS[config.provider]["base_url"],
                timeout=config.request_timeout_seconds,
                max_retries=0,
            )
        response = client.chat.completions.create(
            model=config.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=config.temperature,
            max_tokens=config.max_output_tokens,
            response_format={"type": "json_object"},
            # Groq serves gpt-oss at medium reasoning by default; ask other
            # providers for the same rather than rely on their defaults.
            **({} if config.provider == "groq" else {"reasoning_effort": "medium"}),
        )
        usage = getattr(response, "usage", None)
        return str(response.choices[0].message.content or ""), {
            "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
            "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
        }
