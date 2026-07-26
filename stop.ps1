$ErrorActionPreference = "Continue"
$projectRoot = $PSScriptRoot
$pidFile = Join-Path $projectRoot ".weight-control-processes.json"

if (Test-Path $pidFile) {
    $processes = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    foreach ($processId in @($processes.backend, $processes.frontend)) {
        if ($processId) {
            Stop-Process -Id $processId -ErrorAction SilentlyContinue
        }
    }
    Remove-Item -LiteralPath $pidFile -ErrorAction SilentlyContinue
} else {
    Write-Warning "PID-файл не найден; посторонние Python/Node процессы не затронуты."
}

docker compose -f (Join-Path $projectRoot "docker-compose.yml") down
Write-Host "Weight Control System остановлена" -ForegroundColor Green