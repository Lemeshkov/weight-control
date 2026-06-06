# start.ps1 - Простая версия
Write-Host "Creating project..." -ForegroundColor Yellow

# Создание папок
New-Item -ItemType Directory -Force -Path "backend\app\routers" | Out-Null
New-Item -ItemType Directory -Force -Path "backend\app\utils" | Out-Null
New-Item -ItemType Directory -Force -Path "frontend\src\components" | Out-Null

# backend requirements.txt
@'
fastapi==0.104.1
uvicorn[standard]==0.24.0
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
pydantic==2.5.0
python-dotenv==1.0.0
websockets==12.0
python-multipart==0.0.6
numpy==1.24.3
'@ | Out-File -FilePath "backend\requirements.txt" -Encoding utf8

# backend .env
@'
DATABASE_URL=postgresql://weight_user:weight_pass@localhost:5432/weight_control
UNISERVER_URL=http://localhost:8123/core/SendMsg
UNISERVER_USER=user
UNISERVER_PASSWORD=pass
'@ | Out-File -FilePath "backend\.env" -Encoding utf8

# backend/app/main.py
@'
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Weight Control System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

@app.get("/api/weight/current")
async def get_current_weight():
    return {"weight": 0, "unit": "kg", "stable": False}

@app.post("/api/weighing/start")
async def start_weighing():
    return {"status": "started"}
'@ | Out-File -FilePath "backend\app\main.py" -Encoding utf8

# backend/app/database.py
@'
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://weight_user:weight_pass@localhost:5432/weight_control")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
'@ | Out-File -FilePath "backend\app\database.py" -Encoding utf8

# backend/app/models.py
@'
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.sql import func
from app.database import Base

class Weighing(Base):
    __tablename__ = "weighings"
    
    id = Column(Integer, primary_key=True, index=True)
    plate_number = Column(String(20), index=True)
    direction = Column(String(10))
    weight = Column(Float)
    volume = Column(Float, nullable=True)
    photo_path = Column(String(255), nullable=True)
    is_unloaded = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
'@ | Out-File -FilePath "backend\app\models.py" -Encoding utf8

# __init__.py
New-Item -ItemType File -Force -Path "backend\app\__init__.py" | Out-Null
New-Item -ItemType File -Force -Path "backend\app\routers\__init__.py" | Out-Null
New-Item -ItemType File -Force -Path "backend\app\utils\__init__.py" | Out-Null

# frontend package.json
@'
{
  "name": "weight-control-frontend",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "axios": "^1.6.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.0.0",
    "vite": "^4.4.5"
  }
}
'@ | Out-File -FilePath "frontend\package.json" -Encoding utf8

# frontend vite.config.js
@'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true
      }
    }
  }
})
'@ | Out-File -FilePath "frontend\vite.config.js" -Encoding utf8

# frontend index.html
@'
<!DOCTYPE html>
<html lang="ru">
  <head>
    <meta charset="UTF-8" />
    <title>Weight Control</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
'@ | Out-File -FilePath "frontend\index.html" -Encoding utf8

# frontend/src/main.jsx
New-Item -ItemType Directory -Force -Path "frontend\src" | Out-Null
@'
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
'@ | Out-File -FilePath "frontend\src\main.jsx" -Encoding utf8

# frontend/src/App.jsx
@'
import React, { useState, useEffect } from 'react'
import axios from 'axios'

function App() {
  const [health, setHealth] = useState(null)
  const [weight, setWeight] = useState(0)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    axios.get('/api/health').then(res => setHealth(res.data))
    axios.get('/api/weight/current').then(res => setWeight(res.data.weight))
  }, [])

  const startWeighing = async () => {
    setLoading(true)
    await axios.post('/api/weighing/start')
    alert('Взвешивание начато')
    setLoading(false)
  }

  return (
    <div style={{ padding: 20 }}>
      <h1>Weight Control System</h1>
      <p>Статус: {health?.status || '...'}</p>
      <p>Текущий вес: {weight} кг</p>
      <button onClick={startWeighing} disabled={loading}>
        {loading ? 'Загрузка...' : 'Начать взвешивание'}
      </button>
    </div>
  )
}

export default App
'@ | Out-File -FilePath "frontend\src\App.jsx" -Encoding utf8

# docker-compose.yml
@'
version: '3.8'
services:
  postgres:
    image: postgres:15
    container_name: weight_control_db
    environment:
      POSTGRES_USER: weight_user
      POSTGRES_PASSWORD: weight_pass
      POSTGRES_DB: weight_control
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped
volumes:
  postgres_data:
'@ | Out-File -FilePath "docker-compose.yml" -Encoding utf8

Write-Host "✅ Project created successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. .\venv_weight\Scripts\Activate.ps1"
Write-Host "2. cd backend && pip install -r requirements.txt"
Write-Host "3. cd ../frontend && npm install"
Write-Host "4. docker-compose up -d"
Write-Host "5. uvicorn app.main:app --reload --port 8000"
Write-Host "6. cd frontend && npm run dev"