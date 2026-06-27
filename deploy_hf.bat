@echo off
echo ==============================================
echo  Hugging Face Space Clean Deployment Script
echo ==============================================
echo.

set TEMP_DIR=.hf_deploy_temp

echo [1/5] Cleaning up old temp directory...
if exist %TEMP_DIR% rmdir /s /q %TEMP_DIR%
mkdir %TEMP_DIR%

echo [2/5] Copying essential backend files...
xcopy /s /i /y src %TEMP_DIR%\src >nul
xcopy /s /i /y configs %TEMP_DIR%\configs >nul
xcopy /y Dockerfile %TEMP_DIR%\ >nul
xcopy /y requirements.txt %TEMP_DIR%\ >nul
xcopy /y requirements.lock %TEMP_DIR%\ >nul
xcopy /y runtime.txt %TEMP_DIR%\ >nul
xcopy /y .env.example %TEMP_DIR%\ >nul

echo [3/5] Copying JSON data (excluding binary vector databases)...
mkdir %TEMP_DIR%\data >nul
xcopy /s /i /y data\processed %TEMP_DIR%\data\processed >nul
xcopy /s /i /y data\eval %TEMP_DIR%\data\eval >nul

echo [4/5] Preparing Hugging Face configuration...
> %TEMP_DIR%\README.md echo ---
>> %TEMP_DIR%\README.md echo title: HCMUE Student Handbook RAG
>> %TEMP_DIR%\README.md echo emoji: 🎓
>> %TEMP_DIR%\README.md echo colorFrom: blue
>> %TEMP_DIR%\README.md echo colorTo: indigo
>> %TEMP_DIR%\README.md echo sdk: docker
>> %TEMP_DIR%\README.md echo python_version: "3.11"
>> %TEMP_DIR%\README.md echo app_port: 7860
>> %TEMP_DIR%\README.md echo pinned: false
>> %TEMP_DIR%\README.md echo ---
type README.md >> %TEMP_DIR%\README.md

echo [5/5] Initializing clean Git repository and Pushing...
cd %TEMP_DIR%
git init >nul
git add . >nul
git commit -m "Deploy Clean Backend to Hugging Face" >nul
git remote add hf https://huggingface.co/spaces/AnhFeee/hcmue-handbook-rag-api
git push hf master:main --force

cd ..
rmdir /s /q %TEMP_DIR%

echo.
echo ==============================================
echo  Deployment Successful!
echo ==============================================
