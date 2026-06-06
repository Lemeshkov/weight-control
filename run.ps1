# run.ps1
Write-Host "🚀 Запуск Weight Control System" -ForegroundColor Cyan

# Проверка Docker
$dockerCheck = docker --version 2>$null
if (-not $dockerCheck) {
    Write-Host "❌ Docker не установлен. Установите Docker Desktop для Windows" -ForegroundColor Red
    exit 1
}

# Проверка Python
$pythonCheck = python --version 2>$null
if (-not $pythonCheck) {
    Write-Host "❌ Python не установлен" -ForegroundColor Red
    exit 1
}

# Проверка Node.js
$nodeCheck = node --version 2>$null
if (-not $nodeCheck) {
    Write-Host "❌ Node.js не установлен" -ForegroundColor Red
    exit 1
}

# Запуск PostgreSQL через Docker
Write-Host "🐘 Запуск PostgreSQL..." -ForegroundColor Yellow
docker-compose up -d

# Ожидание готовности PostgreSQL
Write-Host "⏳ Ожидание готовности PostgreSQL..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Установка зависимостей backend
Write-Host "🐍 Установка зависимостей backend..." -ForegroundColor Yellow
cd backend
pip install -r requirements.txt

# Запуск backend в фоне
Write-Host "🚀 Запуск backend сервера..." -ForegroundColor Yellow
$backendProcess = Start-Process -NoNewWindow -PassThru powershell -ArgumentList "-Command uvicorn app.main:app --reload --port 8000"

# Установка зависимостей frontend
Write-Host "⚛️ Установка зависимостей frontend..." -ForegroundColor Yellow
cd ../frontend
npm install

# Запуск frontend в фоне
Write-Host "🎨 Запуск frontend сервера..." -ForegroundColor Yellow
$frontendProcess = Start-Process -NoNewWindow -PassThru powershell -ArgumentList "-Command npm run dev"

Write-Host ""
Write-Host "✅ Система запущена!" -ForegroundColor Green
Write-Host "   Backend: http://localhost:8000" -ForegroundColor Cyan
Write-Host "   Frontend: http://localhost:5173" -ForegroundColor Cyan
Write-Host "   API Docs: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "Для остановки выполните: .\stop.ps1" -ForegroundColor Yellow

# Ждем нажатия клавиши
Read-Host "Нажмите Enter для остановки"

# Остановка процессов
Stop-Process -Id $backendProcess.Id -Force 2>$null
Stop-Process -Id $frontendProcess.Id -Force 2>$null
docker-compose down