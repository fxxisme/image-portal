# 可选：本地一键说明见 README。本脚本仅启动后端（需已创建 .venv）
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..\backend
if (-not (Test-Path .\.venv\Scripts\Activate.ps1)) {
  Write-Error "先: python -m venv .venv && .\.venv\Scripts\Activate.ps1 && pip install -r requirements.txt"
}
$env:DATABASE_URL = if ($env:DATABASE_URL) { $env:DATABASE_URL } else { "sqlite:///./portal.db" }
$env:MEDIA_DIR = if ($env:MEDIA_DIR) { $env:MEDIA_DIR } else { "./media" }
$env:ADMIN_PASSWORD = if ($env:ADMIN_PASSWORD) { $env:ADMIN_PASSWORD } else { "admin" }
$env:JWT_SECRET = if ($env:JWT_SECRET) { $env:JWT_SECRET } else { "dev-secret" }
Remove-Item Env:STATIC_DIR -ErrorAction SilentlyContinue
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
