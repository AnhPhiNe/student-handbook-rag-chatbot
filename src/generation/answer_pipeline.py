import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree
from src.retrieval.core.retrieval_pipeline import run_retrieval_pipeline
from src.retrieval.core.vector_retriever import (
    get_chroma_collection,
    load_embedding_model,
)

from .answer_formatter import format_final_answer, format_final_response
from .answer_guardrails import (
    build_clarification_question,
    build_deterministic_answer,
    build_fallback_answer,
    can_answer_deterministically,
    detect_ambiguous_query,
    is_low_confidence,
    is_out_of_domain_query,
)
from .citation_formatter import format_sources_text, select_relevant_citations
from .gemini_client import GeminiClient
from .io_utils import load_json, load_yaml
from .prompt_builder import (
    DEFAULT_MAX_CONTEXT_CHARS,
    build_answer_prompt,
    limit_context,
)
from .query_rewriter import QueryRewriter, QueryRewriteResult
from .response_cache import get_response_cache
from .semantic_cache import SemanticCache


DEFAULT_CONFIG_PATH = Path("configs/answer_generation.yaml")


class AnswerPipeline:
    def __init__(
        self,
        config_path: str | Path = DEFAULT_CONFIG_PATH,
        llm_client: Any | None = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.config = load_yaml(self.config_path)

        self.scoring_tables = load_json(self.config["input"]["scoring_tables"])
        self.formula_rules = load_json(self.config["input"]["formula_rules"])
        self.entity_registry = load_json(self.config["input"]["entity_registry"])
        self.expansion_rules = load_json(self.config["input"]["query_expansion_rules"])

        self.model = load_embedding_model(self.config["embedding"]["model_name"])
        self.collection = get_chroma_collection(
            persist_dir=self.config["vectorstore"]["persist_dir"],
            collection_name=self.config["vectorstore"]["collection_name"],
        )

        llm_config = self.config["llm"]
        if llm_config.get("provider") not in ["gemini", "groq"]:
            raise ValueError(
                "AnswerPipeline currently supports only llm.provider='gemini' or 'groq'."
            )

        self._llm_client = llm_client
        self.max_context_chars = int(
            llm_config.get("max_context_chars", DEFAULT_MAX_CONTEXT_CHARS)
        )
        self.request_sleep_seconds = float(llm_config.get("request_sleep_seconds", 2))
        self._last_llm_call_at = 0.0
        self.query_rewriter = QueryRewriter.from_config(
            self.config.get("query_rewriter")
        )

        self.response_cache = get_response_cache(
            path=Path("data/processed/cache/response_cache.json"),
            enabled=self.config.get("cache", {}).get("enabled", True),
            ttl_seconds=self.config.get("cache", {}).get("ttl_seconds", 86400),
        )

        semantic_config = self.config.get("semantic_cache", {})
        self.semantic_cache = SemanticCache(
            config=semantic_config, embedding_model=self.model
        )

    @traceable(name="Answer Pipeline", run_type="chain")
    def answer(
        self,
        query: str,
        chat_history: list[dict[str, str]] | None = None,
        cohort: str | None = None,
    ) -> dict[str, Any]:
        """Bộ Não Sinh Ngôn Ngữ: Lấy dữ liệu từ Retrieval và biến thành câu trả lời (Sync Mode).

        Quy trình hoạt động:
        1. Gọi Query Rewriter để sửa lỗi chính tả/ngữ pháp của người dùng.
        2. Chạy Retrieval Pipeline để tìm kiếm thông tin.
        3. Guardrails (Bảo vệ):
           - Chặn câu hỏi Out-of-Domain.
           - Trả lời nhanh Deterministic nếu tính bằng công thức toán học.
           - Báo lỗi Low Confidence nếu không tìm thấy tài liệu.
        4. Caching:
           - Đọc từ answer_response_cache.json xem đã từng trả lời chưa.
           - Nếu có -> Lấy ra dùng ngay (Tiết kiệm chi phí API).
        5. Gọi LLM:
           - Chèn thông tin vào prompt và gọi Gemini để sinh câu trả lời.
        """
        rewrite_result = self.query_rewriter.rewrite(query, chat_history=chat_history)
        effective_query = rewrite_result.effective_query

        # Override cohort from query if explicitly mentioned to prevent UI state mismatch
        import re

        cohort_match = re.search(r"(?i)\bk(?:hóa)?\s*(\d{2})\b", query)
        if cohort_match:
            cohort = f"K{cohort_match.group(1)}"

        # LLM-Evaluated Semantic Cache (before retrieval)
        is_standalone = not chat_history or len(chat_history) == 0
        if is_standalone:
            semantic_cache_key = self.semantic_cache.lookup(query)
            if semantic_cache_key:
                cached = self.response_cache.get(semantic_cache_key)
                if cached:
                    return self._build_output(
                        query=query,
                        retrieval_result={},
                        final_answer=str(cached.get("answer") or ""),
                        context_used="",
                        selected_citations=cached.get("citations") or [],
                        status=str(cached.get("status") or "answered"),
                        error_type=cached.get("error_type"),
                        error_message=cached.get("error_message"),
                        llm_called=False,
                        used_cache=True,
                        query_rewrite=rewrite_result,
                    )

        # Chi cho Query Rewriter hoi lai som khi no dang xu ly follow-up bang history.
        # Cau standalone mo ho se duoc Retrieval/Guardrail ben duoi danh gia bang nguon that.
        if (
            rewrite_result.needs_clarification
            and rewrite_result.clarification_question
            and self._should_answer_rewrite_clarification(rewrite_result)
        ):
            return self._build_output(
                query=query,
                retrieval_result={},
                final_answer=rewrite_result.clarification_question,
                context_used="",
                selected_citations=[],
                status="needs_clarification",
                error_type=None,
                error_message=None,
                llm_called=False,
                used_cache=False,
                clarification_needed=True,
                query_rewrite=rewrite_result,
            )

        try:
            # Với rewrite từ history, chạy thêm retrieval query gốc để kiểm chứng.
            # Nếu rewrite kéo nhầm context, verification sẽ fallback hoặc hỏi lại.
            retrieval_result, rewrite_result = self._run_verified_retrieval(
                query,
                rewrite_result,
                cohort,
            )
            effective_query = rewrite_result.effective_query
        except Exception as exc:
            final_answer = build_fallback_answer(
                query=effective_query,
                retrieval_result=None,
                reason="retrieval_error",
            )
            return self._build_output(
                query=query,
                retrieval_result={},
                final_answer=final_answer,
                context_used="",
                selected_citations=[],
                status="retrieval_error",
                error_type="retrieval_error",
                error_message=str(exc),
                llm_called=False,
                used_cache=False,
                query_rewrite=rewrite_result,
            )

        context_used = limit_context(
            str(retrieval_result.get("context_for_llm") or ""),
            max_context_chars=self.max_context_chars,
        )

        if retrieval_result.get("rewrite_verification_needs_clarification"):
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=retrieval_result.get(
                    "clarification_question",
                    "Bạn muốn hỏi tiếp nội dung trước đó hay đang chuyển sang một chủ đề mới?",
                ),
                context_used=context_used,
                selected_citations=[],
                status="needs_clarification",
                error_type=None,
                error_message=None,
                llm_called=False,
                used_cache=False,
                clarification_needed=True,
                query_rewrite=rewrite_result,
            )

        # AI Router khong nhan chat_history, nen neu cau hoi da duoc rewrite tu history
        # thi khong de router yeu cau clarify lai mot lan nua.
        query_was_rewritten_from_history = self._query_was_rewritten_from_history(
            rewrite_result
        )
        if (
            retrieval_result.get("needs_clarification")
            and not query_was_rewritten_from_history
        ):
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=retrieval_result.get(
                    "clarification_question", "Bạn có thể làm rõ câu hỏi được không?"
                ),
                context_used=context_used,
                selected_citations=[],
                status="needs_clarification",
                error_type=None,
                error_message=None,
                llm_called=False,
                used_cache=False,
                clarification_needed=True,
                query_rewrite=rewrite_result,
            )

        # Cau hoi van thuoc domain nhung thieu scope thi hoi lai, khong dua vao LLM tra loi doan.
        if detect_ambiguous_query(effective_query, retrieval_result):
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=build_clarification_question(
                    effective_query, retrieval_result
                ),
                context_used=context_used,
                selected_citations=[],
                status="needs_clarification",
                error_type=None,
                error_message=None,
                llm_called=False,
                used_cache=False,
                clarification_needed=True,
                query_rewrite=rewrite_result,
            )

        # Co out_of_domain tu router thi dung ngay, khong dua context rong vao LLM.
        if retrieval_result.get("out_of_domain"):
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=(
                    "Câu hỏi này nằm ngoài phạm vi Sổ tay sinh viên nên mình không thể hỗ trợ được. "
                    "Sổ tay chủ yếu bao gồm các nội dung như: quy chế đào tạo, biểu mẫu, "
                    "thủ tục hành chính, học bổng, rèn luyện, ký túc xá, thông tin phòng ban và khoa/ngành. "
                    "Bạn có thể hỏi lại theo một nội dung liên quan đến sổ tay nhé!"
                ),
                context_used="",
                selected_citations=[],
                status="out_of_domain",
                error_type=None,
                error_message=None,
                llm_called=False,
                used_cache=False,
                query_rewrite=rewrite_result,
            )

        # Lop OOD thu 2: kiem tra chat luong retrieval de bat cac cau ngoai pham vi bi route nham.
        if is_out_of_domain_query(effective_query, retrieval_result):
            final_answer = build_fallback_answer(
                effective_query,
                retrieval_result,
                reason="out_of_domain",
            )
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=final_answer,
                context_used="",
                selected_citations=[],
                status="out_of_domain",
                error_type=None,
                error_message=None,
                llm_called=False,
                used_cache=False,
                query_rewrite=rewrite_result,
            )
        citations_config = self.config.get("citations", {})

        guardrails_config = self.config.get("guardrails", {})
        # Cac ket qua bang diem/cong thuc/tool da du deterministic thi tra thang,
        # vua chinh xac hon vua tiet kiem chi phi LLM.
        if guardrails_config.get(
            "allow_deterministic_direct_answer", True
        ) and can_answer_deterministically(retrieval_result):
            selected_citations = select_relevant_citations(
                retrieval_result.get("citations"),
                intent=retrieval_result.get("intent"),
                retrieval_result=retrieval_result,
                max_sources=int(citations_config.get("max_sources", 2)),
            )
            final_answer = format_final_answer(
                build_deterministic_answer(
                    effective_query, retrieval_result, selected_citations
                ),
                selected_citations,
            )
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=final_answer,
                context_used=context_used,
                selected_citations=selected_citations,
                status="answered",
                error_type=None,
                error_message=None,
                llm_called=False,
                used_cache=False,
                query_rewrite=rewrite_result,
            )

        selected_citations = select_relevant_citations(
            retrieval_result.get("citations"),
            intent=retrieval_result.get("intent"),
            retrieval_result=retrieval_result,
            max_sources=int(citations_config.get("max_sources", 2)),
        )

        if guardrails_config.get(
            "skip_llm_on_low_confidence", True
        ) and is_low_confidence(retrieval_result):
            final_answer = format_final_answer(
                build_fallback_answer(
                    effective_query, retrieval_result, reason="low_confidence"
                ),
                selected_citations,
            )
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=final_answer,
                context_used=context_used,
                selected_citations=selected_citations,
                status="low_confidence",
                error_type="retrieval",
                error_message="Retrieval returned empty or insufficient context.",
                llm_called=False,
                used_cache=False,
                query_rewrite=rewrite_result,
            )

        cache_key = self.response_cache.make_cache_key(
            query=effective_query,
            retrieval_result=retrieval_result,
            selected_citations=selected_citations,
        )
        cached = self.response_cache.get(cache_key)
        if cached:
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=str(cached.get("answer") or ""),
                context_used=context_used,
                selected_citations=selected_citations,
                status=str(cached.get("status") or "answered"),
                error_type=cached.get("error_type"),
                error_message=cached.get("error_message"),
                llm_called=False,
                used_cache=True,
                query_rewrite=rewrite_result,
            )

        # Đưa TOÀN BỘ retrieved_items (đã qua ngưỡng 0.70) vào context cho LLM.
        # selected_citations chỉ dùng cho UI hiển thị nguồn tham khảo.
        prompt = build_answer_prompt(
            query=effective_query,
            retrieval_result=retrieval_result,
            selected_citations=None,
            max_context_chars=self.max_context_chars,
            cohort=cohort,
        )

        try:
            llm_client = self._get_llm_client()
        except Exception as exc:
            final_answer = format_final_answer(
                build_fallback_answer(
                    effective_query, retrieval_result, reason="api_error"
                ),
                selected_citations,
            )
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=final_answer,
                context_used=context_used,
                selected_citations=selected_citations,
                status="api_error",
                error_type="api_init_error",
                error_message=str(exc),
                llm_called=False,
                used_cache=False,
                query_rewrite=rewrite_result,
            )

        self._throttle_llm_call()
        llm_result = llm_client.generate(prompt)
        self._last_llm_call_at = time.monotonic()

        if not llm_result.get("ok"):
            error_type = llm_result.get("error_type") or "api_error"
            final_answer = format_final_answer(
                build_fallback_answer(
                    effective_query, retrieval_result, reason=error_type
                ),
                selected_citations,
            )
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=final_answer,
                context_used=context_used,
                selected_citations=selected_citations,
                status="api_error",
                error_type=error_type,
                error_message=llm_result.get("error_message"),
                llm_called=True,
                used_cache=False,
                query_rewrite=rewrite_result,
            )

        llm_text = str(llm_result.get("text") or "").strip()

        final_answer = format_final_response(
            llm_text,
            sources_text=format_sources_text(selected_citations),
        )
        output = self._build_output(
            query=query,
            retrieval_result=retrieval_result,
            final_answer=final_answer,
            context_used=context_used,
            selected_citations=selected_citations,
            status="answered",
            error_type=None,
            error_message=None,
            llm_called=True,
            used_cache=False,
            query_rewrite=rewrite_result,
        )
        self.response_cache.set(
            cache_key,
            {
                "answer": final_answer,
                "status": "answered",
                "error_type": None,
                "error_message": None,
                "citations": selected_citations,
            },
        )

        if is_standalone:
            self.semantic_cache.store(query, cache_key)

        return output

    @traceable(name="Answer Pipeline Stream", run_type="chain")
    def answer_stream(
        self,
        query: str,
        chat_history: list[dict[str, str]] | None = None,
        cohort: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Luồng tạo câu trả lời dạng Streaming (Server-Sent Events)."""
        run_tree = get_current_run_tree()
        run_id = str(run_tree.id) if run_tree else None

        yield {"type": "progress", "message": "Đang tối ưu hóa câu hỏi..."}
        rewrite_result = self.query_rewriter.rewrite(query, chat_history=chat_history)
        effective_query = rewrite_result.effective_query

        # LLM-Evaluated Semantic Cache (before retrieval)
        is_standalone = not chat_history or len(chat_history) == 0
        if is_standalone:
            semantic_cache_key = self.semantic_cache.lookup(query)
            if semantic_cache_key:
                cached = self.response_cache.get(semantic_cache_key)
                if cached:
                    yield {"type": "progress", "message": "Đang truy xuất từ bộ nhớ đệm..."}
                    yield {
                        "type": "metadata",
                        "run_id": run_id,
                        "status": str(cached.get("status") or "answered"),
                        "intent": None,
                        "strategy": None,
                        "citations_used": cached.get("citations") or [],
                        "llm_called": False,
                        "used_cache": True,
                    }
                    yield {"type": "token", "text": str(cached.get("answer") or "")}
                    yield {"type": "done"}
                    return

        # Stream path dung cung rule voi sync path: rewriter chi duoc hoi lai som cho follow-up.
        if (
            rewrite_result.needs_clarification
            and rewrite_result.clarification_question
            and self._should_answer_rewrite_clarification(rewrite_result)
        ):
            yield {
                "type": "metadata",
                "run_id": run_id,
                "status": "needs_clarification",
                "intent": None,
                "strategy": None,
                "citations_used": [],
            }
            yield {"type": "token", "text": rewrite_result.clarification_question}
            yield {"type": "done"}
            return

        yield {"type": "progress", "message": "Đang tìm kiếm thông tin trong Sổ tay..."}
        try:
            # Retrieval chạy đồng bộ trước, sau đó mới stream token LLM về frontend.
            retrieval_result, rewrite_result = self._run_verified_retrieval(
                query,
                rewrite_result,
                cohort=cohort,
            )
            effective_query = rewrite_result.effective_query
        except Exception:
            fallback = build_fallback_answer(
                query=effective_query, retrieval_result=None, reason="retrieval_error"
            )
            yield {
                "type": "metadata",
                "run_id": run_id,
                "status": "retrieval_error",
                "intent": None,
                "strategy": None,
                "citations_used": [],
            }
            yield {"type": "token", "text": fallback}
            yield {"type": "done"}
            return

        if retrieval_result.get("rewrite_verification_needs_clarification"):
            clarification_msg = retrieval_result.get(
                "clarification_question",
                "Bạn muốn hỏi tiếp nội dung trước đó hay đang chuyển sang một chủ đề mới?",
            )
            yield {
                "type": "metadata",
                "run_id": run_id,
                "status": "needs_clarification",
                "intent": retrieval_result.get("intent"),
                "strategy": retrieval_result.get("strategy"),
                "citations_used": [],
                "llm_called": False,
            }
            yield {"type": "token", "text": clarification_msg}
            yield {"type": "done"}
            return

        # Lớp bảo vệ thứ 2: Nếu câu hỏi đã được rewrite từ lịch sử chat,
        # bỏ qua needs_clarification từ AI Router vì AI Router không nhận history
        # và có thể đánh giá sai câu hỏi đã được bổ sung ngữ cảnh.
        query_was_rewritten_from_history = self._query_was_rewritten_from_history(
            rewrite_result
        )
        if (
            retrieval_result.get("needs_clarification")
            and not query_was_rewritten_from_history
        ):
            clarification_msg = retrieval_result.get(
                "clarification_question", "Bạn có thể làm rõ câu hỏi được không?"
            )
            yield {
                "type": "metadata",
                "run_id": run_id,
                "status": "needs_clarification",
                "intent": retrieval_result.get("intent"),
                "strategy": retrieval_result.get("strategy"),
                "citations_used": [],
            }
            yield {"type": "token", "text": clarification_msg}
            yield {"type": "done"}
            return

        # Neu cau hoi mo ho, stream cau hoi lam ro nhu mot token block thay vi goi LLM.
        if detect_ambiguous_query(effective_query, retrieval_result):
            clarification_msg = build_clarification_question(
                effective_query, retrieval_result
            )
            yield {
                "type": "metadata",
                "run_id": run_id,
                "status": "needs_clarification",
                "intent": retrieval_result.get("intent"),
                "strategy": retrieval_result.get("strategy"),
                "citations_used": [],
                "llm_called": False,
            }
            yield {"type": "token", "text": clarification_msg}
            yield {"type": "done"}
            return

        # Out-of-domain duoc chan truoc khi tao prompt de tranh LLM tra loi ngoai nguon.
        if retrieval_result.get("out_of_domain"):
            out_of_domain_msg = (
                "Câu hỏi này nằm ngoài phạm vi Sổ tay sinh viên nên mình không thể hỗ trợ được. "
                "Sổ tay chủ yếu bao gồm các nội dung như: quy chế đào tạo, biểu mẫu, "
                "thủ tục hành chính, học bổng, rèn luyện, ký túc xá, thông tin phòng ban và khoa/ngành. "
                "Bạn có thể hỏi lại theo một nội dung liên quan đến sổ tay nhé!"
            )
            yield {
                "type": "metadata",
                "run_id": run_id,
                "status": "out_of_domain",
                "intent": "out_of_domain",
                "strategy": "none",
                "citations_used": [],
                "llm_called": False,
            }
            yield {"type": "token", "text": out_of_domain_msg}
            yield {"type": "done"}
            return

        if is_out_of_domain_query(effective_query, retrieval_result):
            out_of_domain_msg = build_fallback_answer(
                effective_query,
                retrieval_result,
                reason="out_of_domain",
            )
            yield {
                "type": "metadata",
                "run_id": run_id,
                "status": "out_of_domain",
                "intent": retrieval_result.get("intent"),
                "strategy": retrieval_result.get("strategy"),
                "citations_used": [],
                "llm_called": False,
            }
            yield {"type": "token", "text": out_of_domain_msg}
            yield {"type": "done"}
            return

        # Yield progress based on detected intent
        intent = retrieval_result.get("intent", "regulation_query")
        intent_progress_messages = {
            "formula_query": "Đang đối chiếu công thức tính điểm và học tập...",
            "calculation_query": "Đang thực hiện tính toán số liệu học tập...",
            "procedure_query": "Đang tra cứu các quy trình thủ tục hành chính...",
            "faculty_query": "Đang tìm kiếm thông tin về Khoa và Ngành học...",
            "form_query": "Đang trích xuất thông tin biểu mẫu và hồ sơ...",
            "office_query": "Đang định vị địa chỉ liên hệ và phòng ban...",
            "score_lookup_query": "Đang xếp loại điểm rèn luyện và học tập...",
            "regulation_query": "Đang đối chiếu các quy chế đào tạo...",
            "mixed_query": "Đang tổng hợp dữ liệu từ nhiều chuyên mục...",
        }
        progress_msg = intent_progress_messages.get(intent, "Đang phân tích tài liệu tìm được...")
        yield {"type": "progress", "message": progress_msg}

        citations_config = self.config.get("citations", {})
        guardrails_config = self.config.get("guardrails", {})

        # Deterministic answers: yield as single chunk (no LLM needed)
        if guardrails_config.get(
            "allow_deterministic_direct_answer", True
        ) and can_answer_deterministically(retrieval_result):
            selected_citations = select_relevant_citations(
                retrieval_result.get("citations"),
                intent=retrieval_result.get("intent"),
                retrieval_result=retrieval_result,
                max_sources=int(citations_config.get("max_sources", 2)),
            )
            final_answer = format_final_answer(
                build_deterministic_answer(
                    effective_query, retrieval_result, selected_citations
                ),
                selected_citations,
            )
            yield {
                "type": "metadata",
                "run_id": run_id,
                "status": "answered",
                "intent": retrieval_result.get("intent"),
                "strategy": retrieval_result.get("strategy"),
                "citations_used": selected_citations,
                "llm_called": False,
            }
            yield {"type": "token", "text": final_answer}
            yield {"type": "done"}
            return

        selected_citations = select_relevant_citations(
            retrieval_result.get("citations"),
            intent=retrieval_result.get("intent"),
            retrieval_result=retrieval_result,
            max_sources=int(citations_config.get("max_sources", 2)),
        )

        # Low confidence: yield fallback as single chunk
        if guardrails_config.get(
            "skip_llm_on_low_confidence", True
        ) and is_low_confidence(retrieval_result):
            final_answer = format_final_answer(
                build_fallback_answer(
                    effective_query, retrieval_result, reason="low_confidence"
                ),
                selected_citations,
            )
            yield {
                "type": "metadata",
                "run_id": run_id,
                "status": "low_confidence",
                "intent": retrieval_result.get("intent"),
                "strategy": retrieval_result.get("strategy"),
                "citations_used": selected_citations,
                "llm_called": False,
            }
            yield {"type": "token", "text": final_answer}
            yield {"type": "done"}
            return

        # Đưa TOÀN BỘ retrieved_items (đã qua ngưỡng 0.70) vào context cho LLM.
        # selected_citations chỉ dùng cho UI hiển thị nguồn tham khảo.
        prompt = build_answer_prompt(
            query=effective_query,
            retrieval_result=retrieval_result,
            selected_citations=None,
            max_context_chars=self.max_context_chars,
            cohort=cohort,
        )

        yield {"type": "progress", "message": "Đang tổng hợp câu trả lời..."}
        yield {
            "type": "metadata",
            "run_id": run_id,
            "status": "answered",
            "intent": retrieval_result.get("intent"),
            "strategy": retrieval_result.get("strategy"),
            "citations_used": selected_citations,
            "llm_called": True,
        }

        try:
            llm_client = self._get_llm_client()
            self._throttle_llm_call()
            for chunk in llm_client.generate_stream(prompt):
                yield {"type": "token", "text": chunk}
            self._last_llm_call_at = time.monotonic()
        except Exception:
            fallback = build_fallback_answer(
                effective_query, retrieval_result, reason="api_error"
            )
            yield {"type": "token", "text": fallback}

        # Chặn việc yield sources text dưới dạng văn bản thô
        # sources_text = format_sources_text(selected_citations)
        # if sources_text:
        #     yield {"type": "token", "text": f"\n\n{sources_text}"}

        yield {"type": "done"}

    def _run_retrieval(self, query: str, cohort: str | None = None) -> dict[str, Any]:
        return run_retrieval_pipeline(
            query=query,
            model=self.model,
            collection=self.collection,
            scoring_tables=self.scoring_tables,
            formula_rules=self.formula_rules,
            entity_registry=self.entity_registry,
            expansion_rules=self.expansion_rules,
            top_k=self.config["retrieval"]["default_top_k"],
            batch_size=self.config["embedding"]["batch_size"],
            normalize_embeddings=self.config["embedding"]["normalize_embeddings"],
            cohort=cohort,
        )

    def _run_verified_retrieval(
        self,
        original_query: str,
        rewrite_result: QueryRewriteResult,
        cohort: str | None = None,
    ) -> tuple[dict[str, Any], QueryRewriteResult]:
        effective_query = rewrite_result.effective_query
        rewritten_result = self._run_retrieval(effective_query, cohort=cohort)

        if (
            not self._query_was_rewritten_from_history(rewrite_result)
            or effective_query.strip() == original_query.strip()
        ):
            rewritten_result["rewrite_verification"] = {
                "mode": "single_retrieval",
                "selected": "effective_query",
            }
            return rewritten_result, rewrite_result

        original_result = self._run_retrieval(original_query)
        selected = self._select_verified_retrieval(
            original_result=original_result,
            rewritten_result=rewritten_result,
        )

        verification = {
            "mode": "dual_retrieval",
            "selected": selected,
            "original_quality": _retrieval_quality(original_result),
            "rewritten_quality": _retrieval_quality(rewritten_result),
            "original_intent": original_result.get("intent"),
            "rewritten_intent": rewritten_result.get("intent"),
        }

        if selected == "original_query":
            original_result["rewrite_verification"] = verification
            return original_result, replace(
                rewrite_result,
                effective_query=original_query,
                reason=f"{rewrite_result.reason}_retrieval_fallback_to_original",
            )

        if selected == "needs_clarification":
            rewritten_result["rewrite_verification"] = verification
            rewritten_result["rewrite_verification_needs_clarification"] = True
            rewritten_result["clarification_question"] = (
                "Mình chưa chắc câu hỏi này đang nối tiếp nội dung trước đó hay là một chủ đề mới. "
                "Bạn có thể viết rõ câu hỏi đầy đủ hơn được không?"
            )
            return rewritten_result, replace(
                rewrite_result,
                effective_query=original_query,
                reason=f"{rewrite_result.reason}_retrieval_conflict",
            )

        rewritten_result["rewrite_verification"] = verification
        return rewritten_result, rewrite_result

    def _select_verified_retrieval(
        self,
        *,
        original_result: dict[str, Any],
        rewritten_result: dict[str, Any],
    ) -> str:
        original_answerable = _retrieval_is_answerable(original_result)
        rewritten_answerable = _retrieval_is_answerable(rewritten_result)
        original_quality = _retrieval_quality(original_result)
        rewritten_quality = _retrieval_quality(rewritten_result)

        if rewritten_answerable and not original_answerable:
            return "rewritten_query"
        if original_answerable and not rewritten_answerable:
            return "original_query"
        if not original_answerable and not rewritten_answerable:
            return "rewritten_query"

        if _retrieval_results_conflict(original_result, rewritten_result):
            if rewritten_quality >= original_quality + 0.20:
                return "rewritten_query"
            if original_quality >= rewritten_quality + 0.20:
                return "original_query"
            return "needs_clarification"

        if original_quality > rewritten_quality + 0.15:
            return "original_query"
        return "rewritten_query"

    def _get_llm_client(self) -> Any:
        if self._llm_client is None:
            llm_config = self.config["llm"]
            provider = llm_config.get("provider", "gemini")
            if provider == "gemini":
                self._llm_client = GeminiClient(
                    model_name=llm_config.get("model_name", "gemini-2.5-flash"),
                    temperature=llm_config.get("temperature", 0.2),
                    max_output_tokens=llm_config.get("max_output_tokens", 1024),
                    max_retries=llm_config.get("max_retries", 3),
                    retry_base_delay_seconds=llm_config.get(
                        "retry_base_delay_seconds", 2
                    ),
                    retry_max_delay_seconds=llm_config.get(
                        "retry_max_delay_seconds", 20
                    ),
                    request_timeout_seconds=llm_config.get(
                        "request_timeout_seconds", 60
                    ),
                )
            elif provider == "groq":
                from .groq_client import GroqClient

                self._llm_client = GroqClient(
                    model_name=llm_config.get("model_name", "llama-3.3-70b-versatile"),
                    temperature=llm_config.get("temperature", 0.2),
                    max_output_tokens=llm_config.get("max_output_tokens", 1024),
                    max_retries=llm_config.get("max_retries", 3),
                    retry_base_delay_seconds=llm_config.get(
                        "retry_base_delay_seconds", 2
                    ),
                    retry_max_delay_seconds=llm_config.get(
                        "retry_max_delay_seconds", 20
                    ),
                    request_timeout_seconds=llm_config.get(
                        "request_timeout_seconds", 60
                    ),
                )
        return self._llm_client

    def _throttle_llm_call(self) -> None:
        if self.request_sleep_seconds <= 0 or self._last_llm_call_at <= 0:
            return

        elapsed = time.monotonic() - self._last_llm_call_at
        remaining = self.request_sleep_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _query_was_rewritten_from_history(
        self,
        rewrite_result: QueryRewriteResult,
    ) -> bool:
        context_resolution = rewrite_result.context_resolution or {}
        return bool(rewrite_result.changed and context_resolution.get("history_used"))

    def _should_answer_rewrite_clarification(
        self,
        rewrite_result: QueryRewriteResult,
    ) -> bool:
        context_resolution = rewrite_result.context_resolution or {}
        # Context ambiguity là rủi ro nhiễm history, nên hỏi lại trước khi retrieval.
        # Standalone ambiguity thông thường vẫn để Retrieval/Guardrail đánh giá bằng nguồn thật.
        return bool(
            context_resolution.get("history_used")
            or (
                context_resolution.get("decision") == "ambiguous"
                and context_resolution.get("needs_clarification")
            )
        )

    def _build_output(
        self,
        query: str,
        retrieval_result: dict[str, Any],
        final_answer: str,
        context_used: str,
        selected_citations: list[dict[str, Any]],
        status: str,
        error_type: str | None,
        error_message: str | None,
        llm_called: bool,
        used_cache: bool,
        clarification_needed: bool = False,
        query_rewrite: QueryRewriteResult | None = None,
    ) -> dict[str, Any]:
        query_rewrite_payload = query_rewrite.to_dict() if query_rewrite else None
        run_tree = get_current_run_tree()
        run_id = str(run_tree.id) if run_tree else None

        return {
            "run_id": run_id,
            "query": query,
            "effective_query": (
                query_rewrite.effective_query
                if query_rewrite
                else retrieval_result.get("query", query)
            ),
            "query_rewrite": query_rewrite_payload,
            "answer": final_answer,
            "status": status,
            "error_type": error_type,
            "error_message": error_message,
            "intent": retrieval_result.get("intent"),
            "strategy": retrieval_result.get("strategy"),
            "retrieval_query": retrieval_result.get("retrieval_query"),
            "citations": retrieval_result.get("citations", []),
            "citations_used": selected_citations,
            "structured_result": retrieval_result.get("structured_result"),
            "formula_result": retrieval_result.get("formula_result"),
            "tool_result": retrieval_result.get("tool_result"),
            "llm_called": llm_called,
            "used_cache": used_cache,
            "clarification_needed": clarification_needed,
            "context_used": context_used,
        }


def _retrieval_is_answerable(retrieval_result: dict[str, Any]) -> bool:
    if retrieval_result.get("out_of_domain") or retrieval_result.get(
        "needs_clarification"
    ):
        return False
    if can_answer_deterministically(retrieval_result):
        return True
    return bool(str(retrieval_result.get("context_for_llm") or "").strip()) or bool(
        retrieval_result.get("citations") or retrieval_result.get("retrieved_items")
    )


def _retrieval_quality(retrieval_result: dict[str, Any]) -> float:
    if retrieval_result.get("out_of_domain") or retrieval_result.get(
        "needs_clarification"
    ):
        return 0.0

    score = 0.0
    if can_answer_deterministically(retrieval_result):
        score += 2.0
    if str(retrieval_result.get("context_for_llm") or "").strip():
        score += 1.0

    citations = retrieval_result.get("citations") or []
    retrieved_items = retrieval_result.get("retrieved_items") or []
    score += min(len(citations), 3) * 0.1
    score += min(len(retrieved_items), 5) * 0.05

    top_score = _top_retrieval_score(retrieved_items)
    if top_score is not None:
        score += max(0.0, min(top_score, 1.0))

    return score


def _retrieval_results_conflict(
    original_result: dict[str, Any],
    rewritten_result: dict[str, Any],
) -> bool:
    original_intent = str(original_result.get("intent") or "")
    rewritten_intent = str(rewritten_result.get("intent") or "")
    if original_intent and rewritten_intent and original_intent != rewritten_intent:
        return True

    original_chunk_types = _result_chunk_types(original_result)
    rewritten_chunk_types = _result_chunk_types(rewritten_result)
    return bool(
        original_chunk_types
        and rewritten_chunk_types
        and original_chunk_types.isdisjoint(rewritten_chunk_types)
    )


def _result_chunk_types(retrieval_result: dict[str, Any]) -> set[str]:
    chunk_types = {
        str(item.get("metadata", {}).get("chunk_type") or "").strip()
        for item in retrieval_result.get("retrieved_items", [])
    }
    chunk_types.update(
        str(chunk_type).strip()
        for chunk_type in retrieval_result.get("target_chunk_types", [])
    )
    return {chunk_type for chunk_type in chunk_types if chunk_type}


def _top_retrieval_score(items: list[dict[str, Any]]) -> float | None:
    if not items:
        return None

    top_item = items[0]
    rerank = top_item.get("rerank") or {}
    if isinstance(rerank, dict) and rerank.get("final_score") is not None:
        return float(rerank["final_score"])
    if top_item.get("score") is not None:
        return float(top_item["score"])
    if top_item.get("distance") is not None:
        return 1.0 - float(top_item["distance"])
    return None
