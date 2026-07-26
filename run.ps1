$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"
$requirements = Join-Path $projectRoot "requirements.txt"
$pidFile = Join-Path $projectRoot ".weight-control-processes.json"
$venvPython = Join-Path $projectRoot "venv_weight\Scripts\python.exe"
$pythonExe = if (Test-Path $venvPython) { $venvPython } else { "python" }

Write-Host "Запуск Weight Control System" -ForegroundColor Cyan

docker compose -f (Join-Path $projectRoot "docker-compose.yml") up -d
& $pythonExe -m pip install -r $requirements
Push-Location $backendDir
try {
    & $pythonExe -m alembic -c alembic.ini upgrade head
} finally {
    Pop-Location
}

$backendProcess = Start-Process -FilePath $pythonExe -ArgumentList @("-m", "uvicorn", "main:app", "--reload", "--port", "8000") -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru
npm --prefix $frontendDir install
$frontendProcess = Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev") -WorkingDirectory $frontendDir -WindowStyle Hidden -PassThru

@{
    backend = $backendProcess.Id
    frontend = $frontendProcess.Id
} | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding UTF8

Write-Host "Backend: http://localhost:8000" -ForegroundColor Green
Write-Host "Frontend: http://localhost:5173" -ForegroundColor Green
Write-Host "PID-файл: $pidFile"
Read-Host "Нажмите Enter для остановки"
& (Join-Path $projectRoot "stop.ps1")