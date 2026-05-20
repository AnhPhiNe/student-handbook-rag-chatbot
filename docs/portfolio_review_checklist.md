# Portfolio Review Checklist

Use this checklist before making the repository public or sending it with a CV.

## Must Have

- `python -m compileall src app.py scripts` passes.
- `python -m unittest discover -s tests` passes.
- `python -m scripts.evaluate_retrieval` runs after vectorstore rebuild.
- README has screenshots or a short demo GIF.
- README includes the latest retrieval metric summary.
- Dockerfile starts the FastAPI backend with a mounted vectorstore.
- `.env` and `data/cache/` are not committed.
- `data/vectorstore/` is not committed unless intentionally publishing a small demo index.
- Raw PDF redistribution rights are cleared, or raw PDFs are removed from Git tracking before public release.
- Generated processed artifacts are reviewed because they may contain extracted text from the raw PDF.

## Demo Script

1. `CNTT ở đâu?` shows clarification instead of guessing.
2. `Điểm rèn luyện 85 là loại gì?` uses deterministic lookup.
3. `Email phòng Đào tạo là gì?` shows directory retrieval and citation.
4. Switch Streamlit to API mode and repeat one query.
5. Open the evaluation report and explain Hit@K/MRR.

## Reviewer Talking Points

- The project separates ingestion, chunking, retrieval, generation, API, and UI.
- Deterministic lookup avoids unnecessary LLM calls for table/tool queries.
- Guardrails cover ambiguity, low confidence, out-of-domain, Gemini failure, and backend connection failure.
- Retrieval quality is measured with a golden set rather than judged only by manual examples.
