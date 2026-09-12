FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=7860

# Create non-root user
RUN useradd -m -u 1000 appuser

WORKDIR /app

COPY requirements.txt constraints-runtime.txt ./
RUN pip install --no-cache-dir -c constraints-runtime.txt -r requirements.txt \
    && pip check

# Bake the embedding model into the image. Downloading it at run time makes the
# first question after any container start wait for several GB. The model name
# is read from the retrieval contract so it cannot drift from the config.
ENV HF_HOME=/app/.cache/huggingface
COPY configs/retrieval.yaml ./configs/retrieval.yaml
RUN python -c "import yaml; from sentence_transformers import SentenceTransformer; SentenceTransformer(yaml.safe_load(open('configs/retrieval.yaml'))['embedding']['model_name'])"

COPY . .

# Change ownership and switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:' + os.environ['PORT'] + '/health')" || exit 1

# Load the pipeline on a background thread at boot so the first student is not
# the one who pays for it. See src/api/warmup.py.
ENV STUDENT_RAG_WARMUP_ON_STARTUP=true

CMD python -m uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT} --workers 1
