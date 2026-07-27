@echo off
setlocal EnableExtensions

set "TEMP_DIR=.hf_deploy_temp"
set "HF_SPACE_URL=https://huggingface.co/spaces/AnhFeee/hcmue-handbook-rag-api"
set "COMMIT_MSG=Deploy V25 FastAPI RAG backend"
set "ROOT_DIR=%CD%"
set "DRY_RUN=0"

if /I "%~1"=="--dry-run" set "DRY_RUN=1"

echo ==============================================
echo  Hugging Face Backend-Only Deployment
echo ==============================================
echo.

echo [1/5] Preparing clean package directory...
if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"
mkdir "%TEMP_DIR%"
if errorlevel 1 goto :error

echo [2/5] Copying backend source and configuration...
call :copy_dir "src" "%TEMP_DIR%\src"
if errorlevel 1 goto :error
call :copy_dir "configs" "%TEMP_DIR%\configs"
if errorlevel 1 goto :error
call :copy_file "Dockerfile" "%TEMP_DIR%\Dockerfile"
if errorlevel 1 goto :error
call :copy_file "requirements.txt" "%TEMP_DIR%\requirements.txt"
if errorlevel 1 goto :error
call :copy_file "requirements.lock" "%TEMP_DIR%\requirements.lock"
if errorlevel 1 goto :error
call :copy_file "runtime.txt" "%TEMP_DIR%\runtime.txt"
if errorlevel 1 goto :error
call :copy_file ".env.example" "%TEMP_DIR%\.env.example"
if errorlevel 1 goto :error
call :copy_file "LICENSE" "%TEMP_DIR%\LICENSE"
if errorlevel 1 goto :error

echo [3/5] Copying runtime data allowlist...
call :copy_dir "data\processed\tables" "%TEMP_DIR%\data\processed\tables"
if errorlevel 1 goto :error
call :copy_dir "data\processed\directories" "%TEMP_DIR%\data\processed\directories"
if errorlevel 1 goto :error
call :copy_dir "data\processed\entities" "%TEMP_DIR%\data\processed\entities"
if errorlevel 1 goto :error
call :copy_file "data\processed\graphs\document_edges.json" "%TEMP_DIR%\data\processed\graphs\document_edges.json"
if errorlevel 1 goto :error
call :copy_file "data\processed\chunks\all_docstore_items.json" "%TEMP_DIR%\data\processed\chunks\all_docstore_items.json"
if errorlevel 1 goto :error
call :copy_file "data\processed\chunks\v7_child_parent_chunks.json" "%TEMP_DIR%\data\processed\chunks\v7_child_parent_chunks.json"
if errorlevel 1 goto :error
call :copy_file "crawl_data\chuong_trinh_dao_tao.csv" "%TEMP_DIR%\crawl_data\chuong_trinh_dao_tao.csv"
if errorlevel 1 goto :error

echo [4/5] Writing Hugging Face Space metadata...
(
echo ---
echo title: HCMUE Handbook RAG API
echo colorFrom: blue
echo colorTo: green
echo sdk: docker
echo app_port: 7860
echo pinned: false
echo license: mit
echo ---
echo.
echo # HCMUE Handbook RAG API
echo.
echo Backend-only deployment for the HCMUE AI student handbook assistant.
echo.
echo Runtime: FastAPI, Qwen Router, BGE-M3, Qdrant, BM25, MongoDB, and Gemini 3.1 Flash-Lite.
echo.
echo Source repository: https://github.com/AnhPhiNe/student-handbook-rag-chatbot
) > "%TEMP_DIR%\README.md"
if errorlevel 1 goto :error

if "%DRY_RUN%"=="1" goto :dry_run_complete

echo [5/5] Committing and force-pushing the clean package...
pushd "%TEMP_DIR%"
if errorlevel 1 goto :error
git init
if errorlevel 1 goto :error_in_temp
git checkout -B main
if errorlevel 1 goto :error_in_temp
git config user.name "HCMUE RAG Deploy"
if errorlevel 1 goto :error_in_temp
git config user.email "deploy@example.local"
if errorlevel 1 goto :error_in_temp
git add .
if errorlevel 1 goto :error_in_temp
git commit -m "%COMMIT_MSG%"
if errorlevel 1 goto :error_in_temp
git remote add hf "%HF_SPACE_URL%"
if errorlevel 1 goto :error_in_temp
git push hf main:main --force
if errorlevel 1 goto :error_in_temp
popd

rmdir /s /q "%TEMP_DIR%"
echo.
echo ==============================================
echo  Deployment successful
echo ==============================================
exit /b 0

:dry_run_complete
echo [5/5] Dry run complete. No remote was modified.
echo Package directory: %ROOT_DIR%\%TEMP_DIR%
exit /b 0

:copy_dir
if not exist "%~1" (
    echo Missing required directory: %~1
    exit /b 1
)
robocopy "%~1" "%~2" /E /NFL /NDL /NJH /NJS /NP /XD __pycache__ .pytest_cache .ruff_cache cache reports /XF *.pyc *.lock
if %ERRORLEVEL% GEQ 8 exit /b 1
exit /b 0

:copy_file
if not exist "%~1" (
    echo Missing required file: %~1
    exit /b 1
)
for %%D in ("%~2") do if not exist "%%~dpD" mkdir "%%~dpD"
copy /Y "%~1" "%~2" >nul
if errorlevel 1 exit /b 1
exit /b 0

:error_in_temp
popd

:error
echo.
echo ==============================================
echo  Deployment failed. No cleanup was performed.
echo ==============================================
cd /d "%ROOT_DIR%" 2>nul
exit /b 1
