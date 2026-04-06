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
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:$LlamaPort/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
    if ($resp.StatusCode -eq 200) { $LlamaRunning = $true }
} catch {}
$ErrorActionPreference = $prevEAP

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

    # Context size: use BONSAI_CTX or default to 8192 for fast startup
    $CtxSize = if ($env:BONSAI_CTX) { $env:BONSAI_CTX } else { "8192" }

    Write-Host "==> Starting llama-server (port $LlamaPort, context $CtxSize) ..." -ForegroundColor Cyan
    $LlamaProc = Start-Process -FilePath $LlamaServer -ArgumentList @(
        "-m", $ModelFile.FullName,
        "--host", "127.0.0.1",
        "--port", $LlamaPort,
        "-ngl", "99",
        "-c", $CtxSize,
        "--temp", "0.5",
        "--top-p", "0.85",
        "--top-k", "20",
        "--min-p", "0",
        "--reasoning-budget", "0",
        "--reasoning-format", "none",
        "--chat-template-kwargs", '{"enable_thinking": false}'
    ) -PassThru -WindowStyle Minimized

    # Wait for server to be ready (up to 120 seconds — model loading can be slow)
    Write-Host "    Waiting for llama-server to be ready (this may take a minute) ..." -ForegroundColor Cyan
    $ready = $false
    for ($i = 0; $i -lt 120; $i++) {
        # Check if process has exited (crashed)
        if ($LlamaProc.HasExited) {
            Write-Host "[ERR] llama-server process exited with code $($LlamaProc.ExitCode)." -ForegroundColor Red
            exit 1
        }
        Start-Sleep -Seconds 1
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:$LlamaPort/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
            if ($resp.StatusCode -eq 200) { $ready = $true; break }
        } catch {}
        # Print progress every 15 seconds
        if ($i -gt 0 -and $i % 15 -eq 0) {
            Write-Host "    Still loading... ($i seconds)" -ForegroundColor Yellow
        }
    }
    if (-not $ready) {
        Write-Host "[ERR] llama-server failed to start within 120 seconds." -ForegroundColor Red
        Write-Host "      Try: `$env:BONSAI_CTX = '4096'; .\scripts\start_chat.ps1  (smaller context = faster startup)" -ForegroundColor Yellow
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
