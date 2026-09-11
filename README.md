<div align="center">
  <img src="./frontend/public/bot_avatar.png" width="112" alt="HCMUE AI assistant mascot">
  <h1>HCMUE AI</h1>
  <p><strong>Student Handbook RAG Assistant</strong></p>
  <p>
    A cohort-aware assistant for the Ho Chi Minh City University of Education handbooks: K48–K49, K50, and K51.<br>
    Multi-request planning, structured lookup, hybrid RAG, citations, and a React interface.
  </p>
  <p>
    <a href="https://www.hcmuebot.id.vn"><img src="https://img.shields.io/badge/Demo_Link-hcmuebot.id.vn-2563EB?style=for-the-badge" alt="Demo link; current deployment revision not verified"></a>
    <a href="https://huggingface.co/spaces/AnhFeee/hcmue-handbook-rag-api"><img src="https://img.shields.io/badge/Backend-Hugging_Face-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black" alt="Hugging Face backend link"></a>
    <a href="#evaluation"><img src="https://img.shields.io/badge/Evaluation-official--v1-7C3AED?style=for-the-badge" alt="Official-v1 local evaluation"></a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.11-3670A0?style=flat-square&logo=python&logoColor=white" alt="Python 3.11">
    <img src="https://img.shields.io/badge/FastAPI-Backend-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
    <img src="https://img.shields.io/badge/React_+_Vite-Frontend-20232A?style=flat-square&logo=react&logoColor=61DAFB" alt="React and Vite">
    <img src="https://img.shields.io/badge/Qdrant-Vector_Search-E21727?style=flat-square" alt="Qdrant">
    <img src="https://img.shields.io/badge/MongoDB-Parent_Docs-4EA94B?style=flat-square&logo=mongodb&logoColor=white" alt="MongoDB">
    <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-0F172A?style=flat-square" alt="MIT License"></a>
  </p>
  <p>
    <a href="#project-overview">Overview</a> ·
    <a href="#system-architecture">Architecture</a> ·
    <a href="#runtime-flow">Runtime Flow</a> ·
    <a href="#data-and-repository-structure">Data &amp; Repository</a> ·
    <a href="#evaluation">Evaluation</a> ·
    <a href="#local-setup">Run Locally</a> ·
    <a href="#build-and-deployment-status">Deployment</a>
  </p>
</div>

<p align="center">
  <img src="./frontend/public/chat_ui_screenshot.png" width="100%" alt="HCMUE AI chat interface">
</p>
<p align="center"><sub>Cohort-aware answers, cited sources, structured data, and handbook navigation.</sub></p>

> [!IMPORTANT]
> HCMUE AI is an independent student project—not an official HCMUE application. Verify cited sources or contact the responsible university office before making important academic decisions.

> [!NOTE]
> The current local candidate uses corpus **v33**, pipeline **v76**, normalizer **v28**, and Composer **Gemini 3.1 Flash-Lite / prompt v3.24**. Narrative retrieval applies Cohere `rerank-v4.0-fast` to the top 16 RRF child candidates before parent grouping; it fails open to the original RRF list when reranking is unavailable. Official-v1 and the Cohere experiment measured earlier runtime commits, so their metrics remain historical development measurements rather than scores for this candidate. Production-60 was not run, and the public deployment has not been verified against this candidate.

## 🧭 Contents

1. [Project overview](#project-overview)
   - [Demo & Hosting](#demo-and-hosting)
   - [At a glance](#at-a-glance) · [Capabilities](#capabilities-and-boundaries) · [Current identity](#current-release-identity)
2. [System architecture and runtime](#system-architecture)
   - [Runtime flow](#runtime-flow) · [Structured execution](#structured-execution) · [Retrieval](#retrieval-contract) · [Cache and delivery](#runtime-behavior)
3. [Data and Repository Structure](#data-and-repository-structure)
   - [Repository layout](#repository-layout) · [Source-reading guide](#source-reading-guide) · [Build pipeline](#data-build-pipeline)
4. [Evaluation](#evaluation)
5. [Local setup and checks](#local-setup)
   - [Rebuilding artifacts locally](#rebuilding-locally)
6. [Build and deployment status](#build-and-deployment-status)
7. [License](#license)

<a id="project-overview"></a>

## ✨ Project overview

The assistant combines two paths:

1. **Structured lookup** handles grade/scoring rules, foreign-language equivalency, office/faculty/program directories, cohort/category facts, and formula rules. A validated resolver returns records from reviewed JSON catalogs; the Composer is instructed to preserve returned structured values, but this is not a guarantee.
2. **Narrative retrieval** searches embedded child chunks, fuses dense and BM25 rankings with RRF, reranks a bounded child prefix with Cohere Fast, expands selected hits to full parent articles, and gives the composer a bounded evidence packet. A Cohere limit or failure falls back to the unchanged RRF ordering.

The system can ask for a missing cohort or category, return low confidence or out-of-domain status, and refuse unsupported completion. An answer-shaped sentence is not proof that the requested scope was selected correctly.

<a id="demo-and-hosting"></a>

### 🌐 Demo & Hosting

| Surface | Hosting | Link |
|---|---|---|
| Student-facing chatbot | Vercel with a custom domain | [Open HCMUE AI](https://hcmuebot.id.vn) |
| Backend API documentation | Hugging Face Spaces · FastAPI Swagger UI | [Explore the API](https://anhfeee-hcmue-handbook-rag-api.hf.space/docs) |
| Backend project page | Hugging Face Spaces | [View the Space](https://huggingface.co/spaces/AnhFeee/hcmue-handbook-rag-api) |

The hosted demo may differ from the local candidate documented below. See [Deployment](#build-and-deployment-status) for packaging and release checks.

<a id="at-a-glance"></a>

### 📌 At a glance

| Deterministic contract | Cohere retrieval Hit@5 | MRR | nDCG@5 | Mean Judge correctness |
|:---:|:---:|:---:|:---:|:---:|
| **124/135 · 91.85%** | **153/157 · 97.45%** | **0.9397** | **0.9447** | **0.9599 / 1 · 150 cases** |

<p align="center"><sub>Latest available result per suite: the retained deterministic contract run plus the newer Cohere Fast-16 retrieval and Generate + Judge experiment. Different denominators are not combined into one score.</sub></p>

- **Users:** students asking about regulations, procedures, schedules, requirements, and handbook facts.
- **Knowledge scope:** three merged handbook cohorts: K48-K49, K50, and K51.
- **Practical questions:** grade/scoring tables, foreign-language equivalency, office/faculty/program directories, cohort-specific regulations, and narrative procedures.
- **Answer modes:** structured lookup, narrative retrieval, and explicit clarification or low-confidence outcomes when the request is not answerable from authorized handbook context.
- **Runtime:** FastAPI backend, React/Vite frontend, Qdrant dense retrieval, MongoDB parent documents, optional Redis caches, a Qwen planner, and Gemini composition.
- **Current identity:** pipeline `v76-structured-resolution-contract`, query-plan normalizer `v28-resolver-owned-directory-fallback`, router prompt v41, answer prompt v3.24, and artifact build `build-934f1caf384f99ad96e9`.

The checked-in state is a reproducible local release candidate. A public URL in frontend configuration is a deployment target, not evidence that the corresponding service is currently healthy or promoted.

<a id="capabilities-and-boundaries"></a>

### 🛡️ Capabilities and boundaries

The assistant is designed to:

- preserve cohort and category constraints through planning, normalization, retrieval, and composition;
- use reviewed structured tables for exact catalog-style facts;
- cite the handbook parent article supporting a narrative response;
- expose clarification, out-of-domain, low-confidence, and error outcomes;
- serve the same prepared answer through JSON and server-sent events (SSE).

It does not claim to:

- calculate a new value when the handbook only provides a formula;
- use arbitrary outside knowledge to complete an answer;
- guarantee that a unique fact lock selected the requested scope;
- OCR every image or guarantee coverage for malformed or unreviewed tables;
- provide an independent human audit or production load, latency, or SLA result;
- prove that a configured Hugging Face, Vercel, Qdrant, or MongoDB target is currently deployed and healthy.

### 🧰 Technology stack

| Layer | Technology | Role |
|---|---|---|
| Web client | React, TypeScript, Vite | Chat, incremental answers, citations, source drawers |
| API | FastAPI, Pydantic | Request validation, admission controls, JSON/SSE delivery |
| Planner | Qwen on Groq | Typed tasks, lookup intent, slots, and cohort scope |
| Composer | Gemini | Answer generation from the prepared evidence packet |
| Retrieval | BGE-M3, BM25, RRF, Cohere Fast | Semantic/lexical child search, bounded child reranking, parent selection |
| Knowledge stores | Qdrant, MongoDB, JSON catalogs | Child vectors, full articles, structured facts |
| Operations | Redis, LangSmith, HF Spaces, Vercel | Optional shared response cache, tracing, hosting targets |

<a id="current-release-identity"></a>

### 🪪 Current release identity

| Component | Current repository value | Source |
|---|---|---|
| Python runtime | 3.11.9 | `runtime.txt` |
| Planner | `qwen/qwen3.8-27b` through Groq; typed JSON plan | `configs/ai_router.yaml` |
| Planner prompt | `structured-regulation-v41-explicit-request-count` | `src/retrieval/core/ai_router.py` |
| Plan normalizer | `v28-resolver-owned-directory-fallback` | `src/retrieval/core/query_plan.py` |
| Composer | `gemini-3.1-flash-lite`; temperature 0 | `configs/answer_generation.yaml` |
| Answer prompt | `student-handbook-answer-v3.24-grounded-table-context` | `src/generation/prompt_builder.py` |
| Pipeline | `v76-structured-resolution-contract` | `src/generation/answer_pipeline.py` |
| Embeddings | `BAAI/bge-m3`, 1,024 dimensions, normalized | `configs/retrieval.yaml` and v33 manifest |
| Corpus/artifact snapshot | v33, identified by the manifest build below | `data/processed/metadata/build_manifest.json` |
| Retrieval default | `vector_primary_graph_supplement`: dense + BM25 RRF → Cohere Fast top-16 child rerank → parent grouping; fail-open to RRF | `configs/retrieval.yaml`, `src/retrieval/core/hybrid_pipeline.py` |
| Qdrant target | `student_handbook_semantic_v33` | `data/processed/metadata/build_manifest.json` |
| MongoDB target | `parent_docs_v33` in database `chatbotHCMUE` | `data/processed/metadata/build_manifest.json` |
| Local artifact build | `build-934f1caf384f99ad96e9` | `data/processed/metadata/build_manifest.json` |

The reranker decision was informed by a [separate candidate experiment](docs/COHERE_FAST_RERANK_EXPERIMENT.md), but official-v1 remains the published RRF-only measurement. The `BAAI/bge-m3` value above is the embedding model; Cohere `rerank-v4.0-fast` is the distinct cross-encoder reranking stage. A current-runtime metric must be produced by a new frozen run rather than relabeling the earlier scores.

<a id="system-architecture"></a>

## 🏗️ System architecture

The map below connects the main components through the data they exchange. `AnswerService` owns the shared `AnswerPipeline`; the downstream boxes are modules called by that pipeline, not independent services. The next diagram expands the execution order and alternate outcomes.

**Diagram key:** solid arrows show the main call/data path; dotted arrows show supporting reads, optional services, or publication. Arrow labels specify what crosses the boundary. Stores do not call one another.

~~~mermaid
%%{init: {"flowchart": {"wrappingWidth": 180, "nodeSpacing": 20, "rankSpacing": 25, "padding": 8}}}%%
flowchart TD
    UI["React / Vite<br/>Chat, citations, source drawers"] -->|HTTP / SSE| API["FastAPI routes<br/>Schemas, capacity, rate limits"]
    API --> Pipeline["AnswerService / AnswerPipeline<br/>Shared lifecycle + orchestration"]
    Pipeline -->|question and context| Planner["AI Router + Normalizer<br/>Qwen plan / validation<br/>Local router cache"]
    Planner -->|validated tasks and cohorts| Execute["Task execution inside AnswerPipeline"]
    Execute -->|structured task| Structured["Structured dispatcher<br/>Look up JSON tables,<br/>directories and formula rules"]
    Execute -->|RAG task| CandidateSearch["Candidate retrieval<br/>Qdrant dense + local BM25<br/>RRF fallback pool: up to 24 children"]
    CandidateSearch -->|query + first 16 RRF children| Reranker["Cohere Fast reranker<br/>rerank-v4.0-fast<br/>Optional fail-open stage"]
    Reranker -->|valid child ordering| ParentLoad["Parent expansion<br/>Group children by parent ID<br/>Load full articles from MongoDB"]
    Reranker -.->|unavailable or invalid: original RRF ordering| ParentLoad
    Structured -->|tables, records, optional fact locks| Merge["Merge task results<br/>Preserve task and cohort scope"]
    ParentLoad -->|primary parent evidence| Merge
    Merge --> Packet["Guards + prompt builder<br/>Bounded evidence and citations"]
    Packet -->|answerable and cache miss| Composer["Gemini client<br/>Answer generation / streaming"]
    Composer --> Delivery["Pipeline and API delivery<br/>Answer, citations, status"]
    Delivery --> Display["React / Vite<br/>Render answer and source drawers"]
~~~

| Supporting component | Connection and purpose |
|---|---|
| Router cache | AI Router reads/writes local cached plans before a provider call. |
| Response cache | AnswerPipeline reads completed answers after evidence preparation; Redis or local JSON. |
| LangSmith | API-side tracing and feedback use bounded background submission; optional, outside the answer evidence path. |
| Health/readiness | Separate API routes check required configuration and artifact identities. |

**How to read this map:**

1. **Client → API → pipeline:** the API validates/admit requests; the service provides the shared pipeline instance.
2. **Planner → task execution:** the normalized plan determines which lookup/retrieval modules are called, with task-local inputs and cohort scope. These are alternative or combined branches, not a claim of parallel scheduling.
3. **RAG candidate search → reranker → parent expansion:** dense and BM25 rankings are fused first. Cohere may reorder only the bounded child prefix; it neither searches Qdrant nor loads MongoDB. A failed or unavailable rerank passes the original RRF ordering to parent expansion.
4. **Lookups/retrieval → merge:** structured results and primary parent evidence return to the same orchestration layer. Stores provide data to those modules; they do not call each other.
5. **Merge → packet → Composer → client:** guards and context limits select what can be composed; on a cache miss Gemini generates the answer, which returns through the API. `Display` is the same frontend as the input node, drawn twice to keep the flow readable.

This overview shows the answerable/cache-miss path. The runtime diagram below includes early outcomes and cache hits. Health/readiness are separate API checks; graph-related references use the separate UI-only path in the retrieval diagram.

### Layers and ownership

| Layer | Responsibility | Representative code |
|---|---|---|
| Presentation | Collects a question, shows citations/status, and renders related-source or graph UI. | `frontend/`, `frontend/src/` |
| API | Exposes `/chat`, `/chat/stream`, health/readiness/artifact checks, and feedback. | `src/api/routes/`, `src/api/main.py` |
| Service | Lazily owns one shared answer pipeline for synchronous and streaming requests. | `src/services/answer_service.py` |
| Planner | Interprets requests into typed tasks, slots, constraints, and output shape. | `src/retrieval/core/ai_router.py` |
| Normalizer | Canonicalizes and validates planner output; it is not a second semantic planner. | `src/retrieval/core/query_plan.py` |
| Structured resolver | Executes a validated lookup against reviewed catalogs and exception rules. | `src/retrieval/core/structured_dispatcher.py`, `formula_lookup.py` |
| Candidate retriever | Searches narrative children and fuses dense/BM25 rankings with RRF. | `src/retrieval/core/hybrid_pipeline.py` |
| Reranker | Optionally reorders the first 16 RRF children; validates a complete result and fails open without changing the original candidates. | `src/retrieval/core/cohere_reranker.py` |
| Parent expansion | Groups ranked children by parent ID, validates scope, and loads full parent articles from MongoDB. | `src/retrieval/core/hybrid_pipeline.py` |
| Evidence packet | Applies authorized scope, citations, context limits, and prompt guards. | `src/generation/answer_pipeline.py`, `prompt_builder.py` |
| Composer | Generates an answer from the packet without performing retrieval; instructed to ground claims in supplied evidence. | `src/generation/answer_pipeline.py` |
| Graph UI | Uses related-source/graph information for navigation or display; graph-derived sources are not Composer evidence. | `frontend/`, retrieval metadata |

<a id="runtime-flow"></a>

### 🔄 Runtime flow: from question to answer

For an answerable request with no response-cache hit, the backend follows this main path. A question can use structured lookup, regulation retrieval, or both.

~~~mermaid
%%{init: {"flowchart": {"wrappingWidth": 180, "nodeSpacing": 20, "rankSpacing": 25, "padding": 8}}}%%
flowchart TD
    Input["Question + selected cohort + history"] --> API["API validation + admission controls"]
    API --> Prepare["AnswerPipeline.prepare_answer<br/>Input/cohort normalization"]
    Prepare --> Planner["AI Router<br/>Pre-Planner slang normalization<br/>Router cache or Qwen call"]
    Planner --> Normalize["Post-Planner QueryPlan normalization<br/>Tasks, slots, cohorts, validation"]
    Normalize --> Execute["execute_task<br/>Dispatch each task and cohort"]
    Execute --> Structured["Structured task<br/>JSON lookup + optional fact lock"]
    Execute --> Search["RAG candidate search<br/>Dense + BM25 → RRF<br/>Build fallback pool of up to 24 children"]
    Search --> Rerank["Cohere Fast reranker<br/>Reorder first 16 children"]
    Rerank -->|valid complete ranking| Parent["Parent expansion<br/>Group by parent ID + load MongoDB articles"]
    Rerank -.->|missing key, limit, timeout or invalid result<br/>use original RRF ordering| Parent
    Execute --> Clarify["Clarify task<br/>Missing-information question"]
    Structured --> Merge["Merge task results<br/>Evidence, coverage, source identity"]
    Parent --> Merge
    Clarify --> Merge
    Merge --> Guard["Request-level guards<br/>Stop if no answer can be composed"]
    Guard -->|terminal outcome| Terminal["Clarification / out of scope / insufficient evidence / error<br/>No Composer call"]
    Guard -->|answerable / partly answerable| Packet["Select citations + build bounded packet<br/>Preserve task/cohort associations"]
    Packet --> Cache["Check evidence-bound response cache"]
    Cache -->|miss| Compose["Gemini Composer<br/>Sync generate or streaming chunks"]
    Cache -->|hit| Reuse["Reuse saved answer<br/>Skip Composer"]
    Compose -->|success| Final["Finalize answer + citations + status<br/>Cache successful result"]
    Compose -->|failure| Failure["Error outcome<br/>Do not cache as success"]
    Compose -. incremental text for SSE .-> Output["API delivery<br/>JSON or SSE tokens / metadata / done"]
    Final --> Output
    Terminal --> Output
    Reuse --> Output
    Failure --> Output
~~~

1. **Receive:** the API accepts the question, selected cohort, and optional conversation history.
2. **Plan:** Planner identifies what the student wants and separates multiple requests. Normalizer validates and canonicalizes that plan before execution.
3. **Find candidates:** structured tasks look up reviewed JSON tables or directory records. RAG tasks search narrative children with dense + BM25 and build an RRF fallback pool of up to 24 candidates.
4. **Rerank and expand:** Cohere Fast receives the task query and at most the first 16 RRF children. On success, those reranked children continue to parent grouping and the unused RRF tail is discarded. On failure, the original RRF pool of up to 24 continues unchanged. The resulting children are then expanded into full MongoDB parent articles.
5. **Prepare context:** merge the task results without losing their cohort boundaries, check whether they can support an answer, and build a context-limited evidence packet. Structured evidence can include the selected table plus an exact lookup result; parent articles can include reviewed tables.
6. **Compose:** Gemini uses the packet to answer the covered requests. It does not perform another retrieval step.
7. **Deliver:** return the answer, citations, and status through JSON or SSE. Streaming delivers text incrementally before final metadata.

**Shortcuts and failures are separate from the main path:**

| Situation | What happens |
|---|---|
| The whole request needs clarification, is out of scope, or has insufficient evidence | Return an explicit outcome without calling Composer. Retrieval errors also stop before composition. |
| Only part of a multi-request question needs clarification | Composer can answer the covered parts and ask for the missing information. |
| Response cache hit | After retrieval, guards, and packet preparation, reuse the saved answer instead of calling Composer. |
| Composer/provider failure | Return an error/fallback outcome; do not cache it as a successful answer. |

Provider retries do not represent extra reasoning stages. These steps describe logical processing, not every individual SSE event.

<a id="structured-execution"></a>

### 🧩 Structured execution

This is the structured branch inside task execution. Catalogs define data and applicability; domain lookup functions perform the supported operations. A directory search is not a numeric table conversion.

~~~mermaid
%%{init: {"flowchart": {"wrappingWidth": 180, "nodeSpacing": 20, "rankSpacing": 25, "padding": 8}}}%%
flowchart TD
    Task["Validated structured task<br/>lookup_type, operation, slots, cohorts"] --> Scope["Execute within task cohort<br/>Keep task-local query and inputs"]
    Scope --> Dispatch["structured_dispatcher<br/>Choose lookup implementation"]
    Dispatch --> Tables["Table lookups<br/>Select applicable reviewed tables<br/>Optionally resolve a grounded value"]
    Dispatch --> Directory["Catalog matching<br/>Match names / aliases in profiles<br/>Return relevant records and fields"]
    Dispatch --> Formula["Formula lookup<br/>Read formula_rules.json<br/>Formula + variables, no calculation"]
    Tables --> Resolution["StructuredResolution<br/>Result + source identity"]
    Directory --> Resolution
    Formula --> Resolution
    Resolution --> Covered["Evidence available<br/>Full selected table / matching records<br/>Optional resolved_result"]
    Resolution --> Missing["Missing required information<br/>Clarification / uncovered task"]
    Missing --> Merge["Merge task coverage and clarification<br/>Request-level guards"]
    Covered --> Merge
    Merge -->|fully or partly answerable| Packet["Merged task/cohort evidence packet<br/>Composer receives structured evidence"]
    Merge -->|nothing answerable| Terminal["Terminal clarification / insufficient evidence<br/>No Composer call"]
~~~

**How to read this branch:** dispatch selects a lookup implementation, which reads its catalog and returns evidence plus provenance. A supported, grounded lookup may add `resolved_result`; it does not replace the selected table. Coverage and missing inputs then rejoin the request-level merge. A partial request can continue to Composer, while a wholly unanswerable request stops at a terminal outcome. The packet shown here is the same packet used by the runtime flow, not a second Composer stage.

| Lookup branch | Local data read | Evidence returned |
|---|---|---|
| Tables: scoring, conduct, language, scholarship, study duration | Structured table registry and reviewed table JSON; cohort/applicability metadata | Full selected table representation, source identity, and optional `resolved_result` |
| Directory: office, faculty, program, student service | Directory profiles/catalogs with unit names, aliases and contact/service fields | Matching records and provenance; no numeric conversion |
| Formula | `data/processed/tables/formula_rules.json` | Formula definition, variables and source rule; no computed personal result |

`resolved_result` is added only when the lookup can determine the result under its validated-input contract. Evidence-only results do not automatically fail: whole-table requests and non-unique results can still be useful. Missing information that prevents a safe lookup is represented separately; it must not be turned into a guessed fact lock.

- **Planner:** interprets the request and owns semantic task decomposition. Plans contain bounded tasks and context.
- **Normalizer:** canonicalizes aliases, validates enums and required fields, rejects malformed plans, and applies deterministic defaults. It does not reinterpret the request as a new semantic planner.
- **Resolver:** executes the validated structured lookup against the appropriate catalog. `formula_lookup.py` returns formula, variables, and source rule; it does not calculate a result absent from the handbook.
- **Fact locks:** a unique structured match is passed as a fact-lock/resolved result and the prompt instructs Composer not to rewrite it, but neither is a guarantee that the intended cohort, category, or other scope was selected.
- **Structured evidence:** the current path keeps the full selected table or matching directory records alongside any fact lock. It does not replace the table with a reduced row-only packet or bypass Composer. Mixed structured/RAG tasks are composed together, with task/cohort boundaries retained.
- **Composer:** receives authorized evidence and a prompt guard. The prompt instructs it to preserve structured results, but the official audit records known omissions, unsupported additions, and contradictions; exact preservation is not guaranteed.

<a id="retrieval-contract"></a>

### 🔎 Retrieval contract

~~~mermaid
%%{init: {"flowchart": {"wrappingWidth": 180, "nodeSpacing": 20, "rankSpacing": 25, "padding": 8}}}%%
flowchart TD
    subgraph Offline["OFFLINE BUILD"]
        Docstore["Full parent docstore<br/>all_docstore_items.json"] --> Extract["graph_extractor<br/>Extract explicit article/document references<br/>Validate source and target IDs"]
        Extract --> Edges[("document_edges.json<br/>Validated reference edges")]
    end
    Task["Online RAG task<br/>Query + cohort"] --> Dense["BGE-M3 query embedding<br/>Qdrant dense search"]
    Task --> Sparse["In-process BM25<br/>Sparse regulation search"]
    Dense --> Fusion["Union child IDs + Reciprocal Rank Fusion<br/>k = 60; fallback pool up to 24"]
    Sparse --> Fusion
    Fusion -->|first 16 children| Rerank["Cohere rerank-v4.0-fast<br/>Return a complete ordering<br/>Optional fail-open stage"]
    Rerank -->|success: reranked set, up to 16| Group["Group ranked children by parent ID<br/>Load and validate parent scope"]
    Rerank -.->|failure: original RRF pool, up to 24| Group
    Mongo[("MongoDB parent_docs_v33<br/>Full articles + reviewed tables")] -. parent records .-> Group
    Group --> Primary["Primary results<br/>Up to 5 parents per default call<br/>Focused child references + full parent text"]
    Primary --> Merge["Return to request-level merge<br/>Combine task evidence; preserve cohorts"]
    Merge --> Packet["Guards + bounded evidence packet<br/>Select context and citations"]
    Packet -->|answerable and response-cache miss| Composer["Gemini Composer<br/>Shared request-level answer generation"]
    Composer --> Answer["API → UI<br/>Answer text + citations"]
    Primary -. seed parent IDs .-> Graph["Graph traversal + scope filters<br/>Related-source supplement"]
    Mongo -. related parent records .-> Graph
    Graph --> Related["related_references<br/>UI navigation only; not Composer evidence"]
    Related --> Navigation["API → UI<br/>Related-source navigation"]
    Edges -. loaded reference edges .-> Graph
~~~

**How to read this retrieval pipeline:**

1. **Candidate search:** the retriever sends the task query to dense search and local BM25 with cohort/content filters. Both rank narrative children, not complete MongoDB articles.
2. **Fusion → child rerank → parent lookup:** RRF combines child rankings into a fallback pool of up to 24 candidates. Cohere Fast receives at most the first 16 children before any parent is chosen. A successful call passes that reranked set onward and discards the unused tail; a limit, timeout, invalid response, or missing key passes the original pool of up to 24 onward. The retriever then groups the resulting children by `parent_section_id` and loads the corresponding full parent records from MongoDB.
3. **Offline graph source:** [graph_extractor.py](src/ingestion/graph_extractor.py) reads the full parent docstore during the [build pipeline](#build-pipeline). It extracts explicit references between articles/documents, validates their IDs, and writes [document_edges.json](data/processed/graphs/document_edges.json). This file is a local JSON edge list, not a graph database, embedding index, or extra model.
4. **Online graph use:** selected parent IDs seed traversal over that saved edge list. Scope checks and parent lookups produce `related_references` for UI navigation. This branch ends at the UI; it does **not** feed the Composer packet or add answer evidence.

**Reranker contract:**

| Boundary | Contract |
|---|---|
| Position | After dense/BM25 RRF and before grouping children into parents. It is used only by the narrative RAG branch. |
| Input | One task-local query plus at most the first 16 items from the ordered RRF child list. Any remaining candidates are retained only for the fail-open path. |
| Accepted output | A complete, valid permutation of the submitted child IDs with finite normalized relevance scores. |
| Effect | Reorders child candidates only. It does not select a structured table, change cohort scope, fetch parent documents, traverse graph edges, or compose the answer. |
| Success behavior | Parent grouping receives the complete Cohere ordering of at most 16 submitted children; an unused RRF tail does not continue on this path. |
| Failure behavior | Missing/exhausted keys, timeout, HTTP/provider failure, malformed output, or incomplete ordering returns the original RRF pool of up to 24 immediately; the request does not wait for a key cooldown. |
| Downstream consumer | Parent grouping uses either the accepted Cohere set (up to 16) or the unchanged fail-open RRF pool (up to 24), then loads up to five scoped parent articles from MongoDB. |

**One shared composition stage:** the Composer node is the same request-level stage shown in the runtime diagram, not an extra model call inside each retrieval task. Other task results, including structured evidence in a mixed question, join at the request-level merge. The diagram shows the answerable/cache-miss continuation; cache hits and terminal outcomes follow the runtime flow above. Answer display and related-source navigation are two roles of the same frontend, not separate applications.

Dense and BM25 searches use cohort/content filters. The default search limit is 24 per ranking source and RRF forms a fallback pool capped at 24. A successful Cohere call replaces that pool with its complete ordering of the submitted prefix of at most 16; a fail-open call preserves the full RRF pool. BM25 is initialized from Qdrant child payloads into an in-process index; it is not a second remote database. The implementation is vector-primary: an empty valid dense seed set returns no results before sparse fusion. The diagram shows data dependencies, not parallel search scheduling.

The default `ChildParentHybridRetriever` fuses dense and BM25 rankings with RRF (`k=60`) and asks Cohere to return a complete reranking of the first 16 child candidates. Only a complete, valid permutation is accepted. Success passes those at-most-16 children to parent grouping; failure passes the original at-most-24 RRF pool unchanged. A retrieval call uses up to five final parent articles after candidate ranking; compound plans may make multiple task-level calls and aggregate results. “Top five” means per retrieval call, not five for every compound question.

A child hit expands to its full parent article, including reviewed table content, subject to task/cohort scope and context budget. Focused child text locates the article; it is not a substitute for the parent record.

Graph neighbors are context-only related sources for navigation and display. They do not become Composer evidence. The default mode is `vector_primary_graph_supplement`; `no_graph` (no graph neighbours) and `vector_only` (dense retrieval without BM25 fusion, no graph) are explicit ablations. Reranking changes child order before parent grouping; it does not alter structured lookup, graph traversal, or Composer behavior.

<a id="runtime-behavior"></a>

### ⚙️ Cache, delivery and failure behavior

At request time, `AnswerService` lazily shares one `AnswerPipeline` for both API delivery modes. `prepare_answer` performs planning, task execution, retrieval or structured resolution, scope guards, citation selection, and evidence-packet construction before the JSON or SSE adapter delivers the result. The API surface is `POST /chat`, `POST /chat/stream`, the health/readiness/artifact checks, and feedback.

| Concern | Contract |
|---|---|
| Router cache | Caches Qwen planner decisions; controlled by `configs/ai_router.yaml` and `STUDENT_RAG_DISABLE_ROUTER_CACHE`. |
| Response cache | Caches a completed answer after retrieval and evidence selection, keyed with question, selected citations, evidence/context fingerprint, cohort, pipeline version, and prompt version. |
| Terminal versus partial clarification | When the whole plan needs clarification, `prepare_answer` returns a terminal clarification without Composer. In a mixed plan, covered units can coexist with a `needs_clarification` unit; the evidence packet lets Composer answer covered units and ask only for the missing unit's clarification. |
| Provider retry | Key rotation/HTTP retry belongs to provider calls; it does not create multiple composition stages in one successful response. |
| Cohere rate limits | `COHERE_API_KEYS` is a comma-separated process-local pool. The retriever rotates immediately on HTTP 429 and proactively caps requests per key in a rolling minute; it never sleeps in the request path and falls back to RRF when no key is available. |
| Sync/stream delivery | Both paths share preparation, retrieval, guards, and evidence construction; JSON and SSE use separate delivery adapters afterward. |

The official-v1 evaluation disabled quality caches. The normal local configuration can enable caches; that is not the evaluation configuration.

<a id="data-and-preprocessing"></a>
<a id="data-and-repository-structure"></a>

## 🗂️ Data and Repository Structure

The repository separates **online answer handling**, **offline data preparation**, and **evaluation**. Start with the layout below, then use the source-reading guide to follow one request through the backend.

<a id="repository-layout"></a>

### 🧭 Repository layout

This is a selected map of the current checkout, not an exhaustive listing. Cache folders and local outputs may not exist in a fresh clone.

~~~text
student_handbook_rag/
├── configs/                     # Model settings, aliases, lookup and retrieval contracts
├── data/
│   ├── raw/                     # Source handbook PDFs; offline build inputs
│   ├── curated/                 # Reviewed corrections, aliases and table-region metadata
│   ├── processed/               # Generated, versioned knowledge artifacts
│   │   ├── tables/              # Structured tables, registry and formula rules
│   │   ├── directories/         # Office/faculty/service profiles and program catalogs
│   │   ├── chunks/              # Full parents, narrative view and searchable children
│   │   ├── graphs/              # Related-article edges for UI navigation
│   │   ├── amendments/          # Amendment artifacts
│   │   └── metadata/            # Build manifest, identities and audit metadata
│   ├── eval/
│   │   ├── official_v1/         # Current evaluation dataset, results and provenance
│   │   ├── product_acceptance/  # Historical acceptance review record; not a headline suite
│   │   ├── release_v33_smoke/   # Retained v33 release-verification evidence
│   │   └── reports/             # Local run outputs; not necessarily tracked in Git
│   └── cache/                   # Runtime caches and provider key-pool state
├── src/
│   ├── api/                     # HTTP/SSE routes, schemas, admission and health checks
│   ├── services/                # Application-facing shared pipeline lifecycle
│   ├── generation/              # Answer orchestration, evidence prompts and Composer
│   ├── retrieval/
│   │   ├── core/                # Planner, validation, structured lookup and hybrid RAG
│   │   └── vectorstore/         # Storage adapters, including MongoDB parent access
│   ├── common/                  # Shared cohort, source-identity and configuration helpers
│   ├── preprocessing/           # Handbook structure and source preparation
│   ├── extraction/              # Structured-data extraction
│   ├── chunking/                # Chunk construction
│   ├── ingestion/               # PDF loading, embeddings and graph ingestion
│   └── evaluation/              # Evaluation suites and supporting logic
├── frontend/                    # React + TypeScript + Vite application
├── scripts/                     # Build, audit, evaluation, upload and deploy entrypoints
├── tests/                       # Unit, integration and regression coverage
├── docs/                        # Contracts, maintenance boundaries and historical reports
├── work/                        # Ignored local experiments and review outputs
├── Dockerfile                   # Backend container definition
├── .dockerignore                # Direct Docker-build exclusions
├── requirements*.txt            # Runtime, development and evaluation dependencies
└── constraints-runtime.txt      # Runtime dependency constraints
~~~

| Boundary | What belongs here | What it is not |
|---|---|---|
| Online runtime | API/service, planning, lookup, retrieval, composition and storage clients | A per-request PDF parser or corpus rebuild |
| Offline build | Source PDFs, curated reviews, extraction, chunking and build scripts | A live-answer fallback mechanism |
| Knowledge artifacts | Versioned JSON, parents, children, graph and manifest | Interchangeable copies: each representation has a different role |
| Evaluation | Dataset, evaluator, run outputs and provenance | Runtime evidence or a guarantee of deployment health |
| Local working state | Cache and `work/` outputs | Authoritative source data or files to deploy wholesale |

Deploy packaging uses an explicit allowlist, not this entire tree. Generated artifacts can still be required runtime inputs; raw directory artifacts may also be required for rebuilding. Do not delete files merely because chat does not read them directly. See [Technical Debt and Maintenance Boundary](docs/TECHNICAL_DEBT.md).

<a id="source-reading-guide"></a>

### 📖 Suggested source-reading order

Follow one ordinary question first, then explore structured and RAG branches separately. These links identify entrypoints; they are not a claim that each module is a separate service.

| Step | Start here | What to look for |
|---|---|---|
| 1. Request contract | [schemas.py](src/api/schemas.py), [chat.py](src/api/routes/chat.py), [chat_stream.py](src/api/routes/chat_stream.py) | Accepted inputs, validation, sync/SSE delivery and error boundaries |
| 2. Lifecycle and orchestration | [answer_service.py](src/services/answer_service.py), [answer_pipeline.py](src/generation/answer_pipeline.py) | Shared initialization, `prepare_answer`, task execution and final output |
| 3. Interpretation and validation | [ai_router.py](src/retrieval/core/ai_router.py), [query_plan.py](src/retrieval/core/query_plan.py) | Planner schema/prompt, tasks, cohorts and normalization |
| 4a. Structured branch | [structured_dispatcher.py](src/retrieval/core/structured_dispatcher.py), [lookup registry](configs/structured_lookup_registry.yaml) | Capability dispatch, applicability, evidence-only results and fact locks |
| 4b. RAG branch | [hybrid_pipeline.py](src/retrieval/core/hybrid_pipeline.py) | Dense/BM25 fusion, parent lookup and separate related references |
| 5. Answer generation | [prompt_builder.py](src/generation/prompt_builder.py), [gemini_client.py](src/generation/gemini_client.py) | Evidence packet, instructions, provider retries and streaming |
| 6. Build and reproduce | [build_multi_cohort.py](scripts/build_multi_cohort.py), [parent/child contract](docs/PARENT_CHILD_BUILD_CONTRACT.md) | How source material becomes the runtime artifacts |

Read the matching tests after each component to see expected behavior and edge cases. For the latest measured candidate, start with the [Cohere Fast experiment](docs/COHERE_FAST_RERANK_EXPERIMENT.md); use the older official-v1 report only when reproducing the historical RRF-only baseline.

### v33 artifact snapshot

| Artifact | Count or value | Runtime role |
|---|---:|---|
| Full parent articles | 462 | Parent context and MongoDB documents |
| Narrative child chunks | 3,121 | Qdrant embedding/search input |
| Reviewed structured tables | 35 | Deterministic lookup; not Qdrant vectors |
| Graph edges | 78 | Related-source/navigation context |
| Cohorts | K48-K49: 123 parents / 877 children; K50: 166 / 1,082; K51: 173 / 1,162 | Manifest build partition |
| Embedding | `BAAI/bge-m3`, 1,024 dimensions, normalized | Dense child retrieval |
| Storage targets | Qdrant `student_handbook_semantic_v33`; MongoDB `parent_docs_v33` | Versioned promotion targets |
| Build ID | `build-934f1caf384f99ad96e9` | Cross-store identity |

The cohort labels and counts above are the manifest's source-of-truth labels. The manifest/provenance files retain the reconstruction hashes. The [parent/child build contract](docs/PARENT_CHILD_BUILD_CONTRACT.md) defines the separation invariant used by the local artifacts.

### Representations and separation

| Representation | Purpose | Separation |
|---|---|---|
| `data/processed/chunks/all_docstore_items.json` | Full parent articles, including reviewed table material. | Parent context and MongoDB; not child embedding input. |
| `data/processed/chunks/narrative_docstore_items.json` | Narrative parent view without separated reviewed table regions. | Narrative retrieval artifacts. |
| `data/processed/chunks/child_parent_chunks.json` | Searchable narrative children linked to parent IDs. | Embedded in Qdrant; child hits expand to parents. |
| `data/processed/tables/structured_tables_registry.json` and reviewed JSON | Exact catalog rows and formula rules. | Resolver input; not Qdrant vectors. |
| `data/processed/graphs/document_edges.json` | Related-source edges. | UI/context navigation, never Composer evidence. |
| `data/processed/metadata/build_manifest.json` | Counts, hashes, targets, embedding contract, and build ID. | Audit and promotion identity. |

<a id="data-build-pipeline"></a>

<a id="build-pipeline"></a>

### 🔨 Build pipeline

Source transformation is separate from publication and runtime promotion.

~~~mermaid
%%{init: {"flowchart": {"wrappingWidth": 180, "nodeSpacing": 20, "rankSpacing": 25, "padding": 8}}}%%
flowchart TD
    Sources["Handbook PDFs + cohort section config"] --> Parse["Extract PDF pages → parse sections<br/>Extract records → initial chunks"]
    Parse --> Merge["Merge three cohorts<br/>Namespace IDs and source references"]
    Merge --> Structured["build_structured_table_layer<br/>Tables, registry, directory profiles"]
    Reviews["Curated JSON + table-region reviews"] -. reviewed inputs .-> Structured
    Structured --> Split["build_parent_child_artifacts<br/>Apply reviewed table separation"]
    Reviews -. exact region / source checks .-> Split
    Split --> Parents["all_docstore_items.json<br/>Full parent articles with reviewed tables"]
    Split --> Children["child_parent_chunks.json<br/>Narrative children + parent links"]
    Parents --> Graph["graph_extractor<br/>Extract and validate explicit references<br/>Write document_edges.json"]
    Children --> Audit["Build manifest + integrity audits<br/>Counts, hashes, parent-child links"]
    Graph --> Audit
    Structured -. catalog artifacts .-> Audit
    Audit -. PUSH_REMOTE=1 .-> Preflight["Remote target preflight"]
    Preflight --> Upload["push_to_qdrant: embed children<br/>push_to_mongo: upload full parents"]
    Upload --> Verify["verify_remote_build<br/>Verify paired collections before promotion"]
~~~

The detailed sequence is:

1. Parse selected handbook sections from source PDFs and cohort configuration.
2. Extract structured records and create initial chunks.
3. Merge cohort artifacts and namespace source references; build and validate the structured table layer, registry, and directory profiles.
4. Build the reviewed parent/child representations and their links: retain reviewed table material in full parents and structured JSON, and create narrative children without the separated table regions.
5. Extract explicit article/document references from the full parent docstore, validate their stable source/target IDs, and save `data/processed/graphs/document_edges.json`. Runtime loads this local artifact for related-source UI navigation; it does not rebuild the graph per request.
6. Write the manifest and integrity/audit files before optional remote upload.
7. Optionally preflight empty/versioned Qdrant and MongoDB targets, upload, and verify. Remote writes are opt-in and separate from runtime promotion.

There is no automatic OCR-coverage claim. Image-based or malformed tables require reviewed JSON/regions. Tables are not silently converted into fallback narrative chunks, and policy prose/numbers are retained as source material.

<a id="evaluation"></a>

## 📊 Evaluation

This section reports the **latest available result for each suite**. The deterministic contract result is retained because Cohere does not participate in structured execution. Retrieval and Generate + Judge use the newer [Cohere Fast-16 candidate experiment](docs/COHERE_FAST_RERANK_EXPERIMENT.md). Older RRF-only retrieval/answer tables remain available through [official-v1 provenance](data/eval/official_v1/RESULTS_PROVENANCE.json) and Git history, but are not presented as current candidate metrics.

> [!NOTE]
> These suites were not all executed at one commit. Deterministic is the latest retained structured contract run. The Cohere experiment ran at base commit `8a172ebd` through an evaluation-only seam equivalent to the successful v74 rerank path; subsequent v74 changes added fail-open validation and key rotation. These are therefore latest-available development results, not a newly frozen full v76 evaluation or a production SLA.

### 🪪 Measured candidate

| Component | Measured identity |
|---|---|
| Datasets | 135 deterministic cases; 155 retrieval cases expanded into 157 retrieval events; 150 Generate + Judge cases |
| Corpus | v33; `build-934f1caf384f99ad96e9` |
| Deterministic run | official-v1 Planner/structured contract result; normalizer v26 |
| Cohere experiment | base commit `8a172ebd`; Qwen prompt v41 / normalizer v27 |
| Composer / prompt | `gemini-3.1-flash-lite` / v3.24 |
| Judge | `openai/gpt-oss-120b` |
| Retrieval change | RRF candidates → Cohere `rerank-v4.0-fast` top 16 children → parent grouping |
| Quality caches | Disabled for the quality run |

### 1. 🧭 Deterministic contract and execution — 135 cases

**Purpose:** test task interpretation, route/capability selection, cohort/applicability, structured execution, and applicable result assertions. Composer and Cohere output are not criteria for this suite.

| Metric | Result | Meaning |
|---|---:|---|
| Case contract pass | **124/135 · 91.85%** | Cases satisfying every applicable assertion; 11 cases failed at least one assertion. |
| `resolved_result` assertion | **44/50 · 88.00%** | Exact lookup-result assertions over the 50 fact-lock-eligible cases. |
| Planner fallback | **0/135** | No safe-fallback plan was recorded; this does not mean every plan was correct. |
| API errors | **0/135** | No provider/API failure was recorded; separate from semantic correctness. |

Non-applicable assertions are **N/A**, not automatic passes. A fact lock is required only when the structured contract has grounded inputs, valid scope, and one uniquely applicable result.

#### Breakdown by cohort and difficulty

| Dimension | Group | Passed / cases | Pass rate |
|---|---|---:|---:|
| Cohort | K48–K49 | 44/45 | 97.78% |
| Cohort | K50 | 41/45 | 91.11% |
| Cohort | K51 | 39/45 | 86.67% |
| Difficulty | Realistic | 102/108 | 94.44% |
| Difficulty | Stress | 22/27 | 81.48% |

#### Breakdown by capability

| Group | Passed / cases | Pass rate |
|---|---:|---:|
| Compound | 10/15 | 66.67% |
| Conduct classification | 9/9 | 100.00% |
| Faculty | 5/6 | 83.33% |
| Foreign language | 10/11 | 90.91% |
| Formula lookup (not calculation) | 6/6 | 100.00% |
| Missing input | 6/6 | 100.00% |
| Office | 9/9 | 100.00% |
| Out of domain | 6/6 | 100.00% |
| Regulation/policy | 12/12 | 100.00% |
| Program | 9/9 | 100.00% |
| Scholarship | 9/12 | 75.00% |
| Scoring/classification | 16/17 | 94.12% |
| Student service | 9/9 | 100.00% |
| Study duration | 8/8 | 100.00% |

Compound questions were the weakest group in this sample. Audited failures included route selection, omitted explicit inputs, slot/schema mismatch, unit confusion, and task dependencies; they were not all Resolver failures. Since normalizers v27 and v28 were introduced later, this table is retained as the latest deterministic measurement rather than presented as a fresh v76 score.

### 2. 🔎 Retrieval-layer comparison — 157 events

This paired comparison reused the same saved RRF child candidates for both arms. It isolates child reranking from Planner, Composer, and provider variation.

| Metric | RRF | Cohere Fast-16 | Delta |
|---|---:|---:|---:|
| Hit@5 | 0.9490 | **0.9745 · 153/157** | +0.0255 |
| MRR | 0.8737 | **0.9397** | +0.0660 |
| nDCG@5 | 0.8904 | **0.9447** | +0.0543 |
| Required-source recall@5 | 0.9469 | **0.9724** | +0.0255 |

Paired nDCG@5 improved on 23 events, regressed on 5, and was unchanged on 129. The saved-candidate run does not measure routing, generation, or production latency.

### 3. ✍️ Generate + Judge — 150 cases

All 150 answers were generated and judged. Seventy-seven cases entered retrieval and issued 80 Cohere calls; structured-only, clarification, and out-of-domain cases did not call the reranker.

| Metric | Latest mean | Meaning |
|---|---:|---|
| Answer correctness | **0.9599** | Correctness and requested-answer coverage under the fixed Judge rubric. |
| Faithfulness | **0.9745** | Support for answer claims in the evidence supplied to Composer. |
| Answer relevancy | **0.9796** | Focus on the user's question. |
| Citation correctness | **0.9657** | Support provided by cited sources. |
| Context recall | **0.8896** | Coverage of evidence needed for the expected answer. |
| Context precision | **0.5493** | Relevance of the complete context packet; lower than the other quality dimensions. |
| Hallucination rate | **0.0533** | Fraction flagged by the Judge rubric; not an independently verified error rate. |

| Serving outcome | Cases / 150 |
|---|---:|
| `answered` | 144 |
| `low_confidence` | 2 |
| `needs_clarification` | 2 |
| `out_of_domain` | 2 |
| API failures | 0 |

| Local complete-pipeline latency | Seconds |
|---|---:|
| Mean | 7.508 |
| p50 | 7.348 |
| p95 | 10.475 |
| Maximum | 24.410 |

The 80 successful Cohere calls averaged 0.690 seconds. These timings are local sequential observations, not HF streaming TTFT, concurrent-load measurements, or an SLA.

### Interpretation and limitations

- Retrieval ranking improved materially in the paired saved-candidate comparison; answer-level gains were smaller.
- Confidence intervals for the main Judge metrics overlap the historical RRF run, so the end-to-end difference is directional rather than a statistically established causal gain.
- Context precision decreased even while correctness, recall, faithfulness, and citations improved.
- Historical RRF/BGE answers and Cohere answers were not generated from the same runtime commit; Judge and model generation are stochastic.
- No Production-60 run or current HF load test was performed. The public deployment is not inferred from these local results.
- The current v76 implementation treats Cohere as optional: a missing key, quota limit, timeout, HTTP failure, or invalid response preserves the original RRF list.

The raw experiment artifacts are excluded from the runtime package; their SHA-256 identities and the complete interpretation are recorded in the linked experiment report. A future paper should run a frozen same-commit comparison with independent review before presenting the improvement as a research claim.

<a id="local-setup"></a>

## 💻 Local setup

### Backend

Python 3.11.9 is recorded in `runtime.txt`.

**Windows PowerShell**

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
~~~

**macOS/Linux**

~~~bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
~~~

`requirements.txt` is the runtime set. `requirements-dev.txt` adds development constraints and test/lint tooling; `requirements-eval.txt` layers on the same development set for evaluation work. Do not commit secrets from `.env`.

The `.env.example` template follows the current v33 storage targets. Set the service URLs and credentials for your environment:

~~~dotenv
QDRANT_COLLECTION_NAME=student_handbook_semantic_v33
STUDENT_RAG_HYBRID_COLLECTION=student_handbook_semantic_v33
MONGODB_PARENT_COLLECTION=parent_docs_v33
QDRANT_URL=<your-qdrant-url>
QDRANT_API_KEY=<your-qdrant-key>
MONGODB_URL=<your-mongodb-url>
MONGODB_DB_NAME=chatbotHCMUE
GEMINI_API_KEYS=<comma-separated-keys>
GROQ_API_KEYS=<comma-separated-keys>
COHERE_API_KEYS=<comma-separated-keys>
STUDENT_RAG_COHERE_RERANKER_ENABLED=true
STUDENT_RAG_COHERE_RPM_LIMIT_PER_KEY=10
~~~

`STUDENT_RAG_HYBRID_COLLECTION` is a compatibility override with precedence over `QDRANT_COLLECTION_NAME`. Keep both aligned, or leave the override unset; an old v32 override would otherwise select the wrong collection.

`COHERE_API_KEYS` accepts one or more authorized keys. The default `10` requests/minute/key is conservative for trial-key research; set the limit to the allowance of the key tier actually deployed. Rotation is process-local and matches the one-worker Docker runtime. It is a resilience mechanism, not permission to bypass account-level provider limits.

Optional settings include Redis response caching, LangSmith telemetry, and router/provider overrides. `STUDENT_RAG_REQUIRE_REDIS=true` requires Redis; `STUDENT_RAG_DISABLE_REDIS` disables Redis use. Keep evaluation cache settings separate from normal development.

Start the backend locally:

~~~bash
python -m uvicorn src.api.main:app --reload
~~~

Principal routes are `POST /chat`, `POST /chat/stream`, `GET /health`, `GET /health/readiness`, `GET /health/artifacts`, and `POST /chat/feedback`.

### Frontend

Node 20 is used by CI. From `frontend/`:

~~~bash
npm ci
npm run dev
~~~

For a production build check:

~~~bash
npm run lint
npm run build
~~~

`frontend/.env.example` contains a deployment-target API URL. Configure `VITE_API_BASE_URL` for the backend intended for use; the template value is not a deployment-health assertion.

### Checks

CI performs:

~~~bash
python -m pip check
python scripts/check_deploy_artifacts.py
python -m ruff check src tests scripts/check_deploy_artifacts.py scripts/run_official_deterministic.py scripts/run_official_answers.py --select E,F --ignore E402,E501
python -m pytest tests
~~~

Frontend CI uses Node 20 with `npm ci`, `npm run lint`, and `npm run build`. Evaluation scripts can contact model or vector-store providers and are not required for a documentation-only change.

### Running the official evaluation

The `official_v1` suites run from the repository root. Each run writes its report and a `run_snapshot.json` (git commit, dataset hash, planner, Composer and storage identity) under `data/eval/reports/`; `--limit N` runs a smoke subset and `--output DIR` resumes a run.

~~~bash
python -m scripts.run_official_deterministic --current-worktree
python -m scripts.run_official_answers --suite retrieval
python -m scripts.run_official_answers --suite answers
python -m scripts.run_official_answers --suite production --base-url https://<your-space>.hf.space
~~~

`--retrieval-mode no_graph` or `--retrieval-mode vector_only` runs a retrieval ablation. `scripts/regrade_official_deterministic.py` rescores a saved deterministic run without model calls. The production suite reports pass/fail release gates (success rate, 429s, cache protocol, p95 latency).

<a id="rebuilding-locally"></a>

### Rebuilding locally

The official full-source sequence is the multi-cohort entrypoint. Run it in an isolated worktree or disposable copy because it overwrites generated files under `data/processed/` and cleans generated legacy artifacts.

| Operation | Entrypoint |
|---|---|
| Three-cohort local rebuild | [`scripts/build_multi_cohort.py`](scripts/build_multi_cohort.py) |
| Manifest generation | [`scripts/build_artifact_manifest.py`](scripts/build_artifact_manifest.py) |
| Optional isolated parent/child contract check | [`scripts/build_parent_child_artifacts.py`](scripts/build_parent_child_artifacts.py) |
| Read-only remote verification | [`scripts/verify_remote_build.py`](scripts/verify_remote_build.py) |

**Windows PowerShell**

~~~powershell
$env:PUSH_REMOTE = "0"
.\.venv\Scripts\python.exe -m scripts.build_multi_cohort --qdrant-collection student_handbook_semantic_v33_candidate --mongo-collection parent_docs_v33_candidate
~~~

**macOS/Linux**

~~~bash
PUSH_REMOTE=0 .venv/bin/python -m scripts.build_multi_cohort --qdrant-collection student_handbook_semantic_v33_candidate --mongo-collection parent_docs_v33_candidate
~~~

The multi-cohort command invokes the structured table layer, parent/child separation, graph extraction, manifest generation, and local integrity audits in that order. The candidate collection names identify the intended remote targets in the manifest; with `PUSH_REMOTE=0`, no remote write or remote preflight occurs.

For an optional isolated parent/child contract inspection, use the [parent/child builder](scripts/build_parent_child_artifacts.py) with a new directory under `work/`. This CLI assumes its docstore, registry, and review inputs are already the correct source snapshot; it is not a substitute for the full source-build sequence and is not a publishing step.

**Optional Windows PowerShell contract check**

~~~powershell
.\.venv\Scripts\python.exe -m scripts.build_parent_child_artifacts --output-dir work\candidate-YYYYMMDD
~~~

**Optional macOS/Linux contract check**

~~~bash
.venv/bin/python -m scripts.build_parent_child_artifacts --output-dir work/candidate-YYYYMMDD
~~~

`scripts/verify_remote_build.py` is read-only but contacts configured services and requires credentials. A successful local build is not a completed remote promotion.

<a id="build-and-deployment-status"></a>

## 🚀 Build and deployment status

Deployment helpers do not prove that a live service exists.

For local packaging validation with current targets, use the dry-run path:

**Windows PowerShell**

~~~powershell
.\scripts\deploy_hf_backend.ps1 -DryRun -QdrantCollection student_handbook_semantic_v33 -MongoCollection parent_docs_v33
~~~

This checks the package and manifest contract without modifying a remote space. A real deployment requires explicit operator approval, credentials, and a post-deploy health/readiness check; this README does not claim those steps are complete. The script defaults already match v33; the explicit collection arguments above make the intended deployment targets visible to the operator.

<a id="license"></a>

## 📄 License

The source code is released under the [MIT License](LICENSE). Student-handbook content and university regulations remain the property of their respective publishers.
