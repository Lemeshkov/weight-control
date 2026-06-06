# stop.ps1
Write-Host "🛑 Остановка Weight Control System" -ForegroundColor Cyan

# Остановка Python процессов
Get-Process -Name "python" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process -Name "node" -ErrorAction SilentlyContinue | Stop-Process -Force

# Остановка Docker контейнера
docker-compose down

Write-Host "✅ Система остановлена" -ForegroundColor Green