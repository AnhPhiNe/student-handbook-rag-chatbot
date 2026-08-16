# HCMUE AI - Student Handbook RAG Assistant

<p align="center">
  <strong>Cohort-aware RAG assistant for HCMUE student handbooks.</strong><br>
  Structured lookup, regulation retrieval, citation binding, and student-facing utilities in one React + FastAPI application.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-3670A0?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11">
  <img src="https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/React%20%2B%20Vite-Frontend-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React and Vite">
  <img src="https://img.shields.io/badge/Qdrant-Vector%20Search-E21727?style=for-the-badge" alt="Qdrant">
  <img src="https://img.shields.io/badge/MongoDB-Parent%20Docs-4EA94B?style=for-the-badge&logo=mongodb&logoColor=white" alt="MongoDB">
  <img src="https://img.shields.io/badge/Gemini-Answer%20Generation-8E75B2?style=for-the-badge&logo=google&logoColor=white" alt="Gemini">
  <br>
  <a href="https://www.hcmuebot.id.vn">
    <img src="https://img.shields.io/badge/Live_Chat-hcmuebot.id.vn-0A66C2?style=for-the-badge" alt="Live chat">
  </a>
  <a href="https://huggingface.co/spaces/AnhFeee/hcmue-handbook-rag-api">
    <img src="https://img.shields.io/badge/API-Hugging_Face_Spaces-FFD21E?style=for-the-badge&logo=huggingface" alt="Hugging Face API">
  </a>
</p>

<p align="center">
  <a href="https://www.hcmuebot.id.vn"><strong>Live demo</strong></a>
# HCMUE AI - Student Handbook RAG Assistant

<p align="center">
  <strong>Cohort-aware RAG assistant for HCMUE student handbooks.</strong><br>
  Structured lookup, regulation retrieval, citation binding, and student-facing utilities in one React + FastAPI application.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-3670A0?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11">
  <img src="https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/React%20%2B%20Vite-Frontend-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React and Vite">
  <img src="https://img.shields.io/badge/Qdrant-Vector%20Search-E21727?style=for-the-badge" alt="Qdrant">
  <img src="https://img.shields.io/badge/MongoDB-Parent%20Docs-4EA94B?style=for-the-badge&logo=mongodb&logoColor=white" alt="MongoDB">
  <img src="https://img.shields.io/badge/Gemini-Answer%20Generation-8E75B2?style=for-the-badge&logo=google&logoColor=white" alt="Gemini">
  <br>
  <a href="https://www.hcmuebot.id.vn">
    <img src="https://img.shields.io/badge/Live_Chat-hcmuebot.id.vn-0A66C2?style=for-the-badge" alt="Live chat">
  </a>
  <a href="https://huggingface.co/spaces/AnhFeee/hcmue-handbook-rag-api">
    <img src="https://img.shields.io/badge/API-Hugging_Face_Spaces-FFD21E?style=for-the-badge&logo=huggingface" alt="Hugging Face API">
  </a>
</p>

<p align="center">
  <a href="https://www.hcmuebot.id.vn"><strong>Live demo</strong></a>
  |
  <a href="https://huggingface.co/spaces/AnhFeee/hcmue-handbook-rag-api"><strong>Backend API</strong></a>
  |
  <a href="#evaluation"><strong>Evaluation</strong></a>
</p>

### Overview

![HCMUE AI chat interface](./frontend/public/chat_ui_screenshot.png)

HCMUE AI is a cohort-aware retrieval and generation system for the **K48-K49, K50, and K51** HCMUE student handbooks. It is designed around two distinct information shapes:

- **Structured Catalogs:** For grade conversion tables, study durations, scholarships, foreign-language equivalency, formulas, academic programs, faculties, offices, and student services.
- **Regulation RAG:** For policies, conditions, procedures, consequences, exceptions, and cross-referenced handbook articles.

The runtime maintains structured catalogs queryable as cohort-aware JSON rather than flattening every row into vector noise. For regulation articles, it performs semantic hybrid retrieval (Dense Vector + BM25 Lexical with Cohort Pre-filtering) coupled with a NetworkX Knowledge Graph for outbound article cross-referencing.

The frontend is built as an all-in-one student utility hub: students can query handbook policies, select their cohort, calculate GPA and tuition, explore faculty directories, and review study-method cards within a responsive, accessible interface.

> **Project status:** Production Release Candidate, evaluated on the frozen final holdout dataset (August 2026). This is an independent, non-commercial student project and is not an official HCMUE application. Important academic or financial decisions should always be verified against the cited handbook section or an official university office.

## Live Demo

- **Student-facing chat:** [https://www.hcmuebot.id.vn](https://www.hcmuebot.id.vn)
- **Backend Space:** [https://huggingface.co/spaces/AnhFeee/hcmue-handbook-rag-api](https://huggingface.co/spaces/AnhFeee/hcmue-handbook-rag-api)
- **Source repository:** [https://github.com/AnhPhiNe/student-handbook-rag-chatbot](https://github.com/AnhPhiNe/student-handbook-rag-chatbot)

Example queries:

- `K51 diem D+ co qua mon khong?`
- `K50 hoc toi da bao nhieu nam?`
- `PDT o dau va email la gi?`
- `Khoa CNTT K51 co nhung nganh nao?`
- `Dieu kien tam ngung hoc la gi?`
- `Neu vuot thoi gian hoc toi da thi xu ly the nao?`

---

## Data Processing & Ingestion Pipeline

To handle the structural heterogeneity of student handbooks (spanning tables, contact catalogs, academic formulas, and complex nested regulations), the data ingestion pipeline follows a strict **Dual-Path Architecture**:

```mermaid
flowchart TD
    RawPDF["1. Raw Handbook PDFs (K48-K49, K50, K51)"] --> PDFLoader["src/ingestion/pdf_loader.py<br/>Extract layout, text & page coordinates"]
    PDFLoader --> StructParser["src/preprocessing/structure_parser.py<br/>Hierarchical Parsing (Chương -> Điều -> Khoản -> Điểm)"]
    
    StructParser --> PathA["📁 Path A: Structured Catalog Extraction<br/>(src/extraction/)"]
    StructParser --> PathB["📄 Path B: Child-Parent Chunking<br/>(src/chunking/)"]
    StructParser --> PathC["🕸️ Path C: Cross-Reference Graph<br/>(src/ingestion/graph_extractor.py)"]
    
    PathA --> Tables["9 Deterministic JSON Catalog Groups (30+ JSON files)<br/>• scoring_tables.json & threshold_rules.json<br/>• foreign_language_equivalency_table.json<br/>• formula_rules.json<br/>• faculty_directory & office_directory.json<br/>• program_directory & student_service_directory.json"]
    
    PathB --> ParentDocs["Parent Documents (Full Article Markdown)<br/>462 Parent Sections"]
    PathB --> ChildChunks["Child Semantic Chunks (300-500 tokens)<br/>3,228 Child Chunks with Parent IDs"]
    
    PathC --> GraphEdges["Directed Knowledge Graph Edges<br/>95 Edges across 120 Nodes (LIEN_QUAN_TOI)"]
    
    ParentDocs --> Mongo[("MongoDB Atlas<br/>parent_docs_v9_candidate")]
    ChildChunks --> Embed["Embedding Model: BAAI/bge-m3 (1024-dim)"] --> Qdrant[("Qdrant Cloud<br/>student_handbook_semantic_v29_candidate")]
    Tables --> RuntimeJSON["Runtime JSON Storage (data/processed/tables/ & directories/)"]
    GraphEdges --> GraphJSON["NetworkX In-Memory MultiDiGraph"]
```

### 1. Ingestion & Hierarchical Structure Parsing (`src/ingestion/`, `src/preprocessing/`)
- **PDF Extraction & Layout Analysis:** `pdf_loader.py` parses raw PDF pages and retains source page coordinates to guarantee exact citation binding.
- **Hierarchical Document Parsing:** `structure_parser.py` decomposes raw handbook text into a strict hierarchy: `Chương (Chapter) -> Điều (Article) -> Khoản (Clause) -> Điểm (Point)` and tags each document with its applicable cohort (`K48-K49`, `K50`, `K51`).

### 2. Dual-Path Processing Strategy

#### A. Structured Catalog Extraction (`src/extraction/`)
Extracts tables, rules, and directories across **9 structured lookup groups (comprising 34 cohort-tagged JSON files)** that require 100% exact numerical precision rather than probabilistic vector search:
1. **Scoring & Evaluation Tables (`scoring_tables.json`):** Grade conversion (10-point scale $\leftrightarrow$ 4-point scale $\leftrightarrow$ letter grades A/B/C/D/F), academic standing, and graduation honors.
2. **Threshold & Limit Rules (`threshold_rules.json`):** Academic scholarship classification (Xuất sắc $\ge 3.60$, Giỏi $\ge 3.20$, Khá $\ge 2.50$), conduct score thresholds ($\ge 90, \ge 80, \ge 65$), standard/maximum allowable study durations, and academic probation limits.
3. **Foreign Language Equivalency (`foreign_language_equivalency_table.json`):** Standardized graduation exit benchmarks (IELTS, TOEFL iBT/ITP, TOEIC, JLPT, HSK, TOPIK, VSTEP).
4. **Academic Formulas (`formula_rules.json`):** Exact mathematical definitions for GPA, CPA, tuition exemptions, and scholarship weighting.
5. **Faculty Directory (`faculty_directory.json`, `student_faculty_profiles.json`):** Faculty names, dean offices, physical locations, hotlines, and contact emails across cohorts.
6. **Administrative Office Directory (`office_directory.json`, `student_office_profiles.json`):** Department directories (Phòng Đào tạo, Phòng CTCT&HSSV, Trạm Y tế, Ký túc xá, Thư viện...).
7. **Academic Programs (`program_directory.json`, `faculty_program_directory.json`):** Full list of undergraduate majors, program codes, degree types, and managing departments.
8. **Student Services Directory (`student_service_directory.json`):** Service-to-office routing matrix (student status certificates, tuition loan support, pedagogical fee waivers, bus passes...).
9. **Registry & Reference Index (`structured_tables_registry.json`, `reference_directory.json`):** Global lookup routing registry and provenance cross-referencing.
- **Storage:** Persisted as versioned, validated JSON in `data/processed/tables/` and `data/processed/directories/`.

#### B. Child-Parent Hierarchical Chunking (`src/chunking/`)
Eliminates the trade-off between retrieval precision and generation context:
- **Parent Documents (Docstore):** Complete Article text containing full context, prerequisites, and consequences (462 parent sections stored in **MongoDB Atlas**).
- **Child Chunks (Vector Index):** Granular clause-level semantic windows (~300–500 tokens) with prepended section headers for high-fidelity vector matching (3,228 chunks indexed in **Qdrant Cloud**).
- **Table Regulation Chunks:** Specialized table extractors identify inline regulation tables and link them back to their parent article without exposing internal database IDs.

#### C. Cross-Reference Knowledge Graph Extraction (`src/ingestion/graph_extractor.py`)
- Regex-based and semantic extraction scans regulation text for explicit inter-article citations (e.g., *"theo quy định tại Điều 14"*, *"quy định tại Khoản 2 Điều 18"*).
- Constructs directed multi-graphs where nodes represent Parent Section IDs and edges denote `LIEN_QUAN_TOI` (Related To) relationships (95 edges across 120 nodes with **0.00% cross-cohort leakage**).

### 3. Pre-Flight Storage Validation & Deployment Sync
Before publishing artifacts to MongoDB Atlas and Qdrant Cloud, automated verification scripts validate:
- **Parent-Child Consistency:** Zero orphan child chunks; every chunk references a valid MongoDB parent ID.
- **Cohort Boundary Isolation:** Zero cross-cohort edge links in the knowledge graph.
- **Catalog Non-Emptiness:** Ensures required lookup tables contain non-empty entries for every supported cohort.

---

## Current Architecture

The production release is split into three deterministic execution paths:

| Path | Used for | Why it exists |
|---|---|---|
| **Structured resolver** | Tables, offices, faculties, programs, services, formulas | Exact cohort-aware answers without vector-search ambiguity |
| **Regulation RAG** | Conditions, procedures, exceptions, consequences | Full handbook articles with citations and graph-supported context |
| **Mixed answering** | Questions that require both structured facts and regulation rules | Prevents LLM hallucinations while explaining complex policies |

```mermaid
flowchart TD
    User["Student query + selected cohort"] --> API["FastAPI Guardrails & Rate Limit"]
    API --> Router["Groq Qwen 3.6 27B AI Router"]
    Router --> Query["Validated Query Handling & Slang Normalizer"]

    Query -->|structured| Resolver["Cohort-aware JSON Resolver"]
    Query -->|regulation or mixed| Retrieval["Hybrid Regulation Retrieval"]
    Query -->|ambiguous| Clarify["Clarification Response"]
    Query -->|out_of_domain| Reject["Out-of-domain Safe Refusal"]

    Resolver --> Structured["Validated Structured Table Context"]

    Retrieval --> Dense["BGE-M3 Dense Search (Qdrant Cloud)"]
    Retrieval --> Sparse["BM25 Lexical Search (Cohort Pre-filtered)"]
    Dense --> Fusion["Reciprocal Rank Fusion (RRF)"]
    Sparse --> Fusion
    Fusion --> Primary["Top 5 PRIMARY Parent Sections"]
    Primary --> Graph["NetworkX Knowledge Graph Expansion (Depth 2)"]
    Graph --> Related["Up to 5 Deduplicated RELATED References"]
    Primary --> Mongo["MongoDB Atlas Full Parent Lookup"]

    Structured --> Prompt["Grounded Generation Prompt"]
    Mongo --> Prompt
    Prompt --> Gemini["Gemini 3.1 Flash-Lite Client Pool"]
    Gemini --> Output["Answer + Citations + Related References (UI)"]

    API -. SHA-256 context fingerprint .-> Cache["Redis + Local JSON Two-Tier Cache"]
```

### 1. Query Handling and AI Routing

The system uses `qwen/qwen3.6-27b` via Groq as a fast, typed AI Router. It classifies intent into:

- `structured` (with explicit `lookup_type`, `intent`, and `slots`)
- `rag` with `regulation` or `mixed` execution
- `clarify` (for ambiguous queries)
- `out_of_domain` (safe refusal)

**Guardrails:** The AI Router extracts structured intent and slot spans without free-form query mutations. A strict query guardrail (`validate_normalized_query`) enforces that cohorts, numeric figures, and core semantics are never altered by the router.

### 2. Structured Catalogs

The Router dispatches to one of nine structured lookup categories:

| Group | Typical Data & Purpose |
|---|---|
| **Foreign language** | IELTS, TOEFL, JLPT, HSK, TOPIK graduation equivalency |
| **Study duration** | Standard and maximum allowable study years by training mode |
| **Scholarship** | Academic scholarship classification (Xuất sắc, Giỏi, Khá) |
| **Scoring** | Grade conversions (10-point, 4-point, letter grade), academic ranking, conduct scoring |
| **Student service** | Department responsible for student procedures and certifications |
| **Office** | Office email, hotline, website, and physical address |
| **Faculty** | Faculty directory, dean offices, and contact channels |
| **Program** | Program offerings, faculty ownership, and cohort-specific lists |
| **Formula** | GPA, CPA, or tuition/scholarship formula definitions |

The resolver pulls cohort-tagged JSON, validates required slots and provenance, and embeds the structured table directly into `[STRUCTURED CONTEXT]` for Gemini to produce pedagogical, natural-language answers.

### 3. Regulation Retrieval Pipeline

The production retrieval pipeline follows a clean, high-performance hybrid flow (without expensive reranker bottlenecks):

```text
Validated Query
-> BGE-M3 dense vector search (top 24 child chunks in Qdrant Cloud)
-> BM25 sparse lexical search (top 24 child chunks, cohort pre-filtered)
-> Reciprocal Rank Fusion (RRF)
-> Group candidates by Parent Section ID
-> Select Top 5 PRIMARY Parent Sections
-> In-memory Multi-Source BFS on Knowledge Graph (depth 2, max 5 related parents)
-> Fetch complete parent markdown documents from MongoDB Atlas
-> Inject PRIMARY sources into Gemini prompt; pass RELATED references to UI metadata
```

Qdrant stores semantic chunks with cohort tags. MongoDB Atlas stores complete parent section documents to guarantee context continuity.

### 4. Context, Citations, and UI Separation

- **Primary Sources:** Gemini prompt receives up to 5 full `PRIMARY SOURCES` (budgeted at `160,000` chars total, max `50,000` chars per document).
- **Related References:** Knowledge Graph discoveries are passed as UI reference links, preventing context dilution and hallucination in the LLM context.
- **Citation Integrity:** Citations are bound to the parent section ID, cohort, document title, and exact handbook source pages.

### 5. Reliability & Fault-Tolerant Infrastructure

- **Multi-Key Load Balancing:** Quota-aware LRU key pools for both Gemini (`GeminiKeyPool`) and Groq (`GroqRouterKeyPool`) distribute traffic evenly across multiple keys.
- **Instant 0ms Failover:** Upon receiving HTTP `429 Rate Limit`, the client immediately cools down the offending key and acquires the next healthy key with zero blocking sleep.
- **Sliding-Window Protection:** Real-time sliding window (60s) calculates exact cooldown fractions when all keys reach RPM capacity.
- **Two-Tier Caching:** Redis Cloud distributed cache with automatic local JSON disk fallback (`data/cache/answer_response_cache.json`) using SHA-256 context-aware fingerprinting.
- **API Guardrails:** Client UUID rate limiting, public-IP abuse protection, burst capacity semaphores, and LangSmith realtime tracing.

---

## Data Snapshot

The release candidate knowledge base is built from the official handbooks of three cohorts:

| Storage Layer / Artifact | Count / State |
|---|---:|
| **MongoDB Parent Sections** | **462 parent documents** |
| **Qdrant Regulation Chunks** | **3,228 child chunks** |
| **Active Knowledge Graph Nodes** | **120 parent section nodes** (25.97% coverage) |
| **Directed Knowledge Graph Edges** | **95 directed `LIEN_QUAN_TOI` edges** |
| **Cross-Cohort Edge Leak Rate** | **0.00%** (zero cross-cohort contamination) |
| **Qdrant Collection** | `student_handbook_semantic_v29_candidate` |
| **MongoDB Collection** | `parent_docs_v9_candidate` |

### Parent Section Distribution

| Cohort | Parent Sections | Graph Edges |
|---|---:|---:|
| **K48-K49** | 123 | 30 |
| **K50** | 166 | 34 |
| **K51** | 173 | 31 |
| **Total** | **462** | **95** |

Structured catalogs are maintained separately in `data/processed/tables/` and `data/processed/directories/`. Release packaging performs pre-flight integrity verification on all required JSON catalogs.

---

## Evaluation

The release candidate was evaluated across 6 comprehensive suites using the frozen **final holdout dataset**. All reports, provenances, and dataset hashes are generated and verified.

| Evaluation Suite | Sample Size | Scope & Purpose | Status |
|---|---:|---|:---:|
| **1. Dataset Validation** | 462 docs / 4 datasets | Integrity, schema contracts, and docstore coverage | 🟢 PASS (100%) |
| **2. Structured Lookups** | 120 cases | Catalog routing, table lookup exactness, and fallbacks | 🟢 PASS (100.00%) |
| **3. Regulation Retrieval** | 180 cases | End-to-end Router + Hybrid Qdrant/BM25 + Mongo binding | 🟢 PASS (Hit@5 91.11% \| MRR 0.786) |
| **4. Graph Supplement** | 95 edges | Knowledge graph expansion, depth-2 recall, and cohort isolation | 🟢 PASS (100%) |
| **5. Answer Generation & Judge** | 100 cases | RAGAS automated Judge (`gpt-oss-120b`) across 4 case types | 🟢 PUBLISHED |
| **6. Human Audit (5-Level Rubric)** | 25 cases | 15 stratified-random headline cases + 10 failure diagnostics | 🟢 AUDITED (0% Critical) |
| **7. Production & Fault Injection** | 60 reqs / 13 faults | Live FastAPI throughput, streaming TTFT, cache, and chaos tests | 🟢 PASS (100%) |

---

### 1. Structured Routing and Resolution (`n = 120`)

| Metric | Measured Result | 95% Confidence Interval |
|---|---:|:---:|
| **Cases Passed** | **120 / 120 (100.00%)** | [96.90% – 100.00%] |
| **Lookup Exactness** | **100.00%** | — |
| **Precision** | **100.00%** | — |
| **Recall** | **100.00%** | — |
| **F1-Score** | **100.00%** | — |
| **Intent Accuracy** | **100.00%** | — |
| **Strategy Accuracy** | **100.00%** | — |
| **Structured Value Exactness** | **100.00%** | — |
| **Citation Metadata Accuracy** | **100.00%** | — |
| **Cross-Cohort Leaks** | **0 (0.00%)** | — |
| **Latency (P50 / P95)** | **1.15s / 8.52s** | — |

---

### 2. End-to-End Regulation Retrieval (`n = 180`)

Evaluates the full user retrieval path: Slang Normalizer $\rightarrow$ AI Router $\rightarrow$ Qdrant Dense + BM25 Sparse $\rightarrow$ RRF Fusion $\rightarrow$ Mongo Parent Section Binding.

| Metric | Measured Result | 95% Confidence Interval |
|---|---:|:---:|
| **Hit@1** | **70.56%** | [63.89% – 76.67%] |
| **Hit@3** | **86.67%** | [81.67% – 91.67%] |
| **Hit@5** | **91.11%** | [86.67% – 95.00%] |
| **MRR (Mean Reciprocal Rank)** | **78.56%** | [73.43% – 83.40%] |
| **nDCG@5** | **80.06%** | [75.51% – 84.26%] |
| **Parent Section Match** | **91.11%** | — |
| **Citation Binding Rate** | **91.11%** | — |
| **Cohort Match Rate** | **100.00%** | — |
| **Cohort Leak Rate** | **0.00%** | — |
| **Retrieval Latency (P50 / P95)** | **1.43s / 2.27s** | — |

---

### 3. Knowledge Graph Supplement (`95 edges`, `120 nodes`)

| Metric | Measured Result | Evaluation Objective |
|---|---:|---|
| **Source Section Coverage** | **100.00%** | All source articles mapped |
| **Target Section Coverage** | **100.00%** | All target articles mapped |
| **Direct Expansion Recall** | **100.00%** | 1-hop neighbor recovery |
| **RELATED Selection Recall@5** | **100.00%** | Discovery within UI budget |
| **Related Cohort Leak Rate** | **0.00%** | Strict cohort boundary isolation |
| **Selected Related Parents (Mean)** | **1.64 parents** | Bounded context enrichment |
| **Graph Traversal Latency (P95)** | **0.02ms** | In-memory NetworkX speed |

---

### 4. Generated-Answer Automated Evaluation (`n = 100`)

Evaluated using `openai/gpt-oss-120b` as a strict RAGAS-style Judge over 60 regulation RAG, 20 structured lookup, 10 mixed, and 10 unanswerable queries:

| Metric | Measured Result | 95% Confidence Interval |
|---|---:|:---:|
| **Answer Relevancy** | **86.38%** | [81.62% – 90.59%] |
| **Citation Correctness** | **79.77%** | [73.45% – 85.70%] |
| **Context Recall** | **78.78%** | [72.90% – 84.78%] |
| **Answer Correctness** | **74.84%** | [68.14% – 81.19%] |
| **Faithfulness** | **75.22%** | [68.64% – 81.26%] |
| **Context Precision** | **66.33%** | [61.84% – 70.82%] |
| **Numeric Accuracy** | **93.00%** | — |
| **Abstention Correctness** | **89.00%** | — |
| **Answer Success Rate** | **99.00%** | — |

---

### 5. Standardized Human Audit (`n = 25`)

Manual audit performed by human evaluators against official handbook source pages using a granular 5-level rubric ($1.00, 0.75, 0.50, 0.25, 0.00$).

#### A. Headline Calibration Sample (`n = 15` Stratified Random)
Representative sample across cohorts and query types:

| Metric | Human Audit Result | Evaluation Note |
|---|---:|---|
| **Human Score** | **85.00%** | High production utility |
| **Content Correctness** | **85.00%** | Fully aligned with HCMUE regulations |
| **Faithfulness (Groundedness)** | **93.33%** | 14 / 15 cases strictly source-grounded |
| **Citation Correctness** | **70.00%** | Core articles 100% correct; penalizes over-citations |
| **Actual Unsupported Claims** | **2 / 15** | Low rate of harmless natural summaries |
| **Critical False Passes** | **0 / 15 (0.00%)** | 🛡️ **Zero academic safety violations** |

#### B. Targeted Risk Diagnostic (`n = 10` Lowest Judge Scores)
Diagnostic analysis on the 10 lowest-scoring automated cases:

* **Judge False Positives:** **5 / 10 (50.0%)** (The automated LLM Judge penalized valid answers that adhered to handbook policies).
* **Retrieval Misses:** **2 / 10** (`v9_ans_058` accentless query, `v9_ans_025` K51 directory).
* **Generator Omissions:** **1 / 10** (`v9_ans_080`).
* **Harmless Hallucinations:** **2 / 10** (`v9_ans_100`, `v9_ans_089`).
* **Critical False Passes:** **0 / 10 (0.00%)** (Zero academic or financial hazards).

#### C. Calibration & Agreement Metrics
* **Inter-Annotator Consistency MAE (`human_repeat_mae`):** **0.00** ($100\%$ repeat consistency across 5 validation cases).
* **Human-Judge MAE:** **0.29** (Automated Judge scores ~29% more conservatively than human evaluation).
* **Overall Critical False Passes:** **0 / 25 (0.00% across all audited cases)**.

---

### 6. Production Performance & Hardening Suite (`n = 60`)

Live benchmarking against the FastAPI server evaluating latency, streaming TTFT, caching, and burst concurrency:

| Metric | Measured Result | Benchmark Status |
|---|---:|:---:|
| **Request Completion Rate** | **60 / 60 (100.00%)** | 🟢 Complete |
| **Transport Success Rate** | **100.00%** | 🟢 No Network Drops |
| **Payload Success Rate** | **100.00%** | 🟢 Valid JSON Schemas |
| **Response Status Accuracy** | **98.33%** | 🟢 Protocol Compliant |
| **Error Rate / HTTP 429 Rate** | **0.00% / 0.00%** | 🛡️ Zero Throttling |
| **Timeout Rate** | **0.00%** | 🛡️ Zero Hangs |
| **Overall Latency (P50 / P95)** | **3.07s / 6.19s** | ⚡ Fast Turnaround |
| **Streaming TTFT (P50 / P95)** | **2.20s / 3.19s** | ⚡ 100% Streaming Coverage |
| **Cold Regulation RAG Latency (P50)** | **2.89s** | ⚡ End-to-End Retrieval + LLM |
| **Deterministic Scenario Latency (P50)**| **2.63s** | ⚡ Fast Table Extraction |
| **Warm-Cache Latency (P50)** | **0.73s (730ms)** | ⚡ In-Memory Response |
| **Warm-Cache Hit Rate** | **90.00%** | ⚡ Sub-second Repeat Queries |
| **Burst Concurrency ($c=3, 5$)** | **10 / 10 (100.00%)** | 🏋️ High Concurrency Safe |

---

### 7. Fault Injection & Resilience Suite (`n = 13`)

13 chaos engineering tests simulating single points of failure passed with **100.00% success (`13 / 13 passed`, pytest exit code 0)**:

1. `test_generate_retries_next_key_after_rate_limit`: Instant key rotation on HTTP 429.
2. `test_generate_stream_retries_next_key_after_rate_limit`: Streaming key rotation without stream collapse.
3. `test_streaming_call_times_out_without_chunks`: Socket timeout protection on stalled chunk streams.
4. `test_disconnect_is_classified_as_transient`: Transient transport disconnect auto-retry.
5. `test_concurrent_generate_uses_request_local_clients`: Request-local Gemini client isolation.
6. `test_key_pool_load_balances_between_keys`: Multi-key LRU load balancing.
7. `test_key_pool_skips_key_in_cooldown`: Cooldown key bypass.
8. `test_key_pool_blocks_daily_exhausted_keys`: Daily token exhaustion safety gate.
9. `test_gemini_pool_reports_all_keys_temporarily_limited`: Controlled alert when all keys are limited.
10. `test_gemini_empty_response_is_not_success`: Empty response safety validation.
11. `test_retrieval_exception_stays_in_denominator`: Retrieval error metric integrity.
12. `test_mongo_parent_miss_cannot_count_as_retrieval_hit`: Docstore miss protection.
13. `test_chat_returns_busy_when_capacity_is_full`: HTTP 503 capacity backpressure guardrail.

---

## Technology Stack

| Layer | Technology & Framework |
|---|---|
| **Frontend** | React 18, Vite, TypeScript, TailwindCSS / CSS Modules, Lucide React |
| **Backend API** | FastAPI, Uvicorn, Pydantic v2 |
| **AI Router** | Groq `qwen/qwen3.6-27b` with zero-mutation guardrails |
| **Answer Generation** | Google `gemini-3.1-flash-lite` with multi-key LRU load balancing |
| **Evaluation Judge** | Groq `openai/gpt-oss-120b` (RAGAS framework) |
| **Dense Embeddings** | `BAAI/bge-m3` (1024 dimensions) |
| **Vector Database** | Qdrant Cloud |
| **Docstore & Parent Store** | MongoDB Atlas (462 parent sections) |
| **Knowledge Graph** | NetworkX In-Memory Directed MultiDiGraph (95 edges, depth 2) |
| **Two-Tier Cache** | Redis Cloud + Local JSON Fallback (SHA-256 context fingerprint) |
| **Observability** | LangSmith Realtime Tracing & LLM Monitoring |
| **Deployment** | Vercel (Frontend), Hugging Face Spaces (Backend API) |

---

## Repository Layout

```text
student_handbook_rag/
|-- configs/                  # Runtime, router, retrieval, tables, and ingestion YAMLs
|-- data/
|   |-- raw/                  # Local source handbook PDFs (not committed)
|   |-- processed/            # Processed JSON catalogs, graph edges, and docstore items
|   `-- eval/                 # Frozen holdout datasets and verified release reports
|-- frontend/                 # React + Vite application
|-- scripts/                  # Evaluation runner (evaluate_system.py), indexing, and deployment
|-- src/
|   |-- api/                  # FastAPI routes, schemas, rate limiting, and chat controls
|   |-- chunking/             # Child-parent regulation chunk builder
|   |-- common/               # Key pool managers, env loader, error classification
|   |-- extraction/           # Table, directory, and rule extraction
|   |-- generation/           # Gemini client pool, prompt builder, two-tier cache, answer pipeline
|   |-- ingestion/            # Graph extractor and storage synchronization
|   `-- retrieval/            # AI router, structured dispatchers, hybrid search (Qdrant + BM25)
`-- tests/                    # Unit, integration, and fault injection tests (200+ test cases)
```

---

## Quick Start & Local Setup

### 1. Backend Setup

```bash
# Clone repository
git clone https://github.com/AnhPhiNe/student-handbook-rag-chatbot.git
cd student-handbook-rag-chatbot

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows PowerShell
# source .venv/bin/activate    # Linux / macOS

# Install dependencies
pip install -r requirements.txt

# Start FastAPI server
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

---

## Environment Variables Configuration

Create a `.env` file in the root directory:

```env
# Gemini API Key Pool (comma-separated for auto load-balancing & failover)
GEMINI_API_KEYS=gemini_key_1,gemini_key_2,gemini_key_3

# Groq Router API Key Pool
GROQ_API_KEYS=gsk_key_1,gsk_key_2

# Vector Store (Qdrant Cloud)
VECTORDB_PROVIDER=qdrant
QDRANT_URL=https://your-cluster.qdrant.io
QDRANT_API_KEY=your_qdrant_key
QDRANT_COLLECTION_NAME=student_handbook_semantic_v29_candidate

# Document Store (MongoDB Atlas)
MONGODB_URL=mongodb+srv://user:password@cluster.mongodb.net/
MONGODB_PARENT_COLLECTION=parent_docs_v9_candidate

# Two-Tier Response Caching (Optional Redis)
REDIS_URL=rediss://default:password@your-redis-host:6379

# Observability (LangSmith Realtime Tracing)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_...
LANGCHAIN_PROJECT=hcmue-student-handbook-rag

# API Protection Guardrails
STUDENT_RAG_RATE_LIMIT_PER_MINUTE=20
STUDENT_RAG_IP_RATE_LIMIT_PER_MINUTE=120
STUDENT_RAG_MAX_CONCURRENT_CHAT=5
```

---

## Executing the Evaluation Suite

Run the unified evaluation suite across all components:

```bash
# 1. Validate frozen datasets & docstore
python scripts/evaluate_system.py --suite validate --profile full

# 2. Structured catalogs & tables evaluation (120 cases)
python scripts/evaluate_system.py --suite deterministic --profile full

# 3. End-to-end retrieval evaluation (180 cases)
python scripts/evaluate_system.py --suite retrieval --profile full

# 4. Knowledge graph supplement evaluation (95 edges)
python scripts/evaluate_system.py --suite graph --profile full

# 5. Answer generation & LLM Judge evaluation (100 cases)
python scripts/evaluate_system.py --suite generate --profile full
python scripts/evaluate_system.py --suite judge --profile full

# 6. Fault injection & chaos resilience suite (13 tests)
python scripts/evaluate_system.py --suite faults --profile full

# 7. Production performance & concurrency benchmarking (60 requests)
# Ensure FastAPI server is running on http://127.0.0.1:8000 first
python scripts/evaluate_system.py --suite production --profile full --base-url http://127.0.0.1:8000
```

---

## License and Disclaimer

This project is open-source under the **MIT License**. Handbook text, tables, regulations, and institutional names remain the intellectual property of Ho Chi Minh City University of Education (HCMUE). This software is developed independently for educational, research, and community assistance purposes.
