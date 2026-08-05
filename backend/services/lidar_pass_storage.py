import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from config import settings


class AtomicLidarPassStorage:
    def __init__(self, base_dir: str = settings.LIDAR_PASS_DATA_PATH):
        self.base_dir = Path(base_dir)

    def save(self, session: dict, profiles: list[dict]) -> str:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        started = str(session["started_at"]).replace(":", "").replace("-", "")
        owner = session.get("trip_id") or session.get("session_key") or "pending"
        final_path = self.base_dir / f"lidar_pass_{owner}_{started}.json"
        payload = {"session": session, "profiles": profiles}

        temp_name = None
        try:
            with NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.base_dir,
                prefix=f".{final_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_name = temp_file.name
                json.dump(payload, temp_file, ensure_ascii=False, separators=(",", ":"))
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_name, final_path)
        except Exception:
            if temp_name:
                try:
                    Path(temp_name).unlink(missing_ok=True)
                except OSError:
                    pass
            raise

        return str(final_path)


lidar_pass_storage = AtomicLidarPassStorage()
