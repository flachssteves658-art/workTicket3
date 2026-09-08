$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
  Write-Host "未发现 .env，已从 .env.example 创建。请先填写 LLM_API_KEY。" -ForegroundColor Yellow
  Copy-Item ".env.example" ".env"
}

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

python -X utf8 -m uvicorn app.main:app --host 127.0.0.1 --port 8880 --reload
