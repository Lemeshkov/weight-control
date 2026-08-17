"""Read-only export of Trip -> Vehicle identity for offline diagnostics.

This tool performs one SELECT query and never calls add, flush, commit, or any
schema-management operation. Run it where the backend's DATABASE_URL is available.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select

# Make direct invocation from the repository root independent of PYTHONPATH.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import SessionLocal  # noqa: E402
from models import Trip, Vehicle  # noqa: E402


OUTPUT_FIELDS = ["trip_id", "vehicle_id", "license_plate", "uniserver_code", "status"]


def read_requested_trip_ids(path: Path) -> list[int]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "trip_id" not in reader.fieldnames:
            raise ValueError("Input CSV must contain a trip_id column")
        requested = []
        for line_number, row in enumerate(reader, start=2):
            value = str(row.get("trip_id") or "").strip()
            if not value:
                raise ValueError(f"Missing trip_id at CSV line {line_number}")
            try:
                requested.append(int(value))
            except ValueError as exc:
                raise ValueError(f"Invalid trip_id at CSV line {line_number}: {value!r}") from exc
    return requested


def query_identity_rows(requested: list[int], session_factory: Callable = SessionLocal) -> list[dict[str, Any]]:
    unique_ids = list(dict.fromkeys(requested))
    found: dict[int, Any] = {}
    session = session_factory()
    try:
        if unique_ids:
            statement = (
                select(
                    Trip.id.label("trip_id"),
                    Trip.vehicle_id.label("vehicle_id"),
                    Vehicle.plate_number.label("license_plate"),
                    Trip.uniserver_code.label("uniserver_code"),
                )
                .select_from(Trip)
                .outerjoin(Vehicle, Vehicle.id == Trip.vehicle_id)
                .where(Trip.id.in_(unique_ids))
            )
            found = {int(row.trip_id): row for row in session.execute(statement).all()}
    finally:
        # End the read transaction explicitly. No commit is ever performed.
        session.rollback()
        session.close()

    output = []
    for trip_id in requested:
        row = found.get(trip_id)
        if row is None:
            output.append({
                "trip_id": trip_id,
                "vehicle_id": None,
                "license_plate": None,
                "uniserver_code": None,
                "status": "TRIP_NOT_FOUND",
            })
        elif row.vehicle_id is None or row.license_plate is None:
            output.append({
                "trip_id": trip_id,
                "vehicle_id": row.vehicle_id,
                "license_plate": row.license_plate,
                "uniserver_code": row.uniserver_code,
                "status": "VEHICLE_NOT_FOUND",
            })
        else:
            output.append({
                "trip_id": trip_id,
                "vehicle_id": row.vehicle_id,
                "license_plate": row.license_plate,
                "uniserver_code": row.uniserver_code,
                "status": "FOUND",
            })
    return output


def summarize(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "requested_count": len(rows),
        "found_trip_count": sum(row["status"] != "TRIP_NOT_FOUND" for row in rows),
        "found_vehicle_count": sum(row["status"] == "FOUND" for row in rows),
        "missing_trip_count": sum(row["status"] == "TRIP_NOT_FOUND" for row in rows),
        "missing_vehicle_count": sum(row["status"] == "VEHICLE_NOT_FOUND" for row in rows),
    }


def write_export(output_path: Path, summary_path: Path, rows: list[dict[str, Any]]) -> dict[str, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary = summarize(rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="CSV containing requested trip_id values")
    parser.add_argument("--output", type=Path, required=True, help="Destination identity CSV")
    parser.add_argument("--summary", type=Path, required=True, help="Destination summary JSON")
    args = parser.parse_args()

    requested = read_requested_trip_ids(args.input)
    rows = query_identity_rows(requested)
    summary = write_export(args.output, args.summary, rows)
    # Deliberately print only counts and output locations, never database configuration.
    print(json.dumps({**summary, "output_csv": str(args.output), "summary_json": str(args.summary)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
