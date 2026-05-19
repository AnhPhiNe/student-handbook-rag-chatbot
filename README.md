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
|   |-- ui/streamlit/
|   |-- generation/
|   |-- retrieval/
|   |   |-- core/
|   |   `-- vectorstore/
|   |-- extraction/
|   |-- chunking/
|   |-- ingestion/
|   |-- preprocessing/
|   `-- common/
|-- tests/
|-- requirements.txt
`-- .env.example
```

## Setup

Recommended Python version: **Python 3.11**. The CI workflow also uses Python 3.11.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

On macOS/Linux, activate the environment with:

```bash
source .venv/bin/activate
```

For local development and offline checks, install the dev requirements:

```bash
pip install -r requirements-dev.txt
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

These checks are also configured in GitHub Actions (`.github/workflows/ci.yml`) so
the public portfolio repo can show whether the offline code path still works.

## Rebuild Local Data Artifacts

To rebuild the generated extraction/chunking/vectorstore artifacts in order:

```bash
python -m scripts.run_all_preprocessing
```

This runs Phase 4 extraction, Phase 5 chunking, Phase 6 ChromaDB embedding, and
the Phase 7 retrieval batch report. It can take several minutes because the
embedding model and ChromaDB vectorstore are rebuilt locally.

## Retrieval Evaluation

The repository includes a small golden retrieval set in:

```text
data/eval/golden_queries.json
```

Run the evaluator after the vectorstore exists:

```bash
python -m scripts.evaluate_retrieval
```

The report is written to:

```text
data/processed/metadata/golden_retrieval_eval_report.json
```

Current golden evaluation summary:

| Metric | Result |
|---|---:|
| Golden queries | 22 |
| Retrieval cases | 18 |
| Hit@1 | 83.33% |
| Hit@3 | 100% |
| Hit@5 | 100% |
| MRR | 91.67% |
| Intent accuracy | 100% |
| Strategy accuracy | 100% |

This is a small portfolio golden set for regression checks and retrieval-quality
sanity testing. It is not a production-grade benchmark, and the scores should not
be read as a claim that the assistant is production-ready.

Optional Phase 8 batch test, using the configured local retrieval pipeline:

```bash
python -m scripts.run_phase8_batch --all
```

Direct module entrypoints after the package refactor:

```bash
python -m src.extraction.runner
python -m src.chunking.runner
python -m src.retrieval.vectorstore.runner
python -m src.retrieval.core.runner
python -m src.retrieval.core.batch_test_phase7
python -m src.generation.runner
python -m src.generation.phase8_test
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

## Demo Screenshots

TODO: Add real screenshots before publishing the repository. Do not treat this
README as having final demo images until those assets are captured from the
actual Streamlit app.

Recommended demo flow:

1. Ask `CNTT ở đâu?` to show ambiguity detection and clarification.
2. Ask `Điểm rèn luyện 85 là loại gì?` to show deterministic lookup.
3. Ask `Email phòng Đào tạo là gì?` to show cited directory retrieval.
4. Switch Streamlit from Local mode to API mode and ask the same question.

## Data Policy

The tracked raw PDF is:

```text
data/raw/so-tay-sinh-vien-khoa-48.pdf
```

It is included for learning and demo purposes in this portfolio project. If you
publish or reuse the repository, review the source document's license/copyright
status first. Users can replace this file with their own handbook or policy
document and rerun the preprocessing pipeline to build a new local index.

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

- Expand the golden retrieval evaluation set beyond the current small portfolio benchmark.
- Add screenshot assets and a short demo GIF for the portfolio README.
- Add a clean data rebuild script that runs the pipeline phases in order.
- Continue moving domain heuristics from Python code into YAML configs.
- Improve entity registry quality for abbreviations and department aliases.
