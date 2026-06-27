---
title: HCMUE Student Handbook RAG
emoji: 🎓
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

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

The **HCMUE Student Handbook RAG** is an advanced Retrieval-Augmented Generation (RAG) system designed to answer complex questions regarding the student handbook of Ho Chi Minh City University of Education. By leveraging a multi-cohort pipeline, it provides year-specific insights, acting as an intelligent academic advisor that parses regulations, tuition fees, and policies for various student generations (e.g., K48, K51) to deliver precise, grounded, and citable answers.

## 🚀 Live Demo

- **Vercel UI**: https://student-handbook-rag-chatbot.vercel.app/
- **Hugging Face Backend**: https://huggingface.co/spaces/AnhFeee/hcmue-handbook-rag-api

## 🏛️ High-Availability (HA) Architecture

```mermaid
graph TD
    User([👨‍🎓 Student]) -->|Asks Question| Frontend[React / Vite UI]
    Frontend -->|API Request| Backend[FastAPI Backend]
    
    subgraph Multi-Cohort RAG Pipeline
        Backend --> Router{Intent Router}
        Router -->|Out of Domain| Reject[Guardrail Rejection]
        Router -->|Valid Query| Cache[(Redis L1 Cache)]
        
        Cache -.->|Miss| Embed[BAAI/bge-m3 Embedding]
        Embed --> VectorSearch[(Qdrant Cloud v3)]
        
        VectorSearch -->|Returns 200-token Child Chunks| DocFetch[Fetch Parent_ID]
        DocFetch --> Mongo[(MongoDB Atlas)]
        Mongo -->|Returns Full Parent Doc| LLM[Groq / Gemini LLM]
        
        LLM -->|Generates Answer + Citations| Cache
    end
    
    Cache -->|Returns Answer| Frontend
```

### 1. ⚖️ Groq Load Balancer & Double-Loop Fallback Matrix
- Implemented a custom round-robin **API Key Load Balancer** rotating across 5 distinct Groq API keys to bypass the Free Tier Rate Limits (TPD/TPM).
- **Graceful Quality Degradation**: If the primary LLM (`llama-3.3-70b-versatile`) exhausts all keys, the system sequentially degrades to `gpt-oss-120b`, `qwen3.6-27b`, and finally `llama-3.1-8b-instant`. This guarantees **100% Uptime** and prevents generation failures during peak traffic.

### 2. 🚀 Two-Tier Caching System
- **L1 Cache (Redis via Upstash):** A centralized in-memory caching layer that allows multi-instance backend deployments to share state and skip LLM re-generation for common student queries.
- **L2 Cache (Local JSON Fallback):** In the event of a network partition or Redis downtime, the system dynamically spins up local ephemeral JSON caches to guarantee zero-downtime operation.

### 3. 🛡️ Intelligent Guardrails & Router
- Rejects jailbreaks, out-of-domain queries, and generic greetings in less than `500ms`, saving LLM tokens and computation resources.

### 4. ☁️ Multi-Cohort Parent-Child Storage Architecture
- **MongoDB Atlas (DocStore):** Acts as the centralized "Parent" storage holding full, uncut regulation documents for both K48 and K51 cohorts, guaranteeing that the LLM is fed 100% of the context without arbitrary chunking truncations.
- **Qdrant Cloud (VectorDB):** Stores highly-focused, overlapping 200-token "Child" chunks that act as semantic pointers to the MongoDB documents, achieving sub-millisecond similarity search accuracy while dodging vector dilution.
- **LangSmith Tracing:** Integrated end-to-end tracing capturing chunk relevance, LLM latency, context length, and exact token costs per query.

### 5. 🧬 Dynamic Multi-Cohort Pipeline
- Fully autonomous ingestion pipeline capable of parsing multiple student handbooks (e.g., K48, K51) simultaneously.
- Intelligent prefixing and collision-free ID management across MongoDB and Qdrant allow the Chatbot to effortlessly contrast and compare regulations across different school years.

---

## 📊 Automated Evaluation Metrics (RAGAS / LLM-as-a-Judge)

The RAG pipeline was comprehensively evaluated against a meticulously augmented dataset of **250 test cases**, assessed strictly by an autonomous LLM-as-a-Judge (`gemini-3.1-flash-lite` at `temperature=0.0`).

### 1. Generation Quality (100 Complex Cases)
| Metric | Score | Description |
|---|---|---|
| **Answer Relevance** | **92.2%** | High precision in addressing the core intent without rambling. |
| **Faithfulness** | **77.1%** | Grounding verification to strictly prevent AI hallucination. |
| **Correctness** | **71.5%** | Absolute strict factual correctness against golden ground-truth. |

### 2. Answer Behavior Guardrails (50 Cases)
| Metric | Score | Description |
|---|---|---|
| **Pass Rate** | **86.0%** | Success in deflecting out-of-domain, malicious, or unanswerable queries. |
| **Status Accuracy** | **94.0%** | Precision of the NLP Router in categorizing the query domain. |
| **Citation Accuracy** | **100.0%** | Perfect linking to exact pages, documents, and chunk types. |

### 3. Retrieval Quality (100 Cases)
| Metric | Score | Description |
|---|---|---|
| **Intent Accuracy** | **90.0%** | Correct classification of user intent by the Query Router. |
| **Strategy Accuracy** | **91.0%** | Precision in selecting the most optimal retrieval path (Semantic vs Exact). |

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

---

## 🔄 Rebuild Data Artifacts

To rebuild extraction, chunking, local databases, and evaluation reports for a single cohort (e.g., K48):

```bash
python -m scripts.run_all_preprocessing
```

To run the **Dynamic Multi-Cohort Pipeline** (Parsing and merging both K48 and K51, then pushing to Cloud):

```bash
python scripts/build_multi_cohort.py
```

## ❓ Example Questions

- `CNTT ở đâu?`
- `Điểm B+ quy đổi sang hệ 4 bao nhiêu?`
- `Điểm rèn luyện 85 là loại gì?`
- `Muốn tạm nghỉ học cần mẫu đơn nào?`
- `Email Phòng Đào tạo là gì?`
- `Có thể học vượt để ra trường sớm không?`
- `Học bổng K48 và K51 khác nhau như thế nào?`

## ⚠️ Data Policy

This repository includes the demo source PDF handbooks for testing purposes. The project does not relicense the source document; ownership remains with the original publisher/source (HCMUE).

## 🚧 Limitations

- The system is domain-specific to the HCMUE student handbooks (K48, K51).
- Accentless Vietnamese is supported but accented Vietnamese is still the strongest path.
- Context resolution, query rewriting, and AI routing require valid LLM API keys when enabled.

## 🔮 Future Improvements

- Add semantic response caching.
- Add optional cross-encoder reranking.
- Expand robustness evaluation for accentless, typo-heavy, and slang-heavy Vietnamese.
- Generalize ingestion for multiple handbook/policy documents from other faculties.

---
*Built with ❤️ for the HCMUE Student Community.*
