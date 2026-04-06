# Bonsai Chat — Launch script for Windows
# Usage: .\scripts\start_chat.ps1
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DemoDir = Split-Path -Parent $ScriptDir
$VenvPy = Join-Path $DemoDir ".venv\Scripts\python.exe"
$BonsaiModel = if ($env:BONSAI_MODEL) { $env:BONSAI_MODEL } else { "8B" }
$LlamaPort = if ($env:LLAMA_PORT) { $env:LLAMA_PORT } else { "8080" }
$ChatPort = if ($env:CHAT_PORT) { $env:CHAT_PORT } else { "9090" }

Write-Host ""
Write-Host "========================================="
Write-Host "   Bonsai Chat"
Write-Host "   Model: $BonsaiModel"
Write-Host "========================================="
Write-Host ""

# ── Check venv exists ──
if (-not (Test-Path $VenvPy)) {
    Write-Host "[ERR] Python venv not found. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

# ── Install chat dependencies if needed ──
$HasFastAPI = & $VenvPy -c "import fastapi" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "==> Installing chat dependencies ..." -ForegroundColor Cyan
    & (Join-Path $DemoDir ".venv\Scripts\pip.exe") install -e ".[chat]" --quiet
    Write-Host "[OK] Dependencies installed." -ForegroundColor Green
}

# ── Check if llama-server is already running ──
$LlamaRunning = $false
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:$LlamaPort/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
    if ($resp.StatusCode -eq 200) { $LlamaRunning = $true }
} catch {}

if ($LlamaRunning) {
    Write-Host "[OK] llama-server already running on port $LlamaPort" -ForegroundColor Green
} else {
    # Find model file
    $ModelDir = Join-Path $DemoDir "models\gguf\$BonsaiModel"
    $ModelFile = Get-ChildItem -Path $ModelDir -Filter "*.gguf" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $ModelFile) {
        Write-Host "[ERR] No .gguf model found in $ModelDir. Run .\setup.ps1 first." -ForegroundColor Red
        exit 1
    }

    # Find llama-server binary
    $LlamaServer = Join-Path $DemoDir "bin\cuda\llama-server.exe"
    if (-not (Test-Path $LlamaServer)) {
        Write-Host "[ERR] llama-server.exe not found. Run .\setup.ps1 first." -ForegroundColor Red
        exit 1
    }

    Write-Host "==> Starting llama-server (port $LlamaPort) ..." -ForegroundColor Cyan
    $LlamaProc = Start-Process -FilePath $LlamaServer -ArgumentList @(
        "-m", $ModelFile.FullName,
        "--host", "127.0.0.1",
        "--port", $LlamaPort,
        "-ngl", "99",
        "-c", "0",
        "--temp", "0.5",
        "--top-p", "0.85",
        "--top-k", "20",
        "--min-p", "0",
        "--reasoning-budget", "0",
        "--reasoning-format", "none",
        "--chat-template-kwargs", '{"enable_thinking": false}'
    ) -PassThru -WindowStyle Minimized

    # Wait for server to be ready
    Write-Host "    Waiting for llama-server to be ready ..." -ForegroundColor Cyan
    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:$LlamaPort/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
            if ($resp.StatusCode -eq 200) { $ready = $true; break }
        } catch {}
    }
    if (-not $ready) {
        Write-Host "[ERR] llama-server failed to start within 60 seconds." -ForegroundColor Red
        exit 1
    }
    Write-Host "[OK] llama-server ready." -ForegroundColor Green
}

# ── Start Bonsai Chat ──
Write-Host "==> Starting Bonsai Chat (port $ChatPort) ..." -ForegroundColor Cyan
Write-Host ""
Write-Host "  Open http://localhost:$ChatPort in your browser to chat." -ForegroundColor Green
Write-Host "  Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""

$env:LLAMA_PORT = $LlamaPort
$env:CHAT_PORT = $ChatPort
$env:BONSAI_MODEL = $BonsaiModel

& $VenvPy -m uvicorn chat.app:app --host 127.0.0.1 --port $ChatPort
