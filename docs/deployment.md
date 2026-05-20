# Deployment Workflow: Streamlit Cloud UI + FastAPI Backend

This workflow deploys the public demo as two services. It focuses on the
Docker/Docker Compose variant. For the simpler non-Docker Render workflow, see
`docs/render_streamlit_deploy.md`.

```text
User -> Streamlit Cloud UI -> FastAPI backend -> ChromaDB vectorstore + Gemini
```

The Streamlit app should run in `API` mode in production. The FastAPI backend is
the only service that needs the heavy retrieval artifacts and `GEMINI_API_KEY`.

## 1. Backend Service

Deploy the FastAPI backend with Docker using the repository `Dockerfile`.

Backend start command inside the image:

```bash
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

Required backend environment variables:

```text
GEMINI_API_KEY=...
STUDENT_RAG_CORS_ORIGINS=https://your-streamlit-app.streamlit.app
```

Required backend artifacts:

```text
configs/phase8_answer_generation.yaml
data/processed/tables/scoring_tables.json
data/processed/entities/entity_registry.json
data/processed/entities/query_expansion_rules.json
data/vectorstore/chroma
```

The processed JSON files are part of the repo. The ChromaDB vectorstore is a
generated local artifact and must be made available to the backend by one of
these approaches:

- Mount a persistent disk or volume at `/app/data/vectorstore`.
- Bake `data/vectorstore/chroma` into a private deployment image if size and
  source-document rights are acceptable.
- Rebuild the vectorstore in a deployment setup step, if the platform allows a
  long build and the source PDF is available.

Health checks:

```text
GET /health
GET /health/artifacts
```

`/health` is lightweight and does not load the model. `/health/artifacts` checks
that required config, processed JSON, and vectorstore paths exist.

## 2. Streamlit Cloud UI

Deploy `app.py` on Streamlit Cloud from the same GitHub repository.

Set Streamlit secrets or environment variables:

```text
STUDENT_RAG_EXECUTION_MODE=API
STUDENT_RAG_API_BASE_URL=https://your-fastapi-backend.example.com
```

The UI does not need `GEMINI_API_KEY` when it runs in API mode. The backend owns
Gemini calls and retrieval.

## 3. Local Option B Smoke Test

Run the backend:

```bash
python -m uvicorn src.api.main:app --reload
```

Run Streamlit in API mode:

```bash
$env:STUDENT_RAG_EXECUTION_MODE="API"
$env:STUDENT_RAG_API_BASE_URL="http://127.0.0.1:8000"
python -m streamlit run app.py --server.fileWatcherType none
```

Ask:

```text
Điểm rèn luyện 85 là loại gì?
```

Then verify:

- Streamlit is in API mode.
- The backend `/chat` response includes `request_id` and `latency_ms`.
- `/health/artifacts` returns `status: ok`.

## 4. Docker Compose Local Test

After building local vectorstore artifacts, run:

```bash
docker compose up --build
```

Open:

```text
http://localhost:8501
```

Backend API:

```text
http://localhost:8000/docs
```

## 5. Public Release Notes

Before deploying publicly, decide the data policy:

- If raw PDF redistribution rights are unclear, do not publish raw PDFs.
- Review processed JSON artifacts because they may contain extracted source text.
- Keep `.env` and Streamlit secrets out of Git.
