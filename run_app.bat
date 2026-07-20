@echo off
echo ==============================================
echo KHOI DONG HE THONG HCMUE RAG CHATBOT
echo ==============================================

REM Kích hoạt môi trường ảo (nếu có)
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

echo [1] Dang khoi dong Backend FastAPI...
start "Backend API" cmd /c "uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload"

echo [2] Dang khoi dong Frontend Vite...
cd frontend
if not exist "node_modules" (
    echo Dang cai dat npm packages cho frontend...
    call npm install
)
start "Frontend UI" cmd /c "npm run dev"

echo ==============================================
echo He thong dang chay!
echo - API Backend: http://localhost:8000
echo - Frontend UI: http://localhost:5173
echo ==============================================
pause
