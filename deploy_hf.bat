@echo off
setlocal EnableExtensions

echo ==============================================
echo  Hugging Face Space Clean Deployment Script
echo ==============================================
echo.

set TEMP_DIR=.hf_deploy_temp
set HF_SPACE_URL=https://huggingface.co/spaces/AnhFeee/hcmue-handbook-rag-api
set COMMIT_MSG=Deploy FastAPI RAG backend
set ROOT_DIR=%CD%

echo [1/5] Cleaning up old temp directory...
if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"
mkdir "%TEMP_DIR%"
if errorlevel 1 goto :error
set XCOPY_EXCLUDE=%TEMP_DIR%\xcopy_exclude.txt
> "%XCOPY_EXCLUDE%" (
echo \__pycache__\
echo .pyc
echo .pytest_cache
echo .ruff_cache
echo \cache\
echo .lock
)
if errorlevel 1 goto :error

echo [2/5] Copying essential backend files...
xcopy /s /i /y /exclude:"%XCOPY_EXCLUDE%" src "%TEMP_DIR%\src"
if errorlevel 1 goto :error
xcopy /s /i /y /exclude:"%XCOPY_EXCLUDE%" configs "%TEMP_DIR%\configs"
if errorlevel 1 goto :error
xcopy /y Dockerfile "%TEMP_DIR%\"
if errorlevel 1 goto :error
xcopy /y requirements.txt "%TEMP_DIR%\"
if errorlevel 1 goto :error
xcopy /y requirements.lock "%TEMP_DIR%\"
if errorlevel 1 goto :error
xcopy /y runtime.txt "%TEMP_DIR%\"
if errorlevel 1 goto :error
xcopy /y .env.example "%TEMP_DIR%\"
if errorlevel 1 goto :error

echo [3/5] Copying JSON data (excluding binary vector databases)...
mkdir "%TEMP_DIR%\data"
if errorlevel 1 goto :error
xcopy /s /i /y /exclude:"%XCOPY_EXCLUDE%" data\processed "%TEMP_DIR%\data\processed"
if errorlevel 1 goto :error
xcopy /s /i /y /exclude:"%XCOPY_EXCLUDE%" data\eval "%TEMP_DIR%\data\eval"
if errorlevel 1 goto :error

echo [4/5] Preparing Hugging Face configuration...
copy /y deploy\huggingface\backend\README.md "%TEMP_DIR%\README.md"
if errorlevel 1 goto :error

echo [5/5] Initializing clean Git repository and pushing...
cd "%TEMP_DIR%"
if errorlevel 1 goto :error
git init
if errorlevel 1 goto :error
git checkout -B main
if errorlevel 1 goto :error
git config user.name "HCMUE RAG Deploy"
if errorlevel 1 goto :error
git config user.email "deploy@example.local"
if errorlevel 1 goto :error
git add .
if errorlevel 1 goto :error
git commit -m "%COMMIT_MSG%"
if errorlevel 1 goto :error
git remote add hf "%HF_SPACE_URL%"
if errorlevel 1 goto :error
git push hf main:main --force
if errorlevel 1 goto :error

cd ..
rmdir /s /q "%TEMP_DIR%"

echo.
echo ==============================================
echo  Deployment Successful!
echo ==============================================
exit /b 0

:error
echo.
echo ==============================================
echo  Deployment failed. Check the error above.
echo ==============================================
echo If the push failed with authentication, create a Hugging Face Write token
echo and use it as the password when Git prompts for credentials.
cd /d "%ROOT_DIR%" 2>nul
exit /b 1
