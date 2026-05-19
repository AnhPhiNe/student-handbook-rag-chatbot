# HCMUE Student Handbook RAG Assistant

An AI chatbot for answering questions from the HCMUE student handbook using a local Retrieval-Augmented Generation (RAG) pipeline, ChromaDB vector search, deterministic lookup tools, and Gemini answer generation.

This project is built as an AI Engineer Intern portfolio project: the focus is on practical document processing, retrieval quality, guardrails, citations, and a usable Streamlit interface.

## Key Features

- PDF ingestion and structured parsing for a Vietnamese student handbook.
- Semantic chunking by regulations, procedures, forms, scoring tables, and directories.
- Sentence-transformer embeddings stored in ChromaDB.
- Query routing for regulations, forms, offices, faculties, scoring lookup, and calculator-style questions.
- Entity linking and query expansion for handbook-specific terms.
- Phase 8 answer guardrails: low-confidence fallback, deterministic lookup answers, citations, and clarification for ambiguous queries.
- Streamlit chat UI with source display and optional debug information.

## Architecture Overview

```text
Student handbook PDF
        |
        v
PDF/text extraction -> structure parsing -> entity/form/table extraction
        |
        v
chunking -> embeddings -> ChromaDB vectorstore
        |
        v
query routing + entity linking + retrieval/reranking
        |
        v
Phase 8 guardrails -> Gemini answer generation or deterministic answer
        |
        v
AnswerService shared contract / FastAPI backend
        |
        v
Streamlit chatbot UI with Local/API execution modes
```

The Streamlit app can run in two execution modes. In Local mode it calls
`AnswerService` directly, which lazy-loads `Phase8AnswerPipeline`. In API mode it
calls the FastAPI `POST /chat` endpoint through a small `ChatApiClient`, so the
UI can use the same response schema without duplicating guardrail, retrieval,
citation, cache, or Gemini logic.

## Pipeline Phases

- Phase 1-3: Load the handbook PDF, extract page text, and build structured sections.
- Phase 4: Extract tables, formulas, thresholds, forms, office directories, faculty directories, and procedures.
- Phase 5: Build semantic, structured lookup, and tool-rule chunks.
- Phase 6: Embed semantic chunks and persist them to ChromaDB.
- Phase 7: Route queries, link entities, expand queries, retrieve, and rerank.
- Phase 8: Generate answers with guardrails, citations, deterministic lookup, cache, and ambiguity handling.
- Service layer: Expose a thin `AnswerService` wrapper around Phase 8 for shared UI/API use.
- Phase 9: Serve the chatbot through a Streamlit UI that can call either
  `AnswerService` directly or the FastAPI `/chat` backend.

## Project Structure

Current production-oriented layout:

```text
.
|-- app.py
|-- configs/
|-- data/
|-- docs/
|-- scripts/
|-- src/
|   |-- api/
|   |-- services/
|   |-- ui/phase9/
|   |-- retrieval/
|   |-- chatbot/phase8/
|   |-- ingestion/
|   |-- preprocessing/
|   `-- common/
|-- tests/
|-- requirements.txt
`-- .env.example
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

On macOS/Linux, activate the environment with:

```bash
source .venv/bin/activate
```

## Environment Variables

Create a local `.env` file from the example:

```bash
copy .env.example .env
```

Then set your Gemini key inside `.env`:

```bash
GEMINI_API_KEY=your_api_key_here
```

The Streamlit app, FastAPI backend, and Phase 8 scripts load this project-level
`.env` automatically, so you do not need to run `$env:GEMINI_API_KEY=...` in each
terminal session.

Do not commit `.env` or `.streamlit/secrets.toml`.

## Run the Streamlit App

```bash
python -m streamlit run app.py --server.fileWatcherType none
```

In the Streamlit sidebar, choose:

- `Local` to run Streamlit -> `AnswerService` in the same process.
- `API` to run Streamlit -> FastAPI `POST /chat`.

API mode shows an `API base URL` field. The default is:

```text
http://127.0.0.1:8000
```

The app expects the configured processed data and ChromaDB vectorstore to exist locally. If the vectorstore is missing, rebuild the preprocessing and embedding phases before running the chatbot. In API mode, start the FastAPI backend before sending chat messages.

## Run the FastAPI Backend

Start the API server:

```bash
python -m uvicorn src.api.main:app --reload
```

Open Swagger UI:

```text
http://127.0.0.1:8000/docs
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Example chat request:

```bash
curl -X POST http://127.0.0.1:8000/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"Email Phong Dao tao la gi?\",\"include_debug\":true}"
```

The API reuses `AnswerService`, which lazy-loads the Phase 8 pipeline. `GET /health`
does not load the retrieval pipeline or call Gemini.

## Local/API Manual Test

Terminal 1:

```bash
python -m uvicorn src.api.main:app --reload
```

Terminal 2:

```bash
python -m streamlit run app.py --server.fileWatcherType none
```

In Streamlit:

- Select `Local`, then ask: `Email Phong Dao tao la gi?`
- Select `API`, keep `http://127.0.0.1:8000`, then ask the same question.
- Stop the backend while in API mode and ask again. The UI should show a friendly backend connection message, keep debug fields available, and avoid dumping a traceback.

## Run Tests

Fast offline ambiguity tests:

```bash
python -m unittest discover -s tests
```

Compile check for the production app modules:

```bash
python -m compileall src app.py scripts
```

Optional Phase 8 batch test, using the configured local retrieval pipeline:

```bash
python -m scripts.run_phase8_batch --all
```

## Example Questions

- CNTT ở đâu?
- Phòng CNTT ở đâu?
- Khoa CNTT ở đâu?
- Có thể học vượt để ra trường sớm không?
- Có giới hạn số lần học lại một môn không?
- Muốn tạm nghỉ học cần mẫu đơn nào?
- Điểm rèn luyện 85 là loại gì?
- Email phòng CTCT-HSSV là gì?

## Screenshots

Add screenshots before publishing the repository:

```text
docs/screenshots/chat_home.png
docs/screenshots/answer_with_sources.png
docs/screenshots/clarification_flow.png
```

## Tech Stack

- Python
- Streamlit
- Google Gemini API (`google-genai`)
- Sentence Transformers
- ChromaDB
- PyTorch
- PyYAML
- PyMuPDF
- FastAPI / Uvicorn
- Requests
- python-dotenv

## Limitations

- The answer quality depends on the parsed handbook data and the local ChromaDB index.
- The app has not been deployed yet.
- Gemini calls require a valid `GEMINI_API_KEY` in `.env` or the process environment.
- Some source PDF layouts may require manual validation after parsing.
- Vectorstore and response cache are local generated artifacts and are not committed by default.

## Future Improvements

- Add more automated retrieval evaluation cases.
- Add screenshot assets and a short demo GIF for the portfolio README.
- Add a clean data rebuild script that runs the pipeline phases in order.
- Improve entity registry quality for abbreviations and department aliases.
- Add CI checks for compile and offline unit tests.
