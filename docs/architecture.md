# Architecture

This project keeps the production path small and explicit:

```text
app.py
  -> src.ui.streamlit
  -> src.services.AnswerService
  -> src.generation
  -> src.retrieval.core
  -> src.retrieval.vectorstore / ChromaDB
```

The FastAPI entrypoint uses the same service contract:

```text
src.api.main
  -> src.api.routes.chat
  -> src.services.AnswerService
```

## Module Boundaries

- `src/api`: FastAPI application, routes, schemas, and dependency wiring.
- `src/services`: Shared application service contracts used by UI and API.
- `src/ui/streamlit`: Streamlit UI code.
- `src/generation`: Answer-generation pipeline and guardrails.
- `src/retrieval/core`: Retrieval orchestration, reranking, and structured lookup.
- `src/retrieval/vectorstore`: Embedding and ChromaDB vectorstore access.
- `src/extraction`: Structured extraction from parsed handbook data.
- `src/chunking`: Chunk-building and index manifest generation.
- `src/preprocessing`: Shared preprocessing helpers outside the production runtime path.
- `src/ingestion`: Raw PDF loading.
- `src/common`: Shared cross-cutting utilities such as environment loading.
- `configs`: YAML configuration for pipeline stages.
- `scripts`: Thin local entrypoints for pipeline runners and evaluation scripts.
- `tests`: Offline unit/API tests that should not call Gemini.

## Refactor Notes

Legacy phase package names were migrated to production-oriented package names in
the P2 refactor. Historical phase terminology remains only in config/report file
names and script wrapper names where it documents the original pipeline stages.
