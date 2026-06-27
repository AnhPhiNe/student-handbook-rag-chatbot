# 🎓 HCMUE Student Handbook RAG Assistant

> **Disclaimer**: This is an independent, non-commercial personal project created for the HCMUE student community to easily access handbook information. It is **not** an official application provided or endorsed by Ho Chi Minh City University of Education.

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54" alt="Python 3.11">
  <img src="https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Vite-B73BFE?style=for-the-badge&logo=vite&logoColor=FFD62E" alt="Vite">
  <img src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React">
  <img src="https://img.shields.io/badge/Docker-2CA5E0?style=for-the-badge&logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/MongoDB-%234ea94b.svg?style=for-the-badge&logo=mongodb&logoColor=white" alt="MongoDB">
  <img src="https://img.shields.io/badge/Qdrant-E21727?style=for-the-badge&logo=Qdrant&logoColor=white" alt="Qdrant">
  <img src="https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis">
  <img src="https://img.shields.io/badge/LangSmith-000000?style=for-the-badge" alt="LangSmith">
</p>

## 🌟 Overview

The **HCMUE Student Handbook RAG** is a production-grade, multi-stage Retrieval-Augmented Generation (RAG) system built to answer complex, cohort-specific academic queries regarding the student handbook of Ho Chi Minh City University of Education.

By combining advanced NLP preprocessing, multi-stage hybrid search, intent routing, and fault-tolerant LLM orchestration, the system delivers grounded, citable, and factually accurate answers (verified via LLM-as-a-Judge) with sub-second latencies.

## 🛠️ Architectural Highlights & Engineering Decisions

### 1. 🔍 Advanced Hybrid Retrieval & Reranking
- **Dense & Lexical Fusion:** Combines semantic vectors (generated via `BAAI/bge-m3` on Qdrant Cloud) with sparse BM25 retrieval to capture both deep semantic context and exact academic terminology.
- **Cross-Encoder Reranking:** Integrates a local Cross-Encoder model to compute exact query-document relevance scores, filtering out retrieval noise and feeding only the highest-quality context to the generator.
- **Preprocessing Pipeline:** Implements custom Query Expansion, typo correction, and Entity Linking to translate student abbreviations (e.g., "CNTT", "ĐRL") to their formal equivalents, boosting retrieval recall.

### 2. ⚡ High-Availability & Fault-Tolerant LLM Orchestration
- **API Key Load Balancer:** Combines a custom round-robin balancer rotating across 5 distinct Groq API keys to bypass Rate Limits (TPD/TPM) of the free tier.
- **Graceful Quality Degradation:** Integrates a double-loop fallback model hierarchy. If the primary LLM (`llama-3.3-70b-versatile`) exhausts its tokens, the system dynamically downgrades to `gpt-oss-120b`, `qwen3.6-27b`, and finally `llama-3.1-8b-instant` to guarantee 100% uptime.
- **Two-Tier Caching Matrix:** Shared Redis L1 Cache (Upstash) reduces LLM execution costs. If Redis undergoes a network partition, the system automatically falls back to an ephemeral Local JSON L2 Cache.

### 3. ☁️ Scalable Parent-Child DB Architecture
- **Parent-Child Relation:** Utilizes **MongoDB Atlas (DocStore)** for storing full-length, uncut regulation documents ("Parents"), while **Qdrant Cloud (VectorDB)** stores dense, overlapping 200-token chunks ("Children"). This avoids vector dilution during retrieval while ensuring the LLM receives complete context without arbitrary truncation.
- **Dynamic Multi-Cohort Support:** Segregates and indexes regulations dynamically across different academic years (e.g., K48, K51), enabling the bot to contrast and compare policies across student generations.

---

## 🏛️ System Architecture

This diagram illustrates the high-availability infrastructure, showing how servers, databases, and external APIs are connected.

```mermaid
graph LR
    classDef ui fill:#005571,stroke:#fff,stroke-width:2px,color:#fff;
    classDef api fill:#4ea94b,stroke:#fff,stroke-width:2px,color:#fff;
    classDef cache fill:#DC382D,stroke:#fff,stroke-width:2px,color:#fff;
    classDef db fill:#E21727,stroke:#fff,stroke-width:2px,color:#fff;
    classDef mongo fill:#4ea94b,stroke:#fff,stroke-width:2px,color:#fff;
    classDef llm fill:#8E75B2,stroke:#fff,stroke-width:2px,color:#fff;
    classDef ops fill:#F4A261,stroke:#fff,stroke-width:2px,color:#fff;

    User([👨‍🎓 Student]) -->|HTTPS| Frontend[React / Vite UI]:::ui
    Frontend -->|REST API| Backend[FastAPI Backend]:::api
    
    %% Observability
    Backend -.->|Telemetry| LangSmith[LangSmith Tracing]:::ops
    
    %% Caching System
    Backend -->|Cache Hit| Cache[(Redis Cloud L1)]:::cache
    Cache -.->|Network Fallback| L2[(Local JSON L2)]:::cache
    
    %% Parent-Child Databases
    Backend ---->|Vector Search| Qdrant[(Qdrant Cloud Vectors)]:::db
    Backend ---->|Doc Fetch| Mongo[(MongoDB Atlas Docs)]:::mongo
    
    %% Load Balancer
    Backend -->|Round-Robin| LB{Groq Load Balancer}:::llm
    LB -->|Primary| Llama3[Llama-3.3-70b]:::llm
    LB -.->|Graceful Degradation| Backup[Qwen / GPT-OSS]:::llm
    
    %% Offline Pipeline
    Ingest[Offline Ingestion Pipeline]:::ops ----> Qdrant
    Ingest ----> Mongo
```

---

## 🧠 RAG Processing Pipeline (Data Flow)

This diagram illustrates the logical steps a question goes through, from the moment the user asks it until the final answer is generated.

```mermaid
graph TD
    classDef process fill:#2A9D8F,stroke:#fff,stroke-width:2px,color:#fff;
    classDef router fill:#F4A261,stroke:#fff,stroke-width:2px,color:#fff;
    
    Query([📝 User Query]) --> Guard[Input Guardrails & Security]:::process
    Guard --> Router{NLP Intent Router}:::router
    
    Router -->|Exact Match| Rule[Deterministic Form / Score Lookup]:::process
    Router -->|Semantic| Expand[Query Expansion & Entity Linking]:::process
    
    Expand --> Search[Vector Similarity Search]:::process
    Search --> Fetch[Fetch Full Parent Documents]:::process
    Fetch --> Rerank[Cross-Encoder Reranking]:::process
    
    Rule --> Gen[LLM Answer Generation]:::process
    Rerank --> Gen
    
    Gen --> Output([✅ Final Answer + Citations])
```

### 🧩 Step-by-Step Pipeline Breakdown

1. **Input Guardrails**: Intercepts the query to filter out prompt injections, jailbreaks, or out-of-domain requests.
2. **NLP Intent Router**: Classifies the query domain. Routes to the **Deterministic Lookup** (for exact form requirements, grade calculations) or the **Semantic Retrieval** engine.
3. **Query Expansion & Entity Linking**: Maps Vietnamese abbreviations and academic terminology to expand query semantics.
4. **Vector Search (Qdrant)**: Embeds the query using `bge-m3` and searches against Qdrant Cloud for the top semantic child chunks.
5. **Context Fetching (MongoDB)**: Maps child chunks to their parents in MongoDB Atlas and retrieves full documents.
6. **Cross-Encoder Reranking**: Re-scores the retrieved context against the user query using a local Cross-Encoder to optimize context window space.
7. **LLM Answer Generation**: Synthesizes a factual, well-cited Vietnamese answer, complete with document page numbers.

---

## 📂 Source Code Architecture

The codebase adheres strictly to **Clean Architecture** principles and is fully typed, linted, and formatted using `ruff` for strict PEP-8 compliance.

```text
student_handbook_rag/
├── configs/                 # Project configurations (e.g., yaml/json files for model parameters)
├── data/
│   ├── raw/                 # Original PDF handbooks (e.g., K48, K51)
│   └── processed/           # Extracted data (text extracts, entity registry, structured chunks)
├── deploy/                  # Configuration and scripts for deployment (e.g., to HuggingFace)
├── docs/                    # Project documentation (architecture, design, processes)
├── frontend/                # React/Vite UI source code
├── logs/                    # System runtime logs
├── models/                  # Local storage for downloaded AI models
├── scripts/                 # CLI utilities for data augmentation, evaluation, and preprocessing
├── tests/                   # Comprehensive Unit and Integration Test suite
└── src/
    ├── api/                 # FastAPI controllers, routes, and Pydantic schemas
    ├── chunking/            # Layout-aware semantic chunking logic
    ├── common/              # Shared utilities (Logging, Environment loading)
    ├── extraction/          # Structured data parsing (scoring tables, form templates, directories)
    ├── generation/          # LLM orchestration, Query Rewriting, and text generation
    ├── ingestion/           # Data loading pipelines (reading PDFs -> processing -> Vector DB)
    ├── preprocessing/       # Text cleaning and normalization
    ├── retrieval/           # Core RAG engine (Vector Search, Intent Router, Entity Linker)
    └── services/            # Core business logic binding Retrieval and Generation
```

- **`tests/`**: Over 56 automated Unit and Integration tests ensuring stability across the LLM and API logic.
- **`src/api/`**: Asynchronous FastAPI controllers, Server-Sent Events (SSE) for streaming, and Pydantic models for request/response validation.
- **`src/common/`**: Essential shared modules for the system such as robust logging (`logger.py`) and environment loading (`env_loader.py`).
- **`src/retrieval/`**: The core RAG retrieval engine featuring Intent Routing, Context Building, and Cross-Encoder Reranking logic.
- **`src/generation/`**: LLM orchestration layer managing Prompt Injection, Query Rewriting, and Double-Loop Fallback generation.
- **`src/chunking/` & `src/extraction/`**: Autonomous offline data pipelines responsible for layout-aware PDF parsing (via PyMuPDF) and extracting complex structured business rules (formulas, tables, directories).
- **`src/services/`**: High-level business logic binding the Retrieval and Generation modules.

---

## 📊 Automated Evaluation & Observability (LLM-as-a-Judge)

To ensure factual safety and prevent hallucinations, the system is continuously evaluated against an augmented dataset of **250+ golden test cases**, assessed strictly by an autonomous LLM-as-a-Judge (`gemini-3.1-flash-lite` at `temperature=0.0`).

### 1. Generation Quality (100 Complex Cases)
| Metric (RAGAS) | Score | Description |
|---|---|---|
| **Answer Relevance** | **92.2%** | Verifies that the answer directly solves the user's intent. |
| **Faithfulness** | **77.1%** | Grounding check ensuring the LLM does not hallucinate facts outside the provided context. |
| **Correctness** | **71.5%** | Compares factual outputs directly against human-annotated gold truths. |

### 2. Intent Routing & Guardrails (50 Cases)
| Metric | Score | Description |
|---|---|---|
| **Intent Router Accuracy** | **94.0%** | Measures classification accuracy between semantic and deterministic queries. |
| **Guardrail Pass Rate** | **86.0%** | Deflects prompt injections, jailbreaks, and out-of-domain requests. |
| **Citation Accuracy** | **100.0%** | Perfect matching of answers to source pages and regulations. |

### 3. Observability
- **LangSmith Tracing**: Every live user query records complete telemetry including: retrieval chunk relevance scores, context window size, latency breakdown, and token utilization/cost.

---

## ⚙️ CI/CD & Production Quality Gates

The project implements a complete **GitHub Actions CI/CD Pipeline** (`ci.yml`) to enforce code standards and prevent quality regression during updates:
- **Linting & Code Style:** Strict `ruff check .` checks.
- **Static Syntax Check:** Compiles all python files (`compileall`) to catch compilation bugs.
- **Automated Tests:** Automatically executes unit test discoveries.
- **Performance Quality Gates:** The pipeline executes `scripts.evaluate_router_behavior` on every push. **The build fails automatically** if the NLP Router's intent accuracy or strategy accuracy falls below **75%**.

---

## 💻 Setup & Installation

### 1. Prerequisites
- Python 3.11+
- Node.js & npm (for Frontend)

### 2. Environment Variables (`.env`)
Create a `.env` file in the root directory:
```env
GEMINI_API_KEY="your_gemini_key"
GROQ_API_KEYS="key1,key2,key3" # Comma separated for load balancing

# VectorDB (Qdrant Cloud)
VECTORDB_PROVIDER=qdrant_cloud
QDRANT_URL="https://your-qdrant-cluster.cloud.qdrant.io"
QDRANT_API_KEY="your_qdrant_key"

# Two-Tier Cache (Upstash Redis)
REDIS_URL="rediss://default:your_password@your_upstash_url:6379"

# Document Store (MongoDB Atlas)
MONGODB_URL="mongodb+srv://user:pass@cluster.mongodb.net/?appName=chatbotHCMUE"

# Observability (LangSmith)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT="https://api.smith.langchain.com"
LANGCHAIN_API_KEY="your_langsmith_key"
LANGCHAIN_PROJECT="chatbotHCMUE"
```

### 3. Run the Backend
```bash
pip install -r requirements.txt
uvicorn src.app:app --host 0.0.0.0 --port 8000
```

### 4. Run the React Frontend
```bash
cd frontend
npm install
npm run dev
```

### 5. Data Pipeline Execution (Optional)

To run the **Dynamic Multi-Cohort Pipeline** (parsing, chunking, and merging both K48 and K51 handbooks) and push vector embeddings to Qdrant Cloud:
```bash
python scripts/build_multi_cohort.py
```

---

## 🚧 System Constraints & Future Roadmap

### Current Constraints
- **Domain Specificity:** The retrieval engine and prompt matrices are strictly optimized for the HCMUE academic regulations and student handbook structure.
- **Language Constraint:** Designed specifically for Vietnamese queries (supporting both accented and accentless text). Other languages are not supported.

### Future Roadmap
- **GraphRAG Integration:** Transition from hierarchical document mapping to a Knowledge Graph structure (e.g., using Neo4j) to model complex rule dependencies, such as prerequisite courses, GPA conversions, and conditional academic warnings.
- **Agentic Chunking:** Implement LLM-guided agentic chunking to partition documents by semantic topic rather than rigid layout or token length boundaries.
- **Multi-Modal Parsing:** Incorporate Vision Language Models (VLMs) into the ingestion pipeline to parse handbook tables, structure trees, and process flowcharts directly as visual inputs.

---
*Built with ❤️ for the HCMUE Student Community.*
