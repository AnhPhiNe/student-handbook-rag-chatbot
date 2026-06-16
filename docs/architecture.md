# Architecture

This project is split into two flows:

- **Offline data preparation:** parse the HCMUE student handbook and build
  retrieval artifacts.
- **Runtime answering:** receive user questions, retrieve grounded evidence, run
  guardrails, and return an answer with citations.

## Offline Data Preparation

```text
data/raw/so-tay-sinh-vien-khoa-48.pdf
  -> src.ingestion
  -> src.preprocessing
  -> src.extraction
  -> src.chunking
  -> src.retrieval.vectorstore
  -> data/processed + local ChromaDB
  -> optional migration to Qdrant Cloud
```

Responsibilities:

- `src.ingestion`: loads page-level text from the source PDF.
- `src.preprocessing`: parses handbook structure and section metadata.
- `src.extraction`: extracts scoring tables, formulas, forms, procedures,
  office directories, and faculty/program directories.
- `src.chunking`: creates semantic chunks, structured lookup chunks, formula
  chunks, tool-rule chunks, form chunks, procedure chunks, and directory chunks.
- `src.retrieval.vectorstore`: embeds semantic chunks and stores them locally in
  ChromaDB or uploads/searches through Qdrant Cloud.

The main GitHub repo includes a small local ChromaDB vectorstore for
reproducibility. The production Hugging Face backend uses Qdrant Cloud.

## Runtime Answering Path

```text
React/Vite frontend
  -> FastAPI route: /chat or /chat/stream
  -> src.services.AnswerService
  -> src.generation.AnswerPipeline
      -> LLM ContextResolver
          -> standalone_new_topic: continue without history
          -> follow_up: produce a standalone retrieval query
          -> ambiguous: return a clarification signal
      -> QueryRewriter
          -> normalize accentless/typo-heavy standalone queries
          -> accept only safe history-based rewrites
      -> dual retrieval verification for history-based rewrites
  -> src.retrieval.core.run_retrieval_pipeline
      -> entity linking
      -> query expansion
      -> rule router, with optional Groq AI Router fallback
      -> deterministic branch or semantic retrieval branch
  -> answer guardrails
  -> response cache or Gemini generation
  -> formatted answer with citations
```

### 1. React/Vite Frontend

The frontend sends user messages and chat history to the FastAPI backend. It
supports streaming responses through `/chat/stream` and renders citations from
the metadata events returned by the backend.

### 2. FastAPI Routes

`src/api` owns HTTP concerns only:

- request validation;
- empty/overlong query rejection;
- optional in-memory rate limiting;
- request ID and latency metadata;
- mapping service output into API schemas.

It does not duplicate retrieval, guardrail, cache, or LLM logic.

### 3. AnswerService

`src/services/answer_service.py` is a thin service layer between API routes and
the RAG pipeline. It provides:

- `answer(...)` for normal responses;
- `answer_stream(...)` for Server-Sent Events;
- lazy loading of `AnswerPipeline`, so `/health` can stay lightweight.

This keeps API code simple and avoids loading the embedding model/vector
database until the first real answer request.

### 4. AnswerPipeline

`src/generation/answer_pipeline.py` orchestrates the runtime RAG flow:

1. Resolve whether the current query is standalone, a follow-up, or ambiguous.
2. Return a clarification response when context is ambiguous.
3. Rewrite/normalize the query if needed.
4. Validate that the rewrite does not add unsupported entities.
5. Verify history-based rewrites with dual retrieval.
6. Apply retrieval clarification and out-of-domain guardrails.
7. Return deterministic answers when a structured/tool result is available.
8. Select citations.
9. Use the response cache when possible.
10. Call Gemini only when the answer requires natural-language generation.
11. Format the final answer with source citations.

### 5. ContextResolver And QueryRewriter

`ContextResolver` runs before `QueryRewriter`. When query rewriting is enabled
and `chat_history` is present, it asks the Groq/Llama model to classify the
current query as:

- `standalone_new_topic`
- `follow_up`
- `ambiguous`

If no chat history is present, the resolver returns `no_history` and does not
call the model. The resolver no longer decides follow-up status from a
hardcoded phrase list. Instead, the LLM returns a JSON decision with confidence,
referenced turns, and an optional standalone query. The code then validates that
decision:

- `follow_up` is accepted only with high confidence and a standalone query.
- `standalone_new_topic` prevents chat history from being passed into rewrite.
- `ambiguous` or low-confidence decisions produce a clarification signal.

The resolver does not send a message to the user by itself. It returns
`needs_clarification` and `clarification_question` in `QueryRewriteResult`;
`AnswerPipeline` decides whether that clarification should be returned to the
API/frontend.

`QueryRewriter` normalizes accentless or typo-heavy Vietnamese queries and uses
the resolver output for real follow-ups. Safe rewrite validation prevents the
model from adding entities that are not present in the current query or the
referenced history.

For history-based rewrites, `AnswerPipeline` performs dual retrieval:

```text
original query retrieval
rewritten query retrieval
  -> compare answerability, intent, chunk types, and retrieval quality
  -> choose the stronger query, fallback to original, or ask for clarification
```

This reduces context contamination and semantic drift before the answer
generator sees any retrieved context.

### 6. RetrievalPipeline

`src/retrieval/core/retrieval_pipeline.py` coordinates retrieval:

```text
detect_entities
  -> normalize_query_with_entities
  -> expand_query
  -> route_query
  -> optional AIRouter fallback
  -> strategy-specific execution
```

Strategy branches:

- `calculator_tool`: deterministic scholarship-score calculation.
- `formula_lookup`: deterministic formula lookup, with vector fallback if no
  formula matches.
- `structured_lookup`: deterministic score-table lookup, with vector fallback if
  no table row matches.
- semantic strategies: build one or more retrieval plans, search the vector DB,
  rerank results, merge plans, build citations, and build context for the LLM.

### 7. Router

`src/retrieval/core/query_router.py` is the first intent layer. It uses
domain-specific rules for:

- forms;
- regulations;
- KTX/procedures;
- offices and contact information;
- faculties and programs;
- GPA/scoring lookup;
- formula lookup;
- calculator-tool queries.

If a route is unknown or ambiguous enough to require deeper analysis, the
pipeline can fall back to `AIRouter`, which uses Groq. If Groq credentials are
missing, retrieval falls back conservatively instead of failing.

### 8. Entity Linking

`src/retrieval/core/entity_linker.py` matches offices, faculties, programs, and
common aliases. It uses:

- normalized exact phrase matching with word boundaries;
- accent-folded aliases;
- conservative fuzzy matching for longer aliases;
- canonical-name expansion to improve embedding retrieval.

This is why queries such as `Khoa CNTT ở đâu?` and `Phòng CNTT ở đâu?` can route
to different source types.

### 9. VectorDB Factory

`src/retrieval/vectorstore/vectorstore_factory.py` selects the vector provider:

```text
VECTORDB_PROVIDER=chroma        -> local ChromaDB
VECTORDB_PROVIDER=qdrant_cloud  -> Qdrant Cloud
```

The Qdrant adapter exposes a Chroma-like `.query(...)` interface so existing
retrieval code can work with either provider.

### 10. Answer Guardrails

`src/generation/answer_guardrails.py` handles safety and answerability:

- deterministic result detection;
- ambiguity detection and clarification questions;
- low-confidence fallback;
- out-of-domain fallback;
- deterministic answer formatting for lookup/formula/tool results.

Important ordering:

```text
retrieval clarification
  -> ambiguity clarification
  -> out-of-domain guard
  -> deterministic answer
  -> low-confidence fallback
  -> cache / Gemini generation
```

## Module Boundaries

- `frontend`: React/Vite web UI.
- `src/api`: FastAPI application, routes, schemas, and dependency wiring.
- `src/services`: service contract between API and pipeline.
- `src/generation`: query rewriting, answer pipeline, guardrails, citation
  formatting, prompt building, response cache, and Gemini client.
- `src/retrieval/core`: routing, entity linking, query expansion, retrieval
  orchestration, reranking, structured lookup, formula lookup, and calculator
  tools.
- `src/retrieval/vectorstore`: embedding/vectorstore provider access.
- `src/extraction`: structured data extraction from parsed handbook data.
- `src/chunking`: chunk-building and index manifest generation.
- `src/preprocessing`: structure parsing helpers.
- `src/ingestion`: raw PDF loading.
- `src/common`: shared environment, logging, and console utilities.
- `configs`: YAML configuration for pipeline stages.
- `scripts`: local preprocessing and evaluation entrypoints.
- `tests`: offline unit/API tests that should not call Gemini.
