# Architecture

This project keeps the production path small and explicit:

```text
app.py
  -> src.ui.phase9
  -> src.services.AnswerService
  -> src.chatbot.phase8
  -> src.retrieval.phase7
  -> src.retrieval.phase6 / ChromaDB
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
- `src/ui`: Streamlit UI code.
- `src/chatbot`: Answer-generation pipeline and guardrails.
- `src/retrieval`: Embedding, vectorstore access, retrieval, reranking, and structured lookup.
- `src/preprocessing`: Parsing and chunk-building phases.
- `src/ingestion`: Raw PDF loading.
- `src/common`: Shared cross-cutting utilities such as environment loading.
- `configs`: YAML configuration for pipeline phases.
- `scripts`: Thin local entrypoints for phase runners and evaluation scripts.
- `tests`: Offline unit/API tests that should not call Gemini.

## Refactor Notes

Phase folders are intentionally preserved for now. They contain many internal
relative imports and represent stable milestones in the project history, so
renaming them should be a separate, tested migration.
