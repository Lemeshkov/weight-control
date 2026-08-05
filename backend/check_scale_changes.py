"""Read-only long-running diagnostics for UniServer AUTO scale parameters."""

import argparse
import asyncio
import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx

from config import settings
from services.uniserver_client import uniserver_client


CSV_FIELDS = [
    "timestamp",
    "event",
    "massa",
    "delta_kg",
    "stabil",
    "state",
    "state_name",
    "enable",
    "rx_packet",
    "unit_meas",
    "error",
]
SCALE_ENDPOINT = "/core/plugins/AutoScale1/Parameters"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Log UniServer scale changes without sending commands."
    )
    parser.add_argument("--interval-ms", type=int, default=500)
    parser.add_argument("--min-delta-kg", type=float, default=10)
    parser.add_argument("--heartbeat-seconds", type=float, default=300)
    args = parser.parse_args()

    if args.interval_ms <= 0:
        parser.error("--interval-ms must be greater than zero")
    if args.min_delta_kg < 0:
        parser.error("--min-delta-kg must not be negative")
    if args.heartbeat_seconds <= 0:
        parser.error("--heartbeat-seconds must be greater than zero")
    return args


def now_local() -> datetime:
    return datetime.now().astimezone()


def format_number(value: Any) -> str:
    if value is None or value == "":
        return ""
    number = float(value)
    return f"{number:g}"


def format_bool(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return "true" if value else "false"
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return "true"
    if text in {"false", "0", "no", "off"}:
        return "false"
    return text


def first_present(data: dict, *names: str) -> Any:
    for name in names:
        if name in data:
            return data[name]
    return None


def parse_snapshot(data: Any) -> dict:
    if not isinstance(data, dict):
        raise ValueError(f"unexpected_json_type:{type(data).__name__}")
    if "Massa" not in data:
        raise ValueError("missing_field:Massa")
    if "Stabil" not in data:
        raise ValueError("missing_field:Stabil")

    try:
        massa = float(data["Massa"])
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_field:Massa") from exc

    return {
        "massa": massa,
        "stabil": format_bool(data["Stabil"]),
        "state": first_present(data, "State", "StState"),
        "state_name": first_present(data, "StateName"),
        "enable": format_bool(first_present(data, "Enable")),
        "rx_packet": first_present(data, "RxPacket", "RX_PACKET"),
        "unit_meas": first_present(data, "UnitMeas", "Unit_Meas", "Unit"),
    }


class CsvEventLog:
    def __init__(self) -> None:
        self.logs_dir = Path(__file__).resolve().parent / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.current_date = None
        self.file = None
        self.writer = None
        self.last_path: Optional[Path] = None

    def _ensure_file(self, timestamp: datetime) -> None:
        date_key = timestamp.strftime("%Y%m%d")
        if self.current_date == date_key and self.file is not None:
            return

        self.close()
        path = self.logs_dir / f"scale_changes_{date_key}.csv"
        is_new = not path.exists() or path.stat().st_size == 0
        self.file = path.open("a", encoding="utf-8-sig", newline="")
        self.writer = csv.DictWriter(self.file, fieldnames=CSV_FIELDS)
        if is_new:
            self.writer.writeheader()
            self.file.flush()
        self.current_date = date_key
        self.last_path = path

    def write(self, row: dict, timestamp: datetime) -> None:
        self._ensure_file(timestamp)
        self.writer.writerow(row)
        self.file.flush()

        console = io.StringIO(newline="")
        csv.writer(console).writerow([row[field] for field in CSV_FIELDS])
        print(console.getvalue().rstrip("\r\n"), flush=True)

    def close(self) -> None:
        if self.file is not None:
            self.file.flush()
            self.file.close()
        self.file = None
        self.writer = None


def make_row(
    timestamp: datetime,
    event: str,
    snapshot: Optional[dict],
    delta_kg: float = 0,
    error: str = "",
) -> dict:
    snapshot = snapshot or {}
    return {
        "timestamp": timestamp.isoformat(timespec="milliseconds"),
        "event": event,
        "massa": format_number(snapshot.get("massa")),
        "delta_kg": format_number(delta_kg),
        "stabil": snapshot.get("stabil", ""),
        "state": snapshot.get("state", ""),
        "state_name": snapshot.get("state_name", ""),
        "enable": snapshot.get("enable", ""),
        "rx_packet": snapshot.get("rx_packet", ""),
        "unit_meas": snapshot.get("unit_meas", ""),
        "error": error,
    }


async def fetch_snapshot(client: httpx.AsyncClient) -> dict:
    url = uniserver_client._build_url(SCALE_ENDPOINT)
    try:
        response = await client.get(url, params=uniserver_client.auth_params)
        response.raise_for_status()
    except httpx.ConnectTimeout as exc:
        raise RuntimeError("connect_timeout") from exc
    except httpx.ReadTimeout as exc:
        raise RuntimeError("read_timeout") from exc
    except httpx.ConnectError as exc:
        raise RuntimeError("connection_refused_or_unreachable") from exc
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"http_{exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"network_error:{type(exc).__name__}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("invalid_json") from exc
    try:
        return parse_snapshot(data)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc


def detect_events(previous: dict, current: dict, min_delta_kg: float) -> tuple[list[str], float]:
    delta = current["massa"] - previous["massa"]
    events = []
    if abs(delta) >= min_delta_kg:
        events.append("weight_changed")
    if current["stabil"] != previous["stabil"]:
        events.append("stability_changed")
    if current["state"] != previous["state"]:
        events.append("state_changed")
    if current["state_name"] != previous["state_name"]:
        events.append("state_name_changed")
    if current["enable"] != previous["enable"]:
        events.append("enable_changed")
    return events, delta


async def monitor(args: argparse.Namespace, event_log: CsvEventLog) -> None:
    timeout = httpx.Timeout(settings.UNISERVER_TIMEOUT)
    last_logged: Optional[dict] = None
    api_available: Optional[bool] = None
    last_heartbeat = now_local()

    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            iteration_started = asyncio.get_running_loop().time()
            timestamp = now_local()
            heartbeat_due = (timestamp - last_heartbeat).total_seconds() >= args.heartbeat_seconds

            try:
                snapshot = await fetch_snapshot(client)
            except RuntimeError as exc:
                if api_available is not False:
                    event_log.write(
                        make_row(timestamp, "api_unavailable", last_logged, error=str(exc)),
                        timestamp,
                    )
                elif heartbeat_due:
                    event_log.write(
                        make_row(timestamp, "heartbeat", last_logged, error=str(exc)),
                        timestamp,
                    )
                    last_heartbeat = timestamp
                api_available = False
            else:
                events = []
                delta = 0.0
                if api_available is False:
                    events.append("api_recovered")
                if last_logged is None:
                    events.append("initial")
                else:
                    changed, delta = detect_events(last_logged, snapshot, args.min_delta_kg)
                    events.extend(changed)

                if heartbeat_due:
                    events.append("heartbeat")

                if events:
                    event_name = "|".join(dict.fromkeys(events))
                    if events == ["heartbeat"]:
                        delta = 0.0
                    event_log.write(make_row(timestamp, event_name, snapshot, delta), timestamp)
                    last_logged = snapshot
                if heartbeat_due or "initial" in events:
                    last_heartbeat = timestamp
                api_available = True

            elapsed = asyncio.get_running_loop().time() - iteration_started
            await asyncio.sleep(max(0, args.interval_ms / 1000 - elapsed))


def main() -> int:
    args = parse_args()
    event_log = CsvEventLog()
    try:
        asyncio.run(monitor(args, event_log))
    except KeyboardInterrupt:
        pass
    finally:
        event_log.close()

    last_path = str(event_log.last_path) if event_log.last_path else "CSV file was not created"
    print(f"Stopped. Last CSV file: {last_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
