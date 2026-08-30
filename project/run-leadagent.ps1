$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $RootDir "backend"
$FrontendDir = Join-Path $RootDir "frontend"
$VenvDir = Join-Path $RootDir ".venv"
$Python = Join-Path $VenvDir "Scripts\python.exe"

New-Item -ItemType Directory -Force -Path (Join-Path $BackendDir "data") | Out-Null

if (-not (Test-Path $VenvDir)) {
    python -m venv $VenvDir
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $RootDir "requirements.txt")

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Push-Location $FrontendDir
    npm install
    Pop-Location
}

Write-Host "Starting LeadAgent PRO..."
Write-Host "Backend:  http://localhost:8000"
Write-Host "Frontend: http://localhost:3000"
Write-Host "If you need Ollama for message generation, open another terminal and run: ollama serve"

$backendProc = Start-Process -FilePath $Python -ArgumentList "main.py" -WorkingDirectory $BackendDir -PassThru
$frontendProc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c npm run dev" -WorkingDirectory $FrontendDir -PassThru

try {
    Wait-Process -Id $backendProc.Id, $frontendProc.Id
}
finally {
    if (-not $backendProc.HasExited) {
        Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
    }
    if (-not $frontendProc.HasExited) {
        Stop-Process -Id $frontendProc.Id -Force -ErrorAction SilentlyContinue
    }
}
