"""Execute a QueryPlan: run each task, then merge the evidence for one answer.

The planner produces at most three independent tasks. This module runs them — a
structured lookup or a regulation retrieval per cohort — and merges their evidence,
citations and coverage into the single retrieval result the composer consumes.
Dependencies are explicit constructor arguments so the pipeline stays the caller.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.common.cohort import is_validated_source_applicable
from src.retrieval.core.citation_builder import (
    build_citation_from_lookup,
    enrich_citations_with_parent_details,
)
from src.retrieval.core.graph_traverser import NetworkXGraphTraverser
from src.retrieval.core.hybrid_pipeline import (
    build_related_references,
    run_hybrid_retrieval_pipeline,
    select_graph_related_parent_candidates,
)


def _merge_structured_citation_content(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> str:
    """Preserve every distinct table when one handbook section backs several.

    Citation identity remains the canonical parent section, while the evidence
    payload retains each table and its applicability. This prevents source
    deduplication from silently discarding a sibling structured table.
    """

    tables: list[dict[str, Any]] = []
    seen: set[str] = set()
    for citation in (existing, incoming):
        try:
            payload = json.loads(str(citation.get("content") or ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        candidates = (
            payload.get("tables")
            if isinstance(payload, dict) and isinstance(payload.get("tables"), list)
            else [payload]
        )
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            table = dict(candidate)
            table.setdefault("table_name", citation.get("title"))
            table.setdefault("applicability", citation.get("applicability"))
            identity = json.dumps(
                table, ensure_ascii=False, sort_keys=True, default=str
            )
            if identity in seen:
                continue
            seen.add(identity)
            tables.append(table)

    if not tables:
        return str(existing.get("content") or "")
    return json.dumps({"tables": tables}, ensure_ascii=False, indent=2, default=str)


@dataclass(frozen=True)
class StructuredCatalogs:
    """Reviewed source catalogs the structured resolver reads."""

    formula_rules: list[dict[str, Any]]
    office_directory: list[dict[str, Any]]
    student_service_directory: list[dict[str, Any]]
    student_faculty_profiles: list[dict[str, Any]]
    structured_tables_registry: list[dict[str, Any]]
    program_directory: list[dict[str, Any]]


class PlanExecutor:
    """Run one QueryPlan against the retrieval stack and reviewed catalogs."""

    def __init__(
        self,
        *,
        router: Any,
        slang_normalizer: Any,
        catalogs: StructuredCatalogs,
        parent_sources_by_id: dict[str, dict[str, Any]],
        top_k: int,
        public_source_limit: int,
        model: Any | None = None,
        graph: Any | None = None,
    ) -> None:
        self.router = router
        self.slang_normalizer = slang_normalizer
        self.catalogs = catalogs
        self.parent_sources_by_id = parent_sources_by_id
        self.top_k = top_k
        self.public_source_limit = public_source_limit
        self.model = model
        self._graph = graph

    def run(
        self,
        *,
        query: str,
        cohort: str | None,
        chat_history: list[dict[str, str]] | None,
    ) -> dict[str, Any]:
        """Plan and execute at most three independent, non-recursive tasks."""
        router_input_query = self.slang_normalizer.replace_for_router(query)
        raw_plan = self.router.plan(
            router_input_query,
            chat_history=chat_history,
            cohort=cohort,
        )

        plan_keys = (
            "schema_version",
            "context_mode",
            "normalized_query",
            "standalone_query",
            "referenced_turns",
            "out_of_domain",
            "tasks",
        )
        plan = {key: raw_plan.get(key) for key in plan_keys}
        planner_fallback = raw_plan.get("planner_fallback")
        effective_query_candidate = (
            plan.get("standalone_query")
            if plan.get("context_mode") == "follow_up"
            else plan.get("normalized_query")
        )
        effective_query = str(effective_query_candidate or query).strip() or query
        query_handling = {
            "raw_query": query,
            "effective_query": effective_query,
            "mode": "standalone_rewrite"
            if plan.get("context_mode") == "follow_up"
            else "normalized",
            "context_mode": plan.get("context_mode") or "standalone",
            "source": "query_plan",
            "normalized_query": plan.get("normalized_query"),
            "standalone_query": plan.get("standalone_query"),
            "referenced_turns": plan.get("referenced_turns") or [],
            "validation_errors": raw_plan.get("planner_validation_errors") or [],
            "needs_clarification": False,
            "clarification_question": None,
        }
        base_result = {
            "query": query,
            "retrieval_query": self.slang_normalizer.normalize_for_retrieval(
                effective_query
            ),
            "effective_query": effective_query,
            "raw_query": query,
            "cohort": cohort,
            "selected_cohort": cohort,
            "query_handling": query_handling,
            "query_plan": plan,
            "planner_fallback": planner_fallback,
            "router_usage": raw_plan.get("usage"),
            "router_model": raw_plan.get("model_used"),
        }
        if raw_plan.get("planner_diagnostics") is not None:
            base_result["planner_diagnostics"] = raw_plan["planner_diagnostics"]
        if plan.get("out_of_domain"):
            return {
                **base_result,
                "intent": "out_of_domain",
                "strategy": "query_plan",
                "execution_mode": "none",
                "structured_result": None,
                "retrieved_items": [],
                "citations": [],
                "task_results": [],
                "coverage_by_task": {},
                "supports_task_ids": {},
                "needs_llm_answer": False,
                "needs_clarification": False,
                "clarification_question": None,
                "out_of_domain": True,
            }

        task_executions = [
            self.execute_task(
                task=task,
                task_index=index,
                default_cohort=cohort,
            )
            for index, task in enumerate(plan.get("tasks") or [])
        ]
        return self.aggregate_results(
            base_result=base_result,
            plan=plan,
            task_executions=task_executions,
        )

    def execute_task(
        self,
        *,
        task: dict[str, Any],
        task_index: int,
        default_cohort: str | None,
    ) -> dict[str, Any]:
        """Execute one planned task across its cohorts and normalize the result."""

        task_id = str(task.get("id") or f"t{task_index + 1}")
        mode = task.get("mode")
        task_cohorts = task.get("cohorts") or (
            [default_cohort] if default_cohort else [None]
        )
        task_cohorts = list(dict.fromkeys(task_cohorts))

        if mode == "clarify":
            question = str(
                task.get("clarification_question")
                or "Bạn có thể làm rõ yêu cầu này không?"
            )
            return {
                "task_result": {
                    "task_id": task_id,
                    "question": task.get("question"),
                    "mode": mode,
                    "coverage": "needs_clarification",
                    "clarification_question": question,
                    "cohorts": task_cohorts,
                    "evidence": [],
                },
                "structured_results": [],
                "retrieved_items": [],
                "citations": [],
                "related_references": [],
                "clarification_questions": [question],
            }

        task_evidence: list[dict[str, Any]] = []
        cohort_coverage: dict[str, str] = {}
        resolution_by_cohort: dict[str, str] = {}
        clarification_by_cohort: dict[str, str] = {}
        task_citations: list[dict[str, Any]] = []
        task_items: list[dict[str, Any]] = []
        related_references: list[dict[str, Any]] = []
        structured_results: list[dict[str, Any]] = []
        clarification_questions: list[str] = []

        for task_cohort in task_cohorts:
            if mode == "structured":
                sub_result = self._execute_planned_structured_task(
                    task=task,
                    task_id=task_id,
                    cohort=task_cohort,
                )
            else:
                sub_result = self._execute_planned_rag_task(
                    task=task,
                    task_id=task_id,
                    cohort=task_cohort,
                )
            cohort_key = str(task_cohort or "default")
            cohort_coverage[cohort_key] = sub_result["coverage"]
            if mode == "structured":
                resolution_by_cohort[cohort_key] = sub_result.get("resolution_status", "unavailable")
            task_evidence.extend(sub_result.get("evidence") or [])
            task_citations.extend(sub_result.get("citations") or [])
            task_items.extend(sub_result.get("retrieved_items") or [])
            related_references.extend(sub_result.get("related_references") or [])
            structured = sub_result.get("structured_result")
            if structured:
                structured_results.append(structured)
            clarification = sub_result.get("clarification_question")
            if clarification:
                clarification = str(clarification)
                clarification_questions.append(clarification)
                clarification_by_cohort[cohort_key] = clarification

        statuses = list(cohort_coverage.values())
        if statuses and all(status == "covered" for status in statuses):
            coverage = "covered"
        elif any(status == "needs_clarification" for status in statuses):
            coverage = "needs_clarification"
        else:
            coverage = "uncovered"

        return {
            "task_result": {
                "task_id": task_id,
                "question": task.get("question"),
                "mode": mode,
                "lookup_type": task.get("lookup_type"),
                "intent": task.get("intent"),
                "cohorts": task_cohorts,
                "coverage": coverage,
                "coverage_by_cohort": cohort_coverage,
                "resolution_by_cohort": resolution_by_cohort,
                "clarification_by_cohort": clarification_by_cohort,
                "evidence": task_evidence,
                "citation_count": len(task_citations),
            },
            "structured_results": structured_results,
            "retrieved_items": task_items,
            "citations": task_citations,
            "related_references": related_references,
            "clarification_questions": clarification_questions,
        }

    def aggregate_results(
        self,
        *,
        base_result: dict[str, Any],
        plan: dict[str, Any],
        task_executions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Merge task executions into the stable retrieval result contract."""

        task_results = [execution["task_result"] for execution in task_executions]
        coverage_by_task = {
            str(result["task_id"]): str(result["coverage"])
            for result in task_results
        }
        structured_results = [
            result
            for execution in task_executions
            for result in execution.get("structured_results") or []
        ]
        all_items = [
            item
            for execution in task_executions
            for item in execution.get("retrieved_items") or []
        ]
        all_citations = [
            citation
            for execution in task_executions
            for citation in execution.get("citations") or []
        ]
        all_related_references = [
            reference
            for execution in task_executions
            for reference in execution.get("related_references") or []
        ]
        clarification_questions = [
            question
            for execution in task_executions
            for question in execution.get("clarification_questions") or []
        ]
        merged_items = self._merge_task_items(all_items)
        merged_citations = self._merge_task_citations(all_citations)
        selected_citations = self._select_task_primary_citations(
            merged_citations,
            coverage_by_task,
            max_sources=self.public_source_limit,
        )
        covered_any = any(value == "covered" for value in coverage_by_task.values())
        clarify_any = any(
            value == "needs_clarification" for value in coverage_by_task.values()
        )
        if len(structured_results) == 1:
            structured_result: dict[str, Any] | None = structured_results[0]
        elif structured_results:
            structured_result = {
                "lookup_type": "multi_task_structured",
                "sub_lookups": structured_results,
                "result": structured_results,
                "table_name": "Dữ liệu tra cứu có cấu trúc theo từng yêu cầu",
                "source_label": "Sổ tay sinh viên HCMUE",
            }
        else:
            structured_result = None
        task_modes = {str(task.get("mode")) for task in (plan.get("tasks") or [])}
        executable_modes = task_modes - {"clarify"}
        if len(executable_modes) > 1:
            execution_mode = "mixed"
        elif executable_modes:
            execution_mode = next(iter(executable_modes))
        elif "clarify" in task_modes:
            execution_mode = "clarify"
        else:
            execution_mode = "regulation"
        return {
            **base_result,
            "intent": "multi_task"
            if len(task_results) > 1
            else (task_results[0].get("intent") if task_results else "open_question"),
            "strategy": "query_plan_execution",
            "execution_mode": execution_mode,
            "lookup_type": None,
            "structured_result": structured_result,
            "retrieved_items": merged_items,
            "evidence_citations": merged_citations,
            "citations": selected_citations,
            "related_references": self._merge_related_references(
                all_related_references
            ),
            "task_results": task_results,
            "coverage_by_task": coverage_by_task,
            "supports_task_ids": {
                str(citation.get("chunk_id") or index): citation.get(
                    "supports_task_ids"
                )
                or []
                for index, citation in enumerate(selected_citations)
            },
            "needs_llm_answer": covered_any,
            "needs_clarification": bool(clarify_any and not covered_any),
            "clarification_question": clarification_questions[0]
            if clarification_questions
            else None,
            "out_of_domain": False,
            "deterministic_validated": bool(structured_results),
        }

    def _execute_planned_structured_task(
        self,
        *,
        task: dict[str, Any],
        task_id: str,
        cohort: str | None,
    ) -> dict[str, Any]:
        """Execute one structured lookup task and normalize its evidence packet."""

        from src.retrieval.core.structured_dispatcher import resolve_structured_task

        resolution = resolve_structured_task(
            task,
            query=self.slang_normalizer.normalize_for_retrieval(
                str(task.get("question") or "")
            ),
            cohort=cohort,
            formula_rules=self.catalogs.formula_rules,
            office_directory=self.catalogs.office_directory,
            student_service_directory=self.catalogs.student_service_directory,
            student_faculty_profiles=self.catalogs.student_faculty_profiles,
            structured_tables_registry=self.catalogs.structured_tables_registry,
            program_directory=self.catalogs.program_directory,
            model=self.model,
        )
        if not resolution or not resolution.result:
            return {
                "resolution_status": "unavailable",
                "coverage": "uncovered",
                "evidence": [],
                "citations": [],
                "retrieved_items": [],
            }
        if resolution.result_kind == "clarification":
            return {
                "resolution_status": "needs_clarification",
                "coverage": "needs_clarification",
                "clarification_question": resolution.result.get(
                    "clarification_question"
                ),
                "evidence": [],
                "citations": [],
                "retrieved_items": [],
            }
        evidence = {
            **resolution.result,
            "task_id": task_id,
            "cohort": resolution.result.get("cohort") or cohort,
        }
        citations = enrich_citations_with_parent_details(
            build_citation_from_lookup(evidence),
            self.parent_sources_by_id,
        )
        citations = [
            {
                **citation,
                "task_id": task_id,
                "supports_task_ids": [task_id],
                "cohort": citation.get("cohort") or cohort,
            }
            for citation in citations
        ]
        related_references = self._structured_related_references(
            citations,
            cohort=cohort,
        )
        coverage = "covered" if citations else "uncovered"
        return {
            "coverage": coverage,
            "evidence": [evidence],
            "resolution_status": resolution.resolution_status if citations else "unavailable",
            "structured_result": evidence,
            "citations": citations,
            "related_references": related_references,
            "retrieved_items": [],
        }

    def _execute_planned_rag_task(
        self,
        *,
        task: dict[str, Any],
        task_id: str,
        cohort: str | None,
    ) -> dict[str, Any]:
        """Execute one RAG task and normalize retrieval evidence for generation."""

        task_query = str(task.get("question") or "").strip()
        retrieval_query = self.slang_normalizer.normalize_for_retrieval(task_query)
        task_top_k = self.top_k
        result = run_hybrid_retrieval_pipeline(
            query=task_query,
            top_k=task_top_k,
            cohort=cohort,
            intent=task.get("intent") or "open_question",
            strategy="regulation",
            retrieval_query=retrieval_query,
        )
        items = []
        for item in result.get("retrieved_items") or []:
            if not is_validated_source_applicable(item, cohort):
                continue
            copied = dict(item)
            metadata = dict(copied.get("metadata") or {})
            metadata.update(
                {
                    "task_id": task_id,
                    "supports_task_ids": [task_id],
                    "cohort": metadata.get("cohort") or cohort,
                }
            )
            copied["metadata"] = metadata
            copied["task_id"] = task_id
            copied["supports_task_ids"] = [task_id]
            items.append(copied)
            if len(items) >= task_top_k:
                break
        citations = [
            {
                **citation,
                "task_id": task_id,
                "supports_task_ids": [task_id],
                "cohort": citation.get("cohort") or cohort,
            }
            for citation in (result.get("citations") or [])
            if is_validated_source_applicable(citation, cohort)
        ]
        citations = citations[:task_top_k]
        coverage = "covered" if items and citations else "uncovered"
        evidence = [
            {
                "task_id": task_id,
                "cohort": cohort,
                "retrieval_query": retrieval_query,
                "source_ids": [
                    str(item.get("chunk_id") or item.get("_id") or "") for item in items
                ],
            }
        ]
        return {
            "coverage": coverage,
            "evidence": evidence,
            "citations": citations,
            "retrieved_items": items,
            "related_references": result.get("related_references") or [],
        }

    def _structured_related_references(
        self,
        citations: list[dict[str, Any]],
        *,
        cohort: str | None,
    ) -> list[dict[str, Any]]:
        """Expose direct graph neighbors for structured source articles as UI metadata."""
        primary_ids = list(
            dict.fromkeys(
                str(
                    citation.get("source_parent_id")
                    or citation.get("parent_section_id")
                    or citation.get("chunk_id")
                    or ""
                ).strip()
                for citation in citations
                if isinstance(citation, dict)
            )
        )
        primary_ids = [parent_id for parent_id in primary_ids if parent_id]
        if not primary_ids:
            return []

        graph = self._graph or NetworkXGraphTraverser()
        self._graph = graph
        expanded = graph.expand_context(primary_ids, max_depth=1)
        candidates = select_graph_related_parent_candidates(primary_ids, expanded)
        related_items: list[dict[str, Any]] = []
        for rank, candidate in enumerate(candidates, start=1):
            parent_id = str(candidate.get("parent_id") or "").strip()
            parent = self.parent_sources_by_id.get(parent_id)
            if not isinstance(parent, dict):
                continue
            if cohort and not is_validated_source_applicable(parent, cohort):
                continue
            metadata = dict(parent.get("metadata") or {})
            related_items.append(
                {
                    **parent,
                    "chunk_id": parent_id,
                    "content": parent.get("content") or "",
                    "metadata": {
                        **metadata,
                        "related_source_primary_id": candidate.get("source_primary_id"),
                        "related_graph_depth": candidate.get("depth"),
                        "related_rank": rank,
                    },
                }
            )
        return build_related_references(related_items)

    @staticmethod
    def _merge_related_references(
        references: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge related graph references while preserving stable order."""

        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for reference in references:
            if not isinstance(reference, dict):
                continue
            key = (
                str(reference.get("primary_chunk_id") or ""),
                str(reference.get("related_chunk_id") or ""),
            )
            if not all(key) or key in seen:
                continue
            seen.add(key)
            item = dict(reference)
            display_label = f"R{len(merged) + 1}"
            if item.get("canonical_source_id"):
                item["display_label"] = display_label
                item["id"] = item["canonical_source_id"]
            else:
                item.pop("display_label", None)
                item["id"] = display_label
            merged.append(item)
        return merged

    @staticmethod
    def _merge_task_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Merge task outputs by identity without duplicating evidence."""

        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for item in items:
            metadata = item.get("metadata") or {}
            key = (
                str(metadata.get("cohort") or "default"),
                str(
                    item.get("chunk_id")
                    or item.get("_id")
                    or metadata.get("source_parent_id")
                    or ""
                ),
            )
            if key not in merged:
                merged[key] = dict(item)
                merged[key]["supports_task_ids"] = list(
                    item.get("supports_task_ids") or []
                )
            else:
                supports = merged[key].setdefault("supports_task_ids", [])
                for task_id in item.get("supports_task_ids") or []:
                    if task_id not in supports:
                        supports.append(task_id)
        return list(merged.values())

    @staticmethod
    def _merge_task_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Merge task citations and retain their supporting task identities."""

        merged: dict[tuple[Any, ...], dict[str, Any]] = {}
        for citation in citations:
            canonical_source_id = (
                citation.get("source_parent_id")
                or citation.get("parent_section_id")
                or citation.get("chunk_id")
                or citation.get("document_id")
                or citation.get("source_section")
                or citation.get("title")
            )
            key = (
                str(citation.get("cohort") or "default"),
                str(canonical_source_id or ""),
                # A fact lock belongs to this task/input, not every question
                # citing the same article. Keep unlocked source fusion unchanged.
                (
                    tuple(sorted(citation.get("supports_task_ids") or [])),
                    json.dumps(citation["resolved_result"], sort_keys=True, default=str),
                ) if citation.get("resolved_result") is not None else None,
            )
            if key not in merged:
                merged[key] = dict(citation)
                merged[key]["supports_task_ids"] = list(
                    citation.get("supports_task_ids") or []
                )
            else:
                supports = merged[key].setdefault("supports_task_ids", [])
                for task_id in citation.get("supports_task_ids") or []:
                    if task_id not in supports:
                        supports.append(task_id)
                if (
                    merged[key].get("evidence_kind") == "structured_result"
                    and citation.get("evidence_kind") == "structured_result"
                ):
                    merged[key]["content"] = _merge_structured_citation_content(
                        merged[key],
                        citation,
                    )
                    merged[key]["source_pages"] = sorted(
                        {
                            *list(merged[key].get("source_pages") or []),
                            *list(citation.get("source_pages") or []),
                        }
                    )
        return list(merged.values())

    @staticmethod
    def _select_task_primary_citations(
        citations: list[dict[str, Any]],
        coverage_by_task: dict[str, str],
        *,
        max_sources: int,
    ) -> list[dict[str, Any]]:
        """Select balanced primary evidence across planned tasks."""

        selected: list[dict[str, Any]] = []
        selected_ids: set[int] = set()
        for task_id, coverage in coverage_by_task.items():
            if coverage != "covered":
                continue
            for index, citation in enumerate(citations):
                if task_id in (citation.get("supports_task_ids") or []):
                    if index not in selected_ids:
                        selected.append(citation)
                        selected_ids.add(index)
                    break
        for index, citation in enumerate(citations):
            if len(selected) >= max_sources:
                break
            if index not in selected_ids:
                selected.append(citation)
        return selected[:max_sources]
