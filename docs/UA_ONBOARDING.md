# Onboarding Guide: HCMUE Student Handbook RAG

> **Graph scope:** This guide is based on the runtime-focused knowledge graph in
> `.ua/knowledge-graph.json`, generated for source commit `65418b02` on
> 2026-09-04. It maps the 30 most important runtime components and their main
> dependencies. It is intentionally not a function-by-function graph of all
> 500 repository files.

## 1. Project Overview

This repository implements an HCMUE student handbook RAG assistant. The
backend uses FastAPI, Qdrant, MongoDB, optional Redis, and Gemini generation.
The React/Vite frontend renders synchronous and SSE streaming answers,
citations, structured results, and per-answer feedback.

Read [README.md](../README.md) first. It is the source of truth for the
current architecture, runtime boundaries, evaluation governance, and
deployment workflow.

## 2. Architecture Layers

| Layer | Responsibility | Start here |
| --- | --- | --- |
| Documentation | Runtime boundaries and operational contracts | `README.md` |
| CI and deployment | Quality checks and backend packaging | `.github/workflows/ci.yml`, `scripts/deploy_hf_backend.ps1` |
| Runtime configuration | Retrieval, generation, cache, and storage identity | `configs/retrieval.yaml`, `configs/answer_generation.yaml` |
| API and streaming | FastAPI lifecycle, chat routes, SSE, readiness | `src/api/main.py`, `src/api/routes/` |
| Answer generation | Query orchestration, citations, cache, Gemini | `src/generation/answer_pipeline.py` |
| Retrieval | Query plan, vector search, BM25, evidence assembly | `src/retrieval/core/hybrid_pipeline.py` |
| Frontend | Chat UX, citations, feedback, status display | `frontend/src/` |
| Evaluation | Frozen benchmark selection and regression gates | `scripts/evaluate_system.py`, `tests/` |

## 3. Key Runtime Decisions

- `configs/retrieval.yaml` is the retrieval runtime source of truth. Avoid
  adding model or top-k hard-codes outside that configuration path.
- `AnswerPipeline` is the central orchestration seam. It handles routing,
  deterministic lookup, retrieval, guardrails, prompts, generation, citations,
  cache handling, and compound-task aggregation.
- The response cache is exact and context-aware. A hit skips Gemini generation
  but does not skip routing or retrieval. Redis is used when configured; the
  local JSON fallback has a TTL, global expiry pruning, and a bounded size.
- The graph feature supplies UI related references only. Retrieved source
  chunks remain the evidence used to answer a question.
- The current operating boundary is one worker per replica. Redis is required
  before scaling cache or rate-limit state horizontally. Local BM25 is suitable
  for the current corpus; revisit lexical retrieval only when corpus size or
  observed traffic requires it.
- Like/Dislike feedback is attached to the relevant LangSmith run. There is no
  duplicate Google Apps Script feedback path.

## 4. Guided Tour

1. **Read the project contract.** Start with `README.md` and identify the
   single-worker boundary, storage collections, quality claims, and deploy
   workflow.
2. **Establish runtime identity.** Read `configs/retrieval.yaml`,
   `configs/answer_generation.yaml`,
   `data/processed/metadata/build_manifest.json`, and
   `src/common/storage_config.py`.
3. **Follow an API request.** Read `src/api/main.py`, then
   `src/api/routes/chat.py`, `src/api/routes/chat_stream.py`, and
   `src/api/sse_events.py`.
4. **Study answer orchestration.** Read `src/generation/answer_pipeline.py`
   before diving into helpers. Focus on routing, task execution, aggregation,
   citations, and cache decisions.
5. **Study retrieval.** Read `src/retrieval/core/hybrid_pipeline.py`, then
   `vector_retriever.py`, `bm25_retriever.py`, and `query_plan.py`.
6. **Study provider and cache boundaries.** Read `gemini_client.py` and
   `response_cache.py`.
7. **Cross-check the user experience.** Read `frontend/src/App.tsx`,
   `frontend/src/components/ChatMessage.tsx`, and
   `frontend/src/components/SystemStatusBadge.tsx`.
8. **Finish with quality gates.** Read `scripts/evaluate_system.py`,
   `tests/test_product_regression.py`, `tests/test_evaluation.py`, and
   `scripts/deploy_hf_backend.ps1`.

## 5. File Map

### API and streaming

- `src/api/main.py`: application creation, middleware, routes, and lifecycle.
- `src/api/routes/chat.py`: synchronous chat and answer feedback endpoint.
- `src/api/routes/chat_stream.py`: streaming route and SSE rendering path.
- `src/api/sse_events.py`: SSE event construction and finalization.
- `src/api/routes/health.py`: health and readiness contracts.

### Answer generation

- `src/generation/answer_pipeline.py`: central RAG orchestration.
- `src/retrieval/core/ai_router.py`: intent classification, task planning, and
  output-token budgets.
- `src/generation/gemini_client.py`: Gemini request boundary and usage data.
- `src/generation/response_cache.py`: Redis/local response cache behavior.

### Retrieval

- `src/retrieval/core/hybrid_pipeline.py`: hybrid retrieval and evidence
  assembly.
- `src/retrieval/core/vector_retriever.py`: Qdrant semantic retrieval.
- `src/retrieval/core/bm25_retriever.py`: local lexical retrieval signal.
- `src/retrieval/core/query_plan.py`: task decomposition and aggregation
  contracts.

### Frontend and feedback

- `frontend/src/App.tsx`: application shell, navigation, and cohort state.
- `frontend/src/components/ChatMessage.tsx`: answer rendering, citations, and
  LangSmith feedback UX.
- `frontend/src/components/SystemStatusBadge.tsx`: public Space and readiness
  status display.

### Quality and deployment

- `scripts/evaluate_system.py`: default V9.1 corrected benchmark selection.
- `tests/test_product_regression.py`: user-facing regression contract.
- `tests/test_evaluation.py`: benchmark and evaluation contract tests.
- `tests/test_response_cache.py`: cache TTL, prune, eviction, and legacy tests.
- `scripts/deploy_hf_backend.ps1`: allow-listed Hugging Face backend package.

## 6. Complexity Hotspots

Read these files in focused passes rather than linearly in one sitting:

1. `src/generation/answer_pipeline.py`
2. `src/retrieval/core/hybrid_pipeline.py`
3. `src/retrieval/core/ai_router.py`
4. `src/generation/gemini_client.py`
5. `scripts/evaluate_system.py` and `tests/test_evaluation.py`

For each hotspot, first identify its inputs, outputs, configuration sources,
and tests. Only then read its internal helper functions.

## 7. Using Understand Anything Locally

Use `$understand-dashboard` in Codex to open the graph locally. The dashboard
serves `.ua/knowledge-graph.json` on `127.0.0.1`; it does not upload source
code or graph data.

The committed graph is a useful architectural map for onboarding. If the
runtime architecture changes materially, regenerate and review the graph
before updating this guide.
