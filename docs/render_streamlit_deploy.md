# Deploy: Streamlit Cloud UI + Render FastAPI Backend

This is the simplest non-Docker deployment path for the current project.

```text
User -> Streamlit Cloud UI -> Render FastAPI backend -> ChromaDB vectorstore + Gemini
```

## Before You Start

Run these locally:

```powershell
.\.venv\Scripts\python.exe -m compileall src app.py scripts
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m scripts.evaluate_router_behavior --fail-under-intent 0.95 --fail-under-strategy 0.95
.\.venv\Scripts\python.exe -m scripts.check_deploy_artifacts
```

The last command must show `OK` for:

```text
data/vectorstore/chroma
```

## Important: Vectorstore

Render must have the ChromaDB vectorstore at:

```text
data/vectorstore/chroma
```

Your local vectorstore is small enough for a portfolio demo, but Chroma may
include document text/metadata. Before deploying publicly, decide whether your
source-document rights allow publishing these generated artifacts.

For a quick private deployment test, you can temporarily include the vectorstore
in the GitHub repo. If you do that, remove or adjust this ignore rule first:

```text
data/vectorstore/
```

Then add:

```powershell
git add -f data/vectorstore/chroma
```

For a public repo, prefer a private backend repo, private Render deploy, or a
persistent disk/upload workflow if the data license is unclear.

## 1. Push To GitHub

Commit and push your current repo to GitHub.

Recommended files for this workflow:

```text
render.yaml
runtime.txt
requirements.txt
app.py
src/
configs/
data/processed/
data/vectorstore/chroma   # required by backend if not rebuilt on Render
```

Never commit:

```text
.env
.streamlit/secrets.toml
```

## 2. Deploy FastAPI Backend On Render

In Render:

1. Create a new **Web Service**.
2. Connect your GitHub repository.
3. Choose the Python environment, or let Render read `render.yaml`.
4. Use these commands if configuring manually:

Build command:

```bash
python -m pip install --upgrade pip && pip install -r requirements.txt
```

Start command:

```bash
python -m uvicorn src.api.main:app --host 0.0.0.0 --port $PORT
```

Health check path:

```text
/health
```

Environment variables:

```text
GEMINI_API_KEY=your_gemini_key
STUDENT_RAG_CORS_ORIGINS=https://your-streamlit-app.streamlit.app
PYTHON_VERSION=3.11.9
```

After deploy, open:

```text
https://your-render-api-url.onrender.com/health
https://your-render-api-url.onrender.com/health/artifacts
```

`/health/artifacts` should return:

```json
{
  "status": "ok"
}
```

If it says `missing_artifacts`, the backend cannot see the vectorstore or one of
the processed JSON files.

## 3. Deploy Streamlit UI On Streamlit Cloud

In Streamlit Cloud:

1. Create a new app from the same GitHub repository.
2. Set main file path:

```text
app.py
```

3. Add secrets:

```toml
STUDENT_RAG_EXECUTION_MODE = "API"
STUDENT_RAG_API_BASE_URL = "https://your-render-api-url.onrender.com"
```

The Streamlit UI does not need `GEMINI_API_KEY` in API mode.

## 4. Update Render CORS After Streamlit URL Exists

Once Streamlit gives you the final app URL, go back to Render and set:

```text
STUDENT_RAG_CORS_ORIGINS=https://your-streamlit-app.streamlit.app
```

Redeploy the backend if Render does not restart automatically.

## 5. Smoke Test

Open the Streamlit app and ask:

```text
Điểm rèn luyện 85 là loại gì?
```

Then ask:

```text
Email phòng Đào tạo là gì?
```

Expected behavior:

- Streamlit settings show `API` mode.
- Answers come from the Render backend.
- Sources render in the UI.
- Render logs show `/chat` requests with request IDs and latency.

## Troubleshooting

If Streamlit shows an API connection error:

- Check `STUDENT_RAG_API_BASE_URL` in Streamlit secrets.
- Open Render `/health` in a browser.
- Check Render service is awake.

If `/health/artifacts` returns `missing_artifacts`:

- Confirm `data/vectorstore/chroma` exists in the deployed backend.
- Confirm `data/processed/...` JSON files are present.

If Render build fails:

- Check whether the plan has enough RAM/storage for `torch`, `sentence-transformers`,
  and `chromadb`.
- Try a paid/larger instance or switch to a smaller embedding model later.

