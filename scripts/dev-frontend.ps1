# 本地前端 Vite（/api 代理到 8000）
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..\frontend
if (-not (Test-Path .\node_modules)) {
  npm install
}
if (-not $env:VITE_PROXY_TARGET) {
  $env:VITE_PROXY_TARGET = "http://127.0.0.1:8000"
}
npm run dev
