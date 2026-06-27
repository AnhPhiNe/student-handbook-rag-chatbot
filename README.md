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
  <img src="https://img.shields.io/badge/ChromaDB-FF914D?style=for-the-badge" alt="ChromaDB">
  <img src="https://img.shields.io/badge/Qdrant-E21727?style=for-the-badge&logo=Qdrant&logoColor=white" alt="Qdrant">
  <img src="https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis">
  <img src="https://img.shields.io/badge/LangSmith-000000?style=for-the-badge" alt="LangSmith">
</p>

## 🌟 Overview

The **HCMUE Student Handbook RAG** is an advanced Retrieval-Augmented Generation (RAG) system designed to answer complex questions regarding the student handbook of Ho Chi Minh City University of Education. It acts as an intelligent academic advisor, parsing regulations, tuition fees, and university policies to deliver precise, grounded, and citable answers.

## 🏗️ High-Availability (HA) Architecture

This project is built with a strictly **Production-Ready, Enterprise-Grade** architecture, capable of serving thousands of concurrent students while preventing downtimes or API limit blockades.

### 1. ⚖️ Groq Load Balancer & Double-Loop Fallback Matrix
- Implemented a custom round-robin **API Key Load Balancer** rotating across 5 distinct Groq API keys to bypass the Free Tier Rate Limits (TPD/TPM).
- **Graceful Quality Degradation**: If the primary LLM (`llama-3.3-70b-versatile`) exhausts all keys, the system sequentially degrades to `gpt-oss-120b`, `qwen3.6-27b`, and finally `llama-3.1-8b-instant`. This guarantees **100% Uptime** and prevents generation failures during peak traffic.

### 2. 🚀 Two-Tier Caching System
- **L1 Cache (Redis via Upstash):** A centralized in-memory caching layer that allows multi-instance backend deployments (Vercel/Render) to share state and skip LLM re-generation for common student queries.
- **L2 Cache (Local JSON Fallback):** In the event of a network partition or Redis downtime, the system dynamically spins up local ephemeral JSON caches to guarantee zero-downtime operation.
- **Semantic Routing (ChromaDB):** Utilizes local Vector-based intent matching to map entirely new phrasing to identically cached answers.

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

### 4. Run the Frontend
```bash
cd frontend
npm install
npm run dev
```

---
*Built with ❤️ for the HCMUE Student Community.*
