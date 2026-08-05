import logging
from copy import deepcopy
from threading import RLock
from typing import Optional, Protocol

from database import SessionLocal, engine
from sqlalchemy import inspect


logger = logging.getLogger(__name__)


class LidarSessionRepository(Protocol):
    def is_available(self) -> bool: ...
    def create(self, values: dict) -> Optional[int]: ...
    def update(self, session_id: Optional[int], values: dict) -> None: ...


class InMemoryLidarSessionRepository:
    def __init__(self):
        self._items: dict[int, dict] = {}
        self._next_id = 1
        self._lock = RLock()

    def is_available(self) -> bool:
        return True

    def create(self, values: dict) -> int:
        with self._lock:
            session_id = self._next_id
            self._next_id += 1
            self._items[session_id] = {"id": session_id, **deepcopy(values)}
            return session_id

    def update(self, session_id: Optional[int], values: dict) -> None:
        if session_id is None:
            return
        with self._lock:
            if session_id in self._items:
                self._items[session_id].update(deepcopy(values))

    def get(self, session_id: int) -> Optional[dict]:
        with self._lock:
            item = self._items.get(session_id)
            return deepcopy(item) if item else None


class SqlAlchemyLidarSessionRepository:
    """Metadata repository. Missing migration is reported to the coordinator."""

    def is_available(self) -> bool:
        return inspect(engine).has_table("lidar_pass_sessions")

    def create(self, values: dict) -> int:
        from models import LidarPassSession

        db = SessionLocal()
        try:
            record = LidarPassSession(**values)
            db.add(record)
            db.commit()
            db.refresh(record)
            return record.id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def update(self, session_id: Optional[int], values: dict) -> None:
        if session_id is None:
            return
        from models import LidarPassSession

        db = SessionLocal()
        try:
            record = db.query(LidarPassSession).filter(LidarPassSession.id == session_id).first()
            if record is None:
                raise LookupError(f"Lidar pass session {session_id} not found")
            for key, value in values.items():
                setattr(record, key, value)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
