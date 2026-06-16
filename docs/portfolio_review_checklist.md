# Portfolio Review Checklist

Use this checklist before making the repository public or sending it with a CV.

## Must Have

- `python -m compileall src scripts tests` passes.
- `python -m unittest discover -s tests` passes with 55 tests.
- `python -m scripts.evaluate_router_behavior --fail-under-intent 0.95 --fail-under-strategy 0.95` passes.
- `python -m scripts.evaluate_answers --fail-under-pass-rate 1.0` passes.
- README includes the Vercel frontend and Hugging Face backend demo links.
- README includes the latest router and answer-evaluation summaries.
- Hugging Face backend deployment docs match the current Qdrant Cloud workflow.
- `.env`, API keys, and `data/cache/` are not committed.
- `data/vectorstore/` is committed intentionally only in the main repo for local reproducibility.
- The Hugging Face Space repository does not include frontend, tests, docs, or local ChromaDB when Qdrant Cloud is configured.
- Public UI debug output is disabled unless `STUDENT_RAG_SHOW_DEBUG=true`.
- API query length and optional rate-limit environment variables are documented.
- Raw PDF redistribution rights are reviewed and the README data policy is explicit.

## Demo Script

1. `CNTT ở đâu?` shows clarification instead of guessing.
2. `Điểm B+ quy đổi sang hệ 4 bao nhiêu?` uses deterministic structured lookup.
3. `Email Phòng Đào tạo là gì?` shows directory retrieval and citation.
4. Ask a follow-up after a scholarship question to show LLM context resolution
   and safe query rewriting.
5. Ask `năm nhất có khác không?` after a scholarship question to show that
   follow-ups do not depend on a fixed phrase list.
6. Ask an unrelated new question after that to show old context is not reused blindly.
7. Ask a vague follow-up such as `bên đó thì sao?` to show clarification instead
   of unsafe history reuse.
8. Ask `mấy điểm thì qua môn` and confirm the answer uses Điều 10, not a fallback.
9. Ask `mấy điểm thì được điểm A` and confirm it returns the A range, not scholarship scoring.
10. Open the evaluation report and explain router/answer pass rates.

## Reviewer Talking Points

- The project separates ingestion, chunking, retrieval, generation, API, and UI.
- Deterministic lookup avoids unnecessary LLM calls for table/tool queries.
- Guardrails cover ambiguity, low confidence, out-of-domain, Gemini failure, and backend connection failure.
- Multi-turn safety uses LLM context classification, safe rewrite validation,
  and dual retrieval verification to reduce context contamination.
- Retrieval and answer behavior are measured with offline regression sets rather than only manual examples.
- Entity aliases include accent-folded plus conservative fuzzy matching for light typos.
