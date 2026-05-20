# HCMUE Student Handbook RAG Assistant

An AI chatbot for answering questions from the HCMUE student handbook using a local Retrieval-Augmented Generation (RAG) pipeline, ChromaDB vector search, deterministic lookup tools, and Gemini answer generation.

This project is built as an AI Engineer Intern portfolio project: the focus is on practical document processing, retrieval quality, guardrails, citations, and a usable Streamlit interface.

The current pipeline is intentionally tailored to the HCMUE student handbook used
in this repository. It is not a generic "upload any PDF" chatbot without further
parser, chunking, entity, and routing adaptation.

## Live Demo

- Streamlit Cloud UI: https://student-handbook-rag-hcmue.streamlit.app/
- Hugging Face Spaces backend: https://huggingface.co/spaces/AnhFeee/hcmue-handbook-rag-api

The public demo uses a two-repository deployment model: Streamlit Cloud hosts
the UI, and a Hugging Face Docker Space hosts the FastAPI backend with its own
copy of the prebuilt ChromaDB vectorstore.

## Key Features

- PDF ingestion and structured parsing for a Vietnamese student handbook.
- Semantic chunking by regulations, procedures, forms, scoring tables, and directories.
- Sentence-transformer embeddings stored in ChromaDB.
- Query routing for regulations, forms, offices, faculties, scoring lookup, and calculator-style questions.
- Entity linking and query expansion for handbook-specific terms.
- Answer guardrails: low-confidence fallback, deterministic lookup answers, citations, and clarification for ambiguous queries.
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
answer guardrails -> Gemini answer generation or deterministic answer
        |
        v
AnswerService shared contract / FastAPI backend
        |
        v
Streamlit chatbot UI with Local/API execution modes
```

The Streamlit app can run in two execution modes. In Local mode it calls
`AnswerService` directly, which lazy-loads `AnswerPipeline`. In API mode it
calls the FastAPI `POST /chat` endpoint through a small `ChatApiClient`, so the
UI can use the same response schema without duplicating guardrail, retrieval,
citation, cache, or Gemini logic.

## Pipeline Overview

- PDF ingestion: Load the handbook PDF and extract page-level text.
- Structure parsing: Build normalized sections and line metadata.
- Structured extraction: Extract tables, formulas, thresholds, forms, office directories, faculty directories, and procedures.
- Chunk generation: Build semantic, structured lookup, and tool-rule chunks.
- Embedding and indexing: Embed semantic chunks and persist them to ChromaDB.
- Retrieval orchestration: Route queries, link entities, expand queries, retrieve, and rerank.
- Answer pipeline: Generate answers with guardrails, citations, deterministic lookup, cache, and ambiguity handling.
- Service layer: Expose a thin `AnswerService` wrapper for shared UI/API use.
- User interface: Serve the chatbot through a Streamlit UI that can call either
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

For exact local reproduction of the verified environment, use the generated
lockfile:

```bash
pip install -r requirements.lock
```

The lockfile records one tested local environment. The looser
`requirements.txt` remains the portable install target for development and CI.

## Environment Variables

Create a local `.env` file from the example:

```bash
copy .env.example .env
```

Then set your Gemini key inside `.env`:

```bash
GEMINI_API_KEY=your_api_key_here
```

The Streamlit app, FastAPI backend, and answer-generation scripts load this project-level
`.env` automatically, so you do not need to run `$env:GEMINI_API_KEY=...` in each
terminal session.

Do not commit `.env` or `.streamlit/secrets.toml`.

## Run the Streamlit App

```bash
python -m streamlit run app.py --server.fileWatcherType none
```

The Streamlit app defaults to `Local` mode so a first-time portfolio reviewer can
try the chatbot without starting the FastAPI server. In the Streamlit sidebar,
choose:

- `Local` to run Streamlit -> `AnswerService` in the same process.
- `API` to run Streamlit -> FastAPI `POST /chat`.

API mode shows an `API base URL` field. The default is:

```text
http://127.0.0.1:8000
```

The app expects the configured processed data and ChromaDB vectorstore to exist locally. If the vectorstore is missing, rebuild the local data artifacts before running the chatbot. In API mode, start the FastAPI backend before sending chat messages.

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

The API reuses `AnswerService`, which lazy-loads the answer pipeline. `GET /health`
does not load the retrieval pipeline or call Gemini.

## Deployment Workflow

Recommended public demo architecture:

```text
Streamlit Cloud UI -> FastAPI backend -> ChromaDB vectorstore + Gemini
```

The public portfolio demo currently uses Streamlit Cloud for `app.py` and a
Hugging Face Docker Space for the FastAPI backend:

```text
UI:      https://student-handbook-rag-hcmue.streamlit.app/
Backend: https://huggingface.co/spaces/AnhFeee/hcmue-handbook-rag-api
```

Set the Streamlit Cloud app to API mode:

```text
STUDENT_RAG_EXECUTION_MODE=API
STUDENT_RAG_API_BASE_URL=https://your-fastapi-backend.example.com
```

Set backend secrets/config:

```text
GEMINI_API_KEY=...
STUDENT_RAG_CORS_ORIGINS=https://your-streamlit-app.streamlit.app
```

See `docs/huggingface_backend_deploy.md` for the backend deployment workflow
used by the live demo.

For the current two-repository deployment model:

- This main repository includes the demo source PDF and a small prebuilt
  ChromaDB vectorstore for portfolio reproducibility.
- The Hugging Face backend repository keeps its own copy of
  `data/vectorstore/chroma` as a deployment artifact so the API can serve
  retrieval without rebuilding the index at startup.
- The root `Dockerfile` is kept as the FastAPI backend image template used when
  preparing the Hugging Face Docker Space repository. Docker Compose and Render
  deployment files are intentionally not part of the main repo.
- If the PDF, parser, chunking logic, embedding model, or retrieval config
  changes, rebuild the processed artifacts and vectorstore with
  `python -m scripts.run_all_preprocessing`.

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

This runs PDF extraction, structure parsing, structured extraction, chunking,
ChromaDB embedding, and the retrieval batch report. It can take several minutes
because the embedding model and ChromaDB vectorstore are rebuilt locally.

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

Router behavior coverage is larger and faster because it does not require the
embedding model or vectorstore:

```bash
python -m scripts.evaluate_router_behavior --fail-under-intent 0.95 --fail-under-strategy 0.95
```

Current router behavior set:

| Metric | Result |
|---|---:|
| Behavior queries | 110 |
| Intent accuracy | 100% |
| Strategy accuracy | 100% |
| Target chunk-type accuracy | 100% |

Offline answer evaluation checks deterministic exactness, guardrail status, and
citation selection without calling Gemini:

```bash
python -m scripts.evaluate_answers --fail-under-pass-rate 1.0
```

Current offline answer evaluation summary:

| Metric | Result |
|---|---:|
| Answer eval cases | 14 |
| Pass rate | 100% |
| Status accuracy | 100% |
| Deterministic exactness | 100% |
| Citation type/page checks | 100% |

Optional answer-generation batch test, using the configured local retrieval pipeline:

```bash
python -m scripts.evaluate_answer_batch --all
```

Direct module entrypoints after the package refactor:

```bash
python -m src.ingestion.pdf_loader
python -m src.preprocessing.structure_parser
python -m src.extraction.runner
python -m src.chunking.runner
python -m src.retrieval.vectorstore.runner
python -m src.retrieval.core.runner
python -m src.retrieval.core.retrieval_batch_eval
python -m src.generation.runner
python -m src.generation.answer_batch_eval
```

Write a local reproducibility report:

```bash
python -m scripts.write_reproducibility_report
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

## Demo Flow

Recommended manual demo flow:

1. Ask `CNTT ở đâu?` to show ambiguity detection and clarification.
2. Ask `Điểm rèn luyện 85 là loại gì?` to show deterministic lookup.
3. Ask `Email phòng Đào tạo là gì?` to show cited directory retrieval.
4. Switch Streamlit from Local mode to API mode and ask the same question.

## Data Policy

This repository intentionally includes the demo source PDF at:

```text
data/raw/so-tay-sinh-vien-khoa-48.pdf
```

It is used as the source document for portfolio demonstration, parsing, and
local reproducibility. The project does not relicense the source document;
ownership remains with the original publisher/source. If you reuse this project
with another document, review the source document's license/copyright status
before publishing the PDF or derived artifacts.

This repository also includes a small prebuilt ChromaDB vectorstore at:

```text
data/vectorstore/chroma
```

The vectorstore is generated from the demo PDF so reviewers can run retrieval
and the chatbot without rebuilding the full preprocessing and embedding
pipeline. It can be regenerated with:

```bash
python -m scripts.run_all_preprocessing
```

Adapting the system to another handbook or policy document will likely require
updating the parsing configuration, extraction rules, chunking assumptions,
entity registry, and query routing rules before rebuilding the local index.

## License

Project source code and authored documentation are released under the MIT
License. The source handbook PDF and generated artifacts derived from it are not
relicensed by this repository and remain subject to their original rights.

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
- Public deployment requires a backend that can access `data/vectorstore/chroma`.
- Gemini calls require a valid `GEMINI_API_KEY` in `.env` or the process environment.
- Some source PDF layouts may require manual validation after parsing.
- The bundled vectorstore is a generated demo artifact; rebuild it after
  changing the PDF, configs, chunking logic, or embedding model.
- The source PDF and generated vectorstore may contain or derive from handbook
  content, so redistribution rights should be reviewed before public reuse.
- Source files are UTF-8. If Vietnamese text appears garbled in Windows PowerShell,
  read files with `Get-Content -Encoding UTF8 ...` or use a UTF-8 terminal.

## Future Improvements

- Expand the golden retrieval evaluation set beyond the current small portfolio benchmark.
- Add screenshot assets and a short demo GIF for the portfolio README.
- Continue moving domain heuristics from Python code into YAML configs.
- Improve entity registry quality for abbreviations and department aliases.
