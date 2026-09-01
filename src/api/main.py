from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import chat, chat_stream, health, metrics
from src.common.env_loader import load_project_env


API_VERSION = "0.1.0"

load_project_env()

import sys

if sys.stdout and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


app = FastAPI(
    title="Student Handbook RAG API",
    version=API_VERSION,
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
app.include_router(metrics.router)
app.include_router(chat.router)
app.include_router(chat_stream.router)


@app.get("/")
def root() -> dict[str, str]:
    """Trả về thông tin cơ bản về API.

    Khi người dùng truy cập đường dẫn gốc của API ("/"), hàm này sẽ được gọi
    và trả về một dictionary chứa các thông tin hữu ích về dịch vụ,
    như tên, phiên bản, và các đường dẫn đến tài liệu API hoặc kiểm tra sức khỏe.

    Returns:
        Một dictionary chứa các cặp khóa-giá trị mô tả dịch vụ:
        - 'service': Tên định danh của dịch vụ.
        - 'name': Tên đầy đủ của API.
        - 'version': Phiên bản hiện tại của API.
        - 'health': Đường dẫn để kiểm tra trạng thái sức khỏe của API.
        - 'docs': Đường dẫn đến tài liệu API (Swagger UI/Redoc).
    """
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
