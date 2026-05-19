from __future__ import annotations

from fastapi import FastAPI

from src.api.routes import chat, health
from src.common.env_loader import load_project_env


API_VERSION = "0.1.0"

load_project_env()

app = FastAPI(
    title="Student Handbook RAG API",
    version=API_VERSION,
)

app.include_router(health.router)
app.include_router(chat.router)


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
