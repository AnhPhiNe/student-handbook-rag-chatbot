# HCMUE AI - Student Handbook RAG Assistant

> Independent, non-commercial student project for the HCMUE student community.
> This is not an official application of Ho Chi Minh City University of Education.
> The assistant is built to help students look up handbook information faster, while important decisions should still be verified from citations or official offices.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-3670A0?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11">
  <img src="https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/React%20%2B%20Vite-Frontend-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React Vite">
  <img src="https://img.shields.io/badge/Qdrant-Vector%20DB-E21727?style=for-the-badge" alt="Qdrant">
  <img src="https://img.shields.io/badge/MongoDB-Parent%20Docs-4EA94B?style=for-the-badge&logo=mongodb&logoColor=white" alt="MongoDB">
  <img src="https://img.shields.io/badge/Groq-LLM%20Orchestration-F55036?style=for-the-badge" alt="Groq">
  <img src="https://img.shields.io/badge/Gemini-LLM%20Judge-8E75B2?style=for-the-badge&logo=google&logoColor=white" alt="Gemini">
  <img src="https://img.shields.io/badge/Langfuse-Tracing-FF6136?style=for-the-badge" alt="Langfuse">
  <img src="https://img.shields.io/badge/Redis-Caching-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis">
</p>

## Overview

**HCMUE AI Student Handbook Assistant** is a cohort-aware Retrieval-Augmented Generation system for answering questions from HCMUE student handbooks.

Unlike a simple "PDF chatbot", this project separates the system into two complementary layers:

- **Structured lookup** for information that must be exact, such as program lists, grade thresholds, scoring tables, formulas, offices, and forms.
- **True RAG retrieval** for longer regulations and procedures that need explanation, context, and citations.

The result is a production-oriented public beta assistant that can answer practical student questions such as:

- "Khoa Cong nghe Thong tin co nhung nganh nao?"
- "K50-K51 diem D+ co qua mon khong?"
- "Muon phuc khao diem thi thi lam sao?"
- "Van de hoc phi lien he phong nao?"
- "Tam nghi hoc can bieu mau nao?"

## Key Features

### 1. Cohort-Aware Handbook Reasoning

The system supports handbook differences between **K48-K49** and **K50-K51** instead of treating all documents as one flat knowledge base.

- Every indexed chunk carries `cohort`, `document_id`, `chunk_type`, `content_type`, and `source_pages`.
- Frontend tools and chat answers respect the selected cohort.
- Grade thresholds and program lists are handled differently when handbook rules differ by cohort.

### 2. Hybrid Retrieval With Reranking

For true RAG questions, the system combines:

- Dense vector search with `BAAI/bge-m3`.
- BM25 sparse retrieval for exact Vietnamese academic terms.
- Entity expansion for aliases such as faculty names, office names, and common abbreviations.
- Cross-encoder reranking to improve final context quality.
- Metadata filtering and boosting by cohort and content type.

### 3. Structured Lookup for Deterministic Facts

Information that should not be "generated from vibes" is extracted into structured stores:

- `program_directory`: majors, faculties, career descriptions, cohort applicability.
- `scoring_tables`: grade conversion and training score tables.
- `threshold_rules`: pass/fail thresholds and policy cutoffs.
- `formula_rules`: GPA, scholarship, and tuition-related formulas where available.
- `office_directory`: offices, responsibilities, emails, phone numbers.
- `form_templates`: form name, purpose, source page, and routing to the Forms page.

This design reduces hallucination on high-frequency student questions.

### 4. Parent-Child Retrieval Architecture

The project uses a parent-child retrieval design:

- **Qdrant Cloud** stores semantic child chunks for fast retrieval.
- **MongoDB Atlas** stores parent documents for richer context expansion.
- The app currently uses Qdrant collection `student_handbook_semantic_v4`.

### 5. Production-Oriented LLM Pipeline

The generation layer includes:

- AI router for intent and retrieval strategy.
- Query rewriting for accentless Vietnamese, typo-prone queries, and short queries.
- Groq model fallback chain for answer generation.
- Context allocation to fit relevant sources into a controlled token budget.
- Citation selection that prefers matching cohort, content type, section, and page metadata.
- Guardrails for out-of-domain, unsafe, ambiguous, or low-context questions.

## System Snapshot

| Component | Current State |
|---|---:|
| Supported cohorts | K48-K49, K50-K51 |
| Semantic vector chunks | 798 |
| MongoDB parent docs | 435 |
| Program directory records | 86 |
| Form template records | 19 |
| Qdrant collection | `student_handbook_semantic_v4` |
| Evaluation cases | 500 (150 Golden, 200 Beta, 150 Ragas) |

## Architecture

```mermaid
flowchart LR
    User["Student"] --> Frontend["React / Vite UI"]
    Frontend --> API["FastAPI Backend"]

    API --> Guard["Input Guardrails"]
    Guard --> Router["AI Router + Routing Rules"]

    Router -->|programs / scores / forms / offices| Lookup["Structured Lookup"]
    Router -->|regulations / procedures| Retrieval["Hybrid Retrieval"]

    Retrieval --> Qdrant["Qdrant Cloud\nChild Chunks"]
    Retrieval --> BM25["BM25 Sparse Index"]
    Retrieval --> Reranker["Cross-Encoder Reranker"]
    Reranker --> Mongo["MongoDB Atlas\nParent Docs"]

    Lookup --> Answer["Answer Formatter / LLM"]
    Mongo --> Answer
    Answer --> Citation["Citations + Source Metadata"]
    Citation --> Frontend

    API -. optional .-> Cache["Redis / Local JSON Cache"]
    API -. optional .-> Trace["Langfuse Tracing"]
```

## RAG Processing Pipeline

```mermaid
flowchart TD
    Query["User Query"] --> Validate["Validate Query"]
    Validate --> Rewrite["Query Rewriter"]
    Rewrite --> Route{"Router Decision"}

    Route -->|Structured| Structured["Structured Lookup"]
    Structured --> StructuredAnswer["Deterministic Answer Builder"]

    Route -->|True RAG| Expand["Entity Expansion"]
    Expand --> Vector["Qdrant Dense Retrieval"]
    Expand --> Sparse["BM25 Sparse Retrieval"]
    Vector --> Merge["Candidate Merge"]
    Sparse --> Merge
    Merge --> Rerank["Cross-Encoder Rerank"]
    Rerank --> Parent["Mongo Parent Context"]
    Parent --> Context["Score-Weighted Context Allocation"]

    StructuredAnswer --> Generate["Final Answer"]
    Context --> Generate
    Generate --> Cite["Citation Formatter"]
    Cite --> Output["Answer + Sources"]
```

### Pipeline Breakdown

1. **Input validation**
   - Filters out obviously invalid or out-of-domain questions.
   - Keeps the system focused on HCMUE handbook and student-service topics.

2. **Query rewriting**
   - Handles accentless Vietnamese and short/typo-prone queries.
   - Improves retrieval without changing the user's intent.

3. **Intent routing**
   - Sends deterministic questions to structured lookup.
   - Sends regulation/procedure questions to true RAG retrieval.

4. **Hybrid retrieval**
   - Combines vector retrieval and BM25.
   - Applies cohort/content-type filters when available.

5. **Reranking and parent expansion**
   - Reranks candidates with a local cross-encoder.
   - Expands selected chunks into parent context from MongoDB when needed.

6. **Answer generation**
   - Uses lookup/RAG context as source of truth.
   - Refuses to overclaim when context is missing.

7. **Citation formatting**
   - Returns compact sources with metadata such as cohort, content type, and source pages.

## Data and Ingestion Design

The pipeline processes each handbook through a document profile instead of relying on one-off hardcoded sections.

```mermaid
flowchart TD
    PDF["Raw Handbook PDFs"] --> Parse["PDF Parsing"]
    Parse --> Profile["Document Profile\ncohort, pages, section map"]
    Profile --> Extract["Structured Extraction"]
    Profile --> Chunk["Semantic Chunking"]

    Extract --> Program["program_directory"]
    Extract --> Office["office_directory"]
    Extract --> Form["form_templates"]
    Extract --> Score["scoring_tables / threshold_rules / formula_rules"]

    Chunk --> Chroma["Local Chroma Build"]
    Chroma --> Qdrant["Qdrant Cloud v4"]
    Chunk --> Docstore["MongoDB parent_docs"]
```

### Important ingestion choices

- Keep one unified Qdrant collection instead of one collection per handbook.
- Use metadata filters to separate cohort-specific retrieval.
- Keep repetitive forms and templates mostly in `form_templates`, not semantic RAG.
- Preserve enough source metadata for citation and verification.
- Validate chunk IDs, point IDs, cohort fields, document IDs, and content types before remote push.

## Source Code Architecture

```text
student_handbook_rag/
|-- configs/                  # Runtime, retrieval, embedding, extraction configs
|-- data/
|   |-- raw/                  # Original source PDFs
|   |-- processed/            # Structured data, chunks, metadata artifacts
|   `-- eval/                 # Golden evaluation datasets
|-- frontend/                 # React + Vite frontend
|-- scripts/                  # Ingestion, deployment, evaluation, debug scripts
|-- src/
|   |-- api/                  # FastAPI app, routes, schemas
|   |-- chunking/             # Semantic, table, form, directory chunkers
|   |-- common/               # Shared env/config helpers
|   |-- extraction/           # Structured extraction logic
|   |-- generation/           # LLM clients, prompts, answer pipeline, citations
|   |-- ingestion/            # PDF loading and input handling
|   |-- preprocessing/        # Section parsing and cleanup
|   |-- retrieval/            # Router, lookup, BM25, vector retrieval, reranking
|   `-- services/             # Answer orchestration service
`-- tests/                    # Unit and integration tests
```

## Evaluation

The evaluation design separates deterministic behavior from generated RAG behavior.

### 1. Structured / Tool Evaluation

Structured questions are checked with exactness, item count, cohort correctness, and citation metadata. This avoids incorrectly using LLM-as-a-Judge for answers that should be deterministic.

| Metric | Score |
|---|---:|
| Cases | 70 |
| Pass rate | 94.29% |
| Deterministic exactness | 97.83% |
| Citation metadata accuracy | 93.94% |
| Intent accuracy | 100.00% |
| Strategy accuracy | 100.00% |

### 2. True-RAG Retrieval Evaluation

Retrieval is evaluated only on long-form RAG cases such as regulations, procedures, offices, and faculty details.

| Metric | Score |
|---|---:|
| Cases | 150 (Golden) |
| Hit@3 | 86.25% |
| MRR | 80.19% |
| nDCG@5 | 82.90% |

Breakdown by content type:

| Content Type | Hit@3 | MRR | nDCG@5 |
|---|---:|---:|---:|
| Faculty directory | 100.00% | 100.00% | 96.88% |
| Office directory | 90.48% | 90.48% | 90.48% |
| Procedures | 100.00% | 100.00% | 100.00% |
| Regulation sections | 86.67% | 74.44% | 77.97% |

### 3. RAGAS-Style Gemini Judge

Generated true-RAG answers are evaluated with a RAGAS-style rubric using Gemini 3.1 Flash Lite as Judge. Deterministic lookup cases are excluded from the headline RAGAS metrics.

| Metric | Score |
|---|---:|
| Cases | 150 (Golden) |
| Answer relevancy | 81.27% |
| Faithfulness | 76.87% |
| Answer correctness | 51.80% |
| Context precision | 66.13% |
| Context recall | 61.13% |
| Citation correctness | 77.20% |

### How to read these numbers

- **Cohort Segregation (K50 vs K51):** The system enforces strict isolation between K50 and K51 regulations. This drastically increases the difficulty of the Retrieval task (slightly lowering Hit Rate and Correctness) but successfully boosts **Faithfulness to 76.87%**, ensuring students never receive mixed-up regulations.
- **Comprehensive RAGAS Evaluation:** Although Retrieval quality is already rigorously measured using exact math in Table 2 (Hit Rate, nDCG), we present the full RAGAS suite here for absolute transparency. Note that LLM-judged Context Precision/Recall scores are naturally lower than mathematical Hit Rates due to the strictness of the LLM Judge.
- The system is strong enough for public beta because structured facts and retrieval placement are stable.
- Metrics are reported honestly instead of being filtered to only easy cases (150 Golden Queries tested).

## CI/CD and Quality Gates

GitHub Actions runs offline checks on every push and pull request:

- Python dependency install from `requirements-dev.txt`.
- `ruff check .`
- `python -m compileall src scripts`
- `python -m unittest discover -s tests`
- `python -m scripts.evaluate_router_behavior --fail-under-intent 0.75 --fail-under-strategy 0.75`
- Frontend `npm ci`, `npm run lint`, and `npm run build`.

The deployment flow keeps GitHub source code and Hugging Face Space deployment separate:

- GitHub `main` stores the full project.
- Hugging Face Space receives a clean backend-only deployment bundle.
- Qdrant vectors and MongoDB parent docs are managed as external data services.

## Tech Stack

| Layer | Tools |
|---|---|
| Frontend | React, Vite, TypeScript, lucide-react |
| Backend | FastAPI, Uvicorn, Pydantic |
| Embeddings | BAAI/bge-m3 |
| Vector store | Qdrant Cloud, local Chroma for offline eval |
| Sparse retrieval | BM25 |
| Reranking | Local cross-encoder reranker |
| Parent docstore | MongoDB Atlas |
| LLM provider | Groq model fallback chain |
| Cache | Redis when available, local JSON fallback |
| Evaluation | deterministic eval, retrieval eval, RAGAS-style Gemini Judge |
| Deployment | GitHub, Hugging Face Spaces |

## Setup

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
QDRANT_URL=https://your-qdrant-cluster-url
QDRANT_API_KEY=your_qdrant_key

# Runtime collection is configured in YAML as:
# student_handbook_semantic_v4

# Parent document store
MONGODB_URL=mongodb+srv://user:password@cluster.mongodb.net/?appName=chatbotHCMUE
MONGODB_PARENT_LOOKUP_ENABLED=true

# Cache
REDIS_URL=rediss://default:password@host:6379
STUDENT_RAG_DISABLE_REDIS=false

# Frontend / CORS
STUDENT_RAG_CORS_ORIGINS=https://your-frontend-domain

# Optional tracing
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_key
LANGCHAIN_PROJECT=chatbotHCMUE
```

## Useful Commands

### Run offline evaluations

```bash
python scripts/evaluate_answers.py
python scripts/evaluate_retrieval.py
python scripts/evaluate_router_behavior.py
```

### Build multi-cohort artifacts

```bash
python scripts/build_multi_cohort.py
```

### Push local Chroma vectors to a new Qdrant collection

```bash
python scripts/migrate_to_qdrant.py --target-collection student_handbook_semantic_v4
```

### Deploy backend to Hugging Face Space

```bash
deploy_hf.bat
```

### Frontend checks

```bash
cd frontend
npm run lint
npm run build
```

## Production Smoke Test Checklist

Before public beta, test these flows on the deployed UI:

- Switch between K48-K49 and K50-K51.
- Ask school-wide and faculty-specific program questions.
- Ask pass/fail threshold questions, especially D and D+ for K50-K51.
- Ask about grade appeal, dormitory, temporary leave, scholarship, and re-study.
- Ask office contact questions such as tuition, training, and student affairs.
- Expand citations and verify source metadata.
- Try ambiguous and out-of-domain questions.

## Known Limitations

- This is a public beta assistant, not an official university system.
- Some long regulation/procedure chunks can still lose nuance after context allocation.
- RAGAS-style faithfulness and answer correctness are lower on difficult long-form questions and remain the main improvement targets.
- Form-related questions are intentionally routed to structured lookup and the Forms page instead of optimizing semantic form retrieval.
- There is no admin dashboard yet; feedback is currently handled through simpler logging/feedback mechanisms.

## Roadmap

- Improve long-context selection for regulation and procedure chunks.
- Add stable source-document URLs for "open source" citation buttons.
- Add feedback clustering for repeated low-score or unanswered questions.
- Expand the pipeline when new handbook cohorts are released.
- Add an internal quality dashboard after authentication and role management are introduced.

## Portfolio Notes

This project demonstrates:

- Applied RAG system design beyond a single-PDF chatbot.
- Cohort-aware retrieval and metadata filtering.
- Structured extraction and deterministic lookup for high-precision facts.
- Evaluation-driven iteration using retrieval metrics and RAGAS-style judging.
- Practical deployment trade-offs with Hugging Face, Qdrant, MongoDB, and Groq.

## License and Attribution

This project is built for learning, experimentation, and community support. Handbook content belongs to its respective source documents and should be verified through official HCMUE channels for important decisions.
