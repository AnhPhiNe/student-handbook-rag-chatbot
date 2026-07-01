# HCMUE AI Student Handbook Assistant

> Independent student project. This repository is not an official product of Ho Chi Minh City University of Education (HCMUE). The assistant is designed to help students look up handbook information faster, but important decisions should still be checked against the cited source documents or the relevant university office.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-3670A0?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11">
  <img src="https://img.shields.io/badge/FastAPI-API-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/React-Vite-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React Vite">
  <img src="https://img.shields.io/badge/Qdrant-VectorDB-E21727?style=for-the-badge" alt="Qdrant">
  <img src="https://img.shields.io/badge/MongoDB-DocStore-4EA94B?style=for-the-badge&logo=mongodb&logoColor=white" alt="MongoDB">
  <img src="https://img.shields.io/badge/Groq-LLM-F55036?style=for-the-badge" alt="Groq">
</p>

## Why This Project Exists

HCMUE student handbooks contain a lot of useful information, but students often need fast answers to practical questions:

- "Khoa CNTT co nhung nganh nao?"
- "K50-K51 diem D+ co qua mon khong?"
- "Muon phuc khao diem thi thi lam sao?"
- "Van de hoc phi lien he phong nao?"
- "Bieu mau tam nghi hoc nam o dau?"

This project turns the handbooks into a cohort-aware RAG assistant. It combines deterministic lookup for facts that must be exact with retrieval-augmented generation for longer regulations and procedures.

## Highlights

- **Cohort-aware answers** for K48-K49 and K50-K51.
- **Structured lookup** for programs, grade thresholds, scoring tables, formulas, offices, and forms.
- **Hybrid RAG retrieval** with dense vectors, BM25, entity expansion, metadata filters, and cross-encoder reranking.
- **Parent-child document retrieval** using Qdrant for vector chunks and MongoDB for full parent context.
- **Streaming FastAPI backend** and React/Vite frontend.
- **Production-oriented guardrails** for out-of-scope questions, ambiguous queries, and missing context.
- **Evaluation-first workflow** with deterministic tests, retrieval metrics, and RAGAS-style Gemini Judge reports.

## Current System Snapshot

| Area | Current State |
|---|---:|
| Student handbook cohorts | K48-K49, K50-K51 |
| Semantic chunks in vector index | 798 |
| Parent documents in MongoDB docstore | 435 |
| Program directory records | 86 |
| Form template records | 19 |
| Qdrant collection | `student_handbook_semantic_v4` |
| Backend API | FastAPI |
| Frontend | React + Vite |

## Architecture

```mermaid
flowchart LR
    U["Student"] --> FE["React/Vite Web App"]
    FE --> API["FastAPI Backend"]

    API --> Guard["Input Guardrails"]
    Guard --> Router["AI Router + Rules"]

    Router -->|structured facts| Lookup["Structured Lookup"]
    Router -->|long regulations| Retrieval["Hybrid Retrieval"]

    Retrieval --> Qdrant["Qdrant Cloud\nsemantic child chunks"]
    Retrieval --> BM25["BM25 Sparse Index"]
    Retrieval --> Rerank["Cross-Encoder Reranker"]
    Rerank --> Mongo["MongoDB Atlas\nparent docs"]

    Lookup --> Answer["Answer Formatter / LLM"]
    Mongo --> Answer
    Answer --> Cite["Citations + Source Metadata"]
    Cite --> FE

    API -. optional .-> Redis["Redis / Local Cache"]
    API -. tracing .-> LangSmith["LangSmith"]
```

## Query Flow

1. **Validate the user query**
   - Rejects prompt-injection-like and out-of-domain requests.
   - Asks a follow-up question when the query is too ambiguous.

2. **Route by intent and content type**
   - `program_directory`: majors, faculties, cohort-specific program lists.
   - `scoring_tables` / `threshold_rules`: grade scale, pass/fail thresholds, GPA-related rules.
   - `office_directory`: offices, duties, emails, phone numbers.
   - `form_templates`: form name, purpose, source page, and guidance to the Forms page.
   - `regulation_sections` / `procedures`: longer handbook rules handled by RAG.

3. **Retrieve or lookup**
   - Structured facts are answered from JSON-backed deterministic stores.
   - Long-form questions use Qdrant + BM25 + reranking + Mongo parent-doc expansion.

4. **Generate grounded answer**
   - The LLM is used to explain and phrase the answer.
   - For structured cases, the source of truth is the lookup result, not free-form generation.
   - Citations include cohort, content type, source page, and source metadata when available.

## Data Pipeline

The ingestion pipeline is built around document profiles instead of one-off parsing rules. Each handbook is processed into structured and semantic artifacts:

```mermaid
flowchart TD
    PDF["Raw handbook PDFs"] --> Parse["PDF parsing + section detection"]
    Parse --> Profile["Document profile\ncohort, pages, section map"]
    Profile --> Extract["Structured extraction"]
    Profile --> Chunk["Semantic chunking"]

    Extract --> Programs["program_directory"]
    Extract --> Offices["office_directory"]
    Extract --> Forms["form_templates"]
    Extract --> Scores["scoring_tables / threshold_rules / formula_rules"]

    Chunk --> Chroma["Local Chroma build"]
    Chroma --> Qdrant["Qdrant Cloud v4"]
    Chunk --> Mongo["MongoDB parent_docs"]
```

Key design choices:

- Keep a **single Qdrant collection** with required metadata: `cohort`, `document_id`, `chunk_type`, `content_type`, and `source_pages`.
- Use `cohort` filters instead of separate collections per handbook.
- Keep repetitive forms/templates out of semantic retrieval when they are better served by structured lookup.
- Preserve source pages so students can verify important answers.

## Evaluation

The evaluation suite is intentionally split by system behavior. Deterministic lookup is not judged the same way as free-form RAG generation.

### Deterministic Structured Eval

Structured/tool questions are evaluated with exactness, item counts, cohort correctness, and citation metadata checks.

| Metric | Score |
|---|---:|
| Cases | 70 |
| Pass rate | 94.29% |
| Deterministic exactness | 97.83% |
| Citation metadata accuracy | 93.94% |
| Intent accuracy | 100.00% |
| Strategy accuracy | 100.00% |

### True-RAG Retrieval Eval

Retrieval is evaluated only on true RAG cases: regulation, procedure, office/faculty detail, and other long-form handbook questions.

| Metric | Score |
|---|---:|
| Cases | 80 |
| Hit@1 | 77.50% |
| Hit@3 | 90.00% |
| Hit@5 | 90.00% |
| MRR | 83.13% |
| nDCG@5 | 84.84% |

Breakdown:

| Content type | Hit@3 | MRR | nDCG@5 |
|---|---:|---:|---:|
| Faculty directory | 100.00% | 100.00% | 96.88% |
| Office directory | 90.48% | 90.48% | 90.48% |
| Procedures | 100.00% | 100.00% | 100.00% |
| Regulation sections | 86.67% | 74.44% | 77.97% |

### RAGAS-Style Gemini Judge

For generated true-RAG answers, the project uses a RAGAS-style rubric with Gemini 3.1 Flash Lite as Judge. The latest primary report is calculated only on generated true-RAG answers, excluding deterministic lookup cases from the headline metric.

| Metric | Score |
|---|---:|
| Answer relevancy | 90.23% |
| Context precision | 74.77% |
| Context recall | 75.91% |
| Citation correctness | 80.00% |
| Faithfulness | 72.05% |
| Answer correctness | 62.27% |

Interpretation:

- The system is ready for public beta because high-frequency structured questions and retrieval placement are stable.
- Lower faithfulness/correctness numbers are expected on harder long-form judge cases and are treated as improvement signals, not hidden.
- The UI keeps a visible warning that the assistant can make mistakes and that source citations should be checked for important decisions.

## Repository Structure

```text
student_handbook_rag/
|-- configs/                  # Runtime, retrieval, embedding, chunking configs
|-- data/
|   |-- raw/                  # Original handbook PDFs
|   |-- processed/            # Extracted structured data, chunks, metadata
|   `-- eval/                 # Golden eval cases for structured, retrieval, judge
|-- frontend/                 # React + Vite web app
|-- scripts/                  # Ingestion, migration, evaluation, debug utilities
|-- src/
|   |-- api/                  # FastAPI app, routes, request/response schemas
|   |-- chunking/             # Semantic, directory, form, table chunking
|   |-- common/               # Shared env/config helpers
|   |-- extraction/           # Structured data extraction from handbooks
|   |-- generation/           # Prompting, LLM clients, answer formatting, citations
|   |-- ingestion/            # PDF loading and preprocessing helpers
|   |-- preprocessing/        # Structure parsing and text cleanup
|   |-- retrieval/            # Router, lookup, BM25, vector retrieval, reranking
|   `-- services/             # Answer service orchestration
`-- tests/                    # Unit and integration tests
```

## Tech Stack

| Layer | Tools |
|---|---|
| Frontend | React, Vite, TypeScript, lucide-react |
| Backend | FastAPI, Pydantic, Uvicorn |
| Embeddings | BAAI/bge-m3 |
| Vector database | Qdrant Cloud, local Chroma for offline eval |
| Sparse retrieval | BM25 |
| Reranking | Local cross-encoder reranker |
| Parent docstore | MongoDB Atlas |
| LLM provider | Groq model fallback chain |
| Cache | Redis when available, local JSON fallback |
| Evaluation | deterministic eval, retrieval eval, RAGAS-style Gemini Judge |
| CI | GitHub Actions, ruff, compileall, unittest, frontend lint/build |

## Running Locally

### Backend

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.api.main:app --host 0.0.0.0 --port 7860
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Environment Variables

Create a `.env` file in the repository root. Do not commit real secrets.

```env
# LLM
GROQ_API_KEYS=your_groq_key_1,your_groq_key_2
GEMINI_API_KEY=your_gemini_key_for_eval

# Vector database
VECTORDB_PROVIDER=qdrant_cloud
QDRANT_URL=https://your-cluster-url
QDRANT_API_KEY=your_qdrant_key

# Runtime collection
# Config files currently point to student_handbook_semantic_v4

# Parent document store
MONGODB_URL=mongodb+srv://user:password@cluster.mongodb.net/?appName=chatbotHCMUE
MONGODB_PARENT_LOOKUP_ENABLED=true

# Cache
REDIS_URL=rediss://default:password@host:6379
STUDENT_RAG_DISABLE_REDIS=false

# CORS
STUDENT_RAG_CORS_ORIGINS=https://your-frontend-domain

# Optional tracing
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_key
LANGCHAIN_PROJECT=chatbotHCMUE
```

## Useful Commands

### Run Offline Evaluations

```bash
python scripts/evaluate_answers.py
python scripts/evaluate_retrieval.py
python scripts/evaluate_router_behavior.py
```

### Build Multi-Cohort Artifacts

```bash
python scripts/build_multi_cohort.py
```

### Push Local Chroma Collection to a New Qdrant Collection

```bash
python scripts/migrate_to_qdrant.py --target-collection student_handbook_semantic_v4
```

### Frontend Quality Checks

```bash
cd frontend
npm run lint
npm run build
```

## Deployment Notes

- Current runtime configs point to `student_handbook_semantic_v4`.
- MongoDB `parent_docs` should match the local `data/processed/chunks/docstore_items.json` IDs.
- Before public deployment, smoke test these flows:
  - switch K48-K49 and K50-K51;
  - list programs by school/faculty;
  - pass/fail thresholds and D/D+ behavior;
  - scholarship, re-study, grade appeal, dormitory, temporary leave;
  - office contact questions;
  - citation expand/collapse;
  - ambiguous and out-of-domain questions.

## Limitations

- This is a public beta assistant, not an official policy source.
- Some long regulation/procedure chunks can still lose nuance after context truncation.
- Judge metrics are intentionally reported honestly; faithfulness and correctness remain the main future improvement targets.
- Form retrieval is intentionally handled through structured form lookup and the Forms page instead of optimizing semantic RAG for form templates.

## Roadmap

- Add production feedback clustering for repeated low-confidence questions.
- Improve parent/child context selection for long regulations and procedures.
- Add source document viewer links when stable public URLs are available.
- Expand cohorts when new student handbooks are released.
- Build a lightweight internal quality dashboard after authentication/roles are introduced.

## License and Attribution

This project is built as a non-commercial student engineering project for learning, experimentation, and community support. Handbook content belongs to its respective source documents and should be verified through official HCMUE channels when used for important decisions.
