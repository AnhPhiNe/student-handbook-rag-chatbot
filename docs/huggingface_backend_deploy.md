# Deploy Backend On Hugging Face Docker Space

This workflow keeps the UI and backend separated:

```text
React/Vite UI -> Hugging Face Docker Space FastAPI backend -> Qdrant Cloud + Gemini
```

The current production backend uses Qdrant Cloud for vector search. The local
ChromaDB vectorstore remains useful for GitHub portfolio reproducibility, but it
does not need to be copied into the Hugging Face Space when
`VECTORDB_PROVIDER=qdrant_cloud` is configured.

## 1. Prepare Local Repo

Run these checks before updating the Space:

```powershell
.\.venv\Scripts\python.exe -m compileall src scripts
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m scripts.evaluate_router_behavior --fail-under-intent 0.95 --fail-under-strategy 0.95
```

For end-to-end offline answer behavior:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_answers --fail-under-pass-rate 1.0
```

## 2. Space Repository Structure

The Hugging Face Space repository should stay backend-only. It should contain:

```text
Dockerfile
README.md
requirements.txt
requirements.lock
configs/
src/
data/processed/
```

Do not copy:

```text
.env
.venv/
frontend/
tests/
docs/
scripts/
data/cache/
data/vectorstore/
```

`data/vectorstore/` is intentionally excluded from the Space because production
retrieval uses Qdrant Cloud.

## 3. Space Secrets And Variables

In the Hugging Face Space Settings tab, configure:

Secrets:

```text
GEMINI_API_KEY=...
GROQ_API_KEY=...
QUERY_REWRITER_API_KEY=...
QDRANT_URL=...
QDRANT_API_KEY=...
STUDENT_RAG_ADMIN_API_KEY=...
```

Variables:

```text
PORT=7860
VECTORDB_PROVIDER=qdrant_cloud
QDRANT_CREATE_PAYLOAD_INDEXES=false
QUERY_REWRITER_ENABLED=true
STUDENT_RAG_CORS_ORIGINS=https://hcmuebot.id.vn
STUDENT_RAG_MAX_QUERY_CHARS=500
STUDENT_RAG_RATE_LIMIT_PER_MINUTE=20
STUDENT_RAG_SHOW_DEBUG=false
MONGODB_PARENT_LOOKUP_ENABLED=true
MONGODB_TIMEOUT_MS=3000
MONGODB_FAILURE_BACKOFF_SECONDS=300
```

`configs/answer_generation.yaml` in this repository currently sets
`query_rewriter.enabled: false`, so the query-rewriter layer is disabled by
default. If you want to enable Groq/Llama context resolution and query
rewriting in the Space, set `query_rewriter.enabled: true` in the Space copy
of `configs/answer_generation.yaml` before pushing backend files.

## 4. Push Backend Files

Use a separate clone of the Space repo, for example:

```powershell
git clone https://huggingface.co/spaces/AnhFeee/hcmue-handbook-rag-api hf_check
```

Copy only backend runtime files from the main repo into the Space clone:

```text
Dockerfile
deploy/huggingface/backend/README.md -> README.md
requirements.txt
requirements.lock
configs/
src/
data/processed/
```

Then commit and push inside the Space clone:

```powershell
git add Dockerfile README.md requirements.txt requirements.lock configs src data/processed
git commit -m "Deploy FastAPI RAG backend"
git push origin main
```

If Hugging Face asks for credentials, use a Hugging Face access token as the
password.

## 5. Verify Backend

After the Space rebuilds, open:

```text
https://anhfeee-hcmue-handbook-rag-api.hf.space/health
```

`/health/artifacts` is admin-only. Set `STUDENT_RAG_ADMIN_API_KEY` in Space
secrets and send it as `X-Admin-API-Key` when checking deployment artifacts:

```powershell
Invoke-RestMethod `
  -Uri "https://anhfeee-hcmue-handbook-rag-api.hf.space/health/artifacts" `
  -Headers @{"X-Admin-API-Key"=$env:STUDENT_RAG_ADMIN_API_KEY}
```

Expected response when Qdrant Cloud is configured:

```json
{
  "status": "ok",
  "required_artifacts": [
    {"path": "configs/answer_generation.yaml", "exists": true, "kind": "config"},
    {"path": "data/processed/tables/scoring_tables.json", "exists": true, "kind": "processed_json"},
    {"path": "data/processed/tables/formula_rules.json", "exists": true, "kind": "processed_json"},
    {"path": "data/processed/entities/entity_registry.json", "exists": true, "kind": "processed_json"},
    {"path": "data/processed/entities/query_expansion_rules.json", "exists": true, "kind": "processed_json"},
    {"path": "QDRANT_URL", "exists": true, "kind": "env"},
    {"path": "QDRANT_API_KEY", "exists": true, "kind": "env"}
  ]
}
```

Then test chat:

```powershell
Invoke-RestMethod `
  -Uri "https://anhfeee-hcmue-handbook-rag-api.hf.space/chat" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body '{"query":"Điểm B+ quy đổi sang hệ 4 bao nhiêu?","include_debug":true}'
```

The first request may be slower while the embedding model is loaded.

## 6. Point Frontend To Backend

In the React frontend deployment environment, set:

```text
VITE_API_BASE_URL=https://anhfeee-hcmue-handbook-rag-api.hf.space
```

The frontend should call the backend runtime URL, not the Hugging Face repository
page.

## Troubleshooting

If `/health/artifacts` returns `403`:

- Confirm `STUDENT_RAG_ADMIN_API_KEY` is set in the Space secrets.
- Confirm the same value is sent in the `X-Admin-API-Key` header.

If `/health/artifacts` says `missing_artifacts`:

- Confirm `VECTORDB_PROVIDER=qdrant_cloud` is set in the Space variables.
- Confirm `QDRANT_URL` and `QDRANT_API_KEY` are set as secrets.
- Confirm `data/processed/...` files exist in the Space repository.

If `/chat` is slow:

- Wait for the first embedding-model load.
- Check Space logs for model download/load progress.
- If logs show MongoDB SSL or server selection timeouts, confirm `MONGODB_URL`
  and MongoDB Atlas Network Access, or temporarily set
  `MONGODB_PARENT_LOOKUP_ENABLED=false`.
- Keep `MONGODB_TIMEOUT_MS` low, for example `3000`, so parent-document lookup
  cannot block answers for tens of seconds when MongoDB is unreachable.
- Consider upgrading Space hardware if cold starts are too slow.

If the React UI cannot connect:

- Confirm `VITE_API_BASE_URL` points to the `.hf.space` runtime URL.
- Confirm `STUDENT_RAG_CORS_ORIGINS` includes the Vercel frontend URL.
- Check the Space logs for incoming `/chat/stream` requests.
