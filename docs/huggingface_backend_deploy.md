# Deploy Backend On Hugging Face Docker Space

This workflow keeps the UI and backend separated:

```text
Streamlit Cloud UI -> Hugging Face Docker Space FastAPI backend -> ChromaDB + BGE-M3 + Gemini
```

Hugging Face Docker Spaces are useful here because the backend can run a custom
FastAPI service and often has more room for ML dependencies than a small generic
web-service tier.

## 1. Prepare Local Repo

Run:

```powershell
.\.venv\Scripts\python.exe -m scripts.check_deploy_artifacts
.\.venv\Scripts\python.exe -m compileall src app.py scripts
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Make sure `data/vectorstore/chroma` exists locally:

```text
OK: data/vectorstore/chroma
```

The main repository intentionally includes the demo PDF and a small prebuilt
vectorstore for portfolio reproducibility. Review the data/license policy first:
ChromaDB may contain text or metadata derived from the source handbook.

## 2. Create The Hugging Face Space

In Hugging Face:

1. Go to **Spaces** -> **Create new Space**.
2. Choose a name, for example:

```text
hcmue-handbook-rag-api
```

3. Choose **Docker** as the SDK.
4. Pick Public or Private.

Hugging Face Docker Spaces expose the port configured by `app_port`. The root
`Dockerfile` defaults to port `7860`, which matches the Space metadata template
in:

```text
deploy/huggingface/backend/README.md
```

## 3. Add Space Secrets And Variables

In the Space **Settings** tab, add:

Secrets:

```text
GEMINI_API_KEY=your_real_gemini_key
```

Variables:

```text
PORT=7860
STUDENT_RAG_CORS_ORIGINS=https://student-handbook-rag-hcmue.streamlit.app
```

You can temporarily set CORS to `*` while testing, then replace it with the real
Streamlit Cloud URL.

## 4. Push Backend Files To The Space

Clone the Space repository:

```powershell
git clone https://huggingface.co/spaces/<your-username>/hcmue-handbook-rag-api hf-backend-space
```

Copy the project files into that cloned Space repo. Keep or replace the Space
`README.md` with:

```text
deploy/huggingface/backend/README.md
```

At minimum, the Space repo needs:

```text
Dockerfile
requirements.txt
src/
configs/
data/processed/
data/vectorstore/chroma
assets/
```

Do not copy:

```text
.env
.streamlit/secrets.toml
.venv/
data/cache/
```

Commit and push inside the Space repo:

```powershell
git add .
git commit -m "Deploy FastAPI RAG backend"
git push
```

If Hugging Face asks for credentials, use a Hugging Face access token as the
password.

## 5. Verify Backend

After the Space finishes building, open:

```text
https://<your-username>-hcmue-handbook-rag-api.hf.space/health
https://<your-username>-hcmue-handbook-rag-api.hf.space/health/artifacts
```

`/health/artifacts` should return:

```json
{
  "status": "ok"
}
```

Then test chat:

```powershell
Invoke-RestMethod `
  -Uri "https://<your-username>-hcmue-handbook-rag-api.hf.space/chat" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body '{"query":"GPA 2.95 duoc xep loai hoc luc gi?","include_debug":true}'
```

The first request may be slow while the embedding model is downloaded and loaded.

## 6. Point Streamlit Cloud To Hugging Face Backend

In Streamlit Cloud secrets, set:

```toml
STUDENT_RAG_EXECUTION_MODE = "API"
STUDENT_RAG_API_BASE_URL = "https://<your-username>-hcmue-handbook-rag-api.hf.space"
```

Reboot the Streamlit app.

Expected flow:

```text
Streamlit Cloud -> Hugging Face Space /chat -> answer with citations
```

## Troubleshooting

If `/health` works but `/chat` is slow:

- Wait for the first model load.
- Check Space logs for model download/load progress.
- If it still fails, switch to a lighter embedding model or upgrade Space hardware.

If `/health/artifacts` says `missing_artifacts`:

- Confirm `data/vectorstore/chroma` was copied into the Space repository.
- Confirm `data/processed/...` files exist.

If Streamlit shows an API connection error:

- Open the HF backend `/health` URL directly.
- Confirm `STUDENT_RAG_API_BASE_URL` has no `/docs`, `/health`, or `/chat` suffix.
- Check the Space logs for a `/chat` request.
