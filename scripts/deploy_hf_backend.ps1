param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$TempDir = Join-Path $RootDir ".hf_deploy_temp"
$HfSpaceUrl = "https://huggingface.co/spaces/AnhFeee/hcmue-handbook-rag-api"
$CommitMessage = "Deploy v43 conditional answer behavior"

function Assert-InWorkspace {
    param([string]$Path)
    $resolvedRoot = (Resolve-Path -LiteralPath $RootDir).Path
    $resolvedPath = if (Test-Path -LiteralPath $Path) {
        (Resolve-Path -LiteralPath $Path).Path
    } else {
        [System.IO.Path]::GetFullPath($Path)
    }
    if (-not $resolvedPath.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate outside workspace: $resolvedPath"
    }
}

function Copy-RequiredFile {
    param(
        [string]$Source,
        [string]$Destination
    )
    $sourcePath = Join-Path $RootDir $Source
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "Missing required file: $Source"
    }
    $destPath = Join-Path $TempDir $Destination
    $destParent = Split-Path -Parent $destPath
    if (-not (Test-Path -LiteralPath $destParent)) {
        New-Item -ItemType Directory -Path $destParent | Out-Null
    }
    Copy-Item -LiteralPath $sourcePath -Destination $destPath -Force
}

function Copy-RequiredJsonArtifact {
    param(
        [string]$Source,
        [string]$Destination
    )
    $sourcePath = Join-Path $RootDir $Source
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "Missing required runtime artifact: $Source"
    }
    $raw = Get-Content -Raw -LiteralPath $sourcePath
    if ([string]::IsNullOrWhiteSpace($raw)) {
        throw "Runtime artifact is empty: $Source"
    }
    try {
        $parsed = $raw | ConvertFrom-Json
    }
    catch {
        throw "Runtime artifact is not valid JSON: $Source"
    }
    $isEmptyArray = $parsed -is [array] -and $parsed.Count -eq 0
    $isEmptyObject = -not ($parsed -is [array]) -and $parsed.PSObject.Properties.Count -eq 0
    if ($isEmptyArray -or $isEmptyObject) {
        throw "Runtime artifact must not be [] or {}: $Source"
    }
    Copy-RequiredFile $Source $Destination
}

function Copy-RequiredDirectory {
    param(
        [string]$Source,
        [string]$Destination
    )
    $sourcePath = Join-Path $RootDir $Source
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Container)) {
        throw "Missing required directory: $Source"
    }
    $destPath = Join-Path $TempDir $Destination
    if (-not (Test-Path -LiteralPath $destPath)) {
        New-Item -ItemType Directory -Path $destPath | Out-Null
    }
    & robocopy $sourcePath $destPath /E /NFL /NDL /NJH /NJS /NP /XD __pycache__ .pytest_cache .ruff_cache cache reports /XF *.pyc *.lock | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "Failed to copy directory: $Source"
    }
}

function Invoke-Git {
    param([string[]]$GitArgs)
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') failed with exit code $LASTEXITCODE"
    }
}

Write-Host "=============================================="
Write-Host " Hugging Face Backend-Only Deployment"
Write-Host "=============================================="
Write-Host ""

Write-Host "[1/5] Preparing history-preserving package directory..."
Assert-InWorkspace $TempDir
if (Test-Path -LiteralPath $TempDir) {
    Remove-Item -LiteralPath $TempDir -Recurse -Force
}
if ($DryRun) {
    New-Item -ItemType Directory -Path $TempDir | Out-Null
}
else {
    Invoke-Git @("clone", "--branch", "main", "--single-branch", $HfSpaceUrl, $TempDir)
    Get-ChildItem -LiteralPath $TempDir -Force |
        Where-Object { $_.Name -ne ".git" } |
        Remove-Item -Recurse -Force
}

Write-Host "[2/5] Copying backend source and configuration..."
Copy-RequiredDirectory "src" "src"
Copy-RequiredDirectory "configs" "configs"
Copy-RequiredFile "Dockerfile" "Dockerfile"
Copy-RequiredFile "requirements.txt" "requirements.txt"
Copy-RequiredFile "requirements.lock" "requirements.lock"
Copy-RequiredFile "runtime.txt" "runtime.txt"
Copy-RequiredFile ".env.example" ".env.example"
Copy-RequiredFile "LICENSE" "LICENSE"

Write-Host "[3/5] Copying runtime data allowlist..."
Copy-RequiredDirectory "data\processed\tables" "data\processed\tables"
Copy-RequiredDirectory "data\processed\directories" "data\processed\directories"
Copy-RequiredDirectory "data\processed\entities" "data\processed\entities"
Copy-RequiredDirectory "data\processed\graphs" "data\processed\graphs"
Copy-RequiredJsonArtifact "data\processed\amendments\amendments.json" "data\processed\amendments\amendments.json"
Copy-RequiredJsonArtifact "data\processed\chunks\all_docstore_items.json" "data\processed\chunks\all_docstore_items.json"
Copy-RequiredJsonArtifact "data\processed\chunks\child_parent_chunks.json" "data\processed\chunks\child_parent_chunks.json"
Copy-RequiredJsonArtifact "data\processed\metadata\build_manifest.json" "data\processed\metadata\build_manifest.json"

$packagedManifestPath = Join-Path $TempDir "data\processed\metadata\build_manifest.json"
$packagedManifest = Get-Content -Raw -LiteralPath $packagedManifestPath | ConvertFrom-Json
if ($packagedManifest.storage_targets.qdrant_collection -ne "student_handbook_semantic_v31") {
    throw "Unexpected Qdrant target in packaged build manifest: $($packagedManifest.storage_targets.qdrant_collection)"
}
if ($packagedManifest.storage_targets.mongo_parent_collection -ne "parent_docs_v31") {
    throw "Unexpected Mongo target in packaged build manifest: $($packagedManifest.storage_targets.mongo_parent_collection)"
}

Write-Host "[4/5] Writing Hugging Face Space metadata..."
@"
---
title: HCMUE Handbook RAG API
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# HCMUE Handbook RAG API

Backend-only deployment for the HCMUE AI student handbook assistant.

Runtime: FastAPI, Qwen Router, BGE-M3, Qdrant, BM25, MongoDB, and Gemini 3.1 Flash-Lite.

Source repository: https://github.com/AnhPhiNe/student-handbook-rag-chatbot
"@ | Set-Content -LiteralPath (Join-Path $TempDir "README.md") -Encoding utf8

if ($DryRun) {
    Write-Host "[5/5] Dry run complete. No remote was modified."
    Write-Host "Package directory: $TempDir"
    exit 0
}

Write-Host "[5/5] Committing and pushing the clean package..."
Push-Location $TempDir
try {
    Invoke-Git @("config", "user.name", "HCMUE RAG Deploy")
    Invoke-Git @("config", "user.email", "deploy@example.local")
    Invoke-Git @("add", ".")
    & git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "No Hugging Face package changes to deploy."
    }
    elseif ($LASTEXITCODE -eq 1) {
        Invoke-Git @("commit", "-m", $CommitMessage)
        Invoke-Git @("push", "origin", "main:main")
    }
    else {
        throw "git diff --cached --quiet failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

if (Test-Path -LiteralPath $TempDir) {
    Remove-Item -LiteralPath $TempDir -Recurse -Force
}

Write-Host ""
Write-Host "=============================================="
Write-Host " Deployment successful"
Write-Host "=============================================="
