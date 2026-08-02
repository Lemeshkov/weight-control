from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Register shared SQLAlchemy metadata without initializing hardware clients.
import models  # noqa: F401
from routers.laboratory import router as laboratory_router


app = FastAPI(
    title="Weight Control — Laboratory",
    version="1.0.0",
    description="Independent API for coal laboratory experiments",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(laboratory_router)


@app.get("/api/health", tags=["health"])
async def health_check():
    return {
        "status": "ok",
        "service": "laboratory",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
