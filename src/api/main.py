from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import chat, chat_stream, health
from src.common.env_loader import load_project_env


API_VERSION = "0.1.0"

load_project_env()

import sys

if sys.stdout and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 [FastAPI] Preloading heavy models to prevent Cold Start...")
    from src.api.deps import get_answer_service
    from src.retrieval.core.bm25_retriever import get_bm25_retriever
    from src.retrieval.core.cross_encoder_reranker import get_local_reranker
    
    # Kích hoạt Singleton ngay từ lúc server khởi động
    get_answer_service()
    get_bm25_retriever()
    get_local_reranker()
    print("✅ [FastAPI] All models preloaded successfully!")
    yield

app = FastAPI(
    title="Student Handbook RAG API",
    version=API_VERSION,
    lifespan=lifespan,
)

cors_origins = [
    origin.strip()
    for origin in os.getenv("STUDENT_RAG_CORS_ORIGINS", "").split(",")
    if origin.strip()
]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(chat_stream.router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "student_handbook_rag",
        "name": "Student Handbook RAG API",
        "version": API_VERSION,
        "health": "/health",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api.main:app", host="127.0.0.1", port=8000, reload=True)
