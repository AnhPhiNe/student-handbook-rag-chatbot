---
title: HCMUE Student Handbook RAG API
emoji: 📚
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# HCMUE Student Handbook RAG API

FastAPI backend for the HCMUE Student Handbook RAG assistant.

Runtime stack:

- FastAPI chat API
- Qdrant Cloud vector search
- Groq/Llama context resolver and query rewriting when enabled in config
- Gemini answer generation when deterministic lookup is not enough

Useful endpoints:

- `/health`
- `/health/artifacts` (admin-only, requires `X-Admin-API-Key`)
- `/docs`
- `/chat`
- `/chat/stream`
