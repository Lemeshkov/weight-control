"""Offline validation of diagnostic manifest vehicle/trip ownership."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def validate_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    bindings = manifest.get("bindings")
    if not isinstance(bindings, list):
        return {
            "manifest": str(path),
            "session_key": manifest.get("session_key"),
            "identity_status": "LEGACY_NO_IDENTITY",
            "binding_count": 0,
            "unique_trip_count": 0,
            "trip_id": manifest.get("trip_id"),
            "vehicle_id": None,
            "license_plate": None,
            "uniserver_code": None,
        }

    unique_trips = {item.get("trip_id") for item in bindings if item.get("trip_id") is not None}
    identity = manifest.get("identity") or (bindings[0] if len(bindings) == 1 else {})
    required = ("trip_id", "vehicle_id", "license_plate_snapshot")
    if len(unique_trips) > 1 or len(bindings) > 1:
        status = "INVALID_MULTI_TRIP"
    elif len(bindings) == 0:
        status = "UNBOUND"
    elif any(identity.get(key) in (None, "") for key in required):
        status = "INCOMPLETE_IDENTITY"
    else:
        status = "VALID_SINGLE_TRIP"
    return {
        "manifest": str(path),
        "session_key": manifest.get("session_key"),
        "identity_status": status,
        "binding_count": len(bindings),
        "unique_trip_count": len(unique_trips),
        "trip_id": identity.get("trip_id"),
        "vehicle_id": identity.get("vehicle_id"),
        "license_plate": identity.get("license_plate_snapshot"),
        "uniserver_code": identity.get("uniserver_code"),
    }


def discover_manifests(inputs: list[Path]) -> list[Path]:
    found: list[Path] = []
    for item in inputs:
        if item.is_file():
            found.append(item)
        elif item.is_dir() and (item / "manifest.json").is_file():
            found.append(item / "manifest.json")
        elif item.is_dir():
            found.extend(item.rglob("manifest.json"))
    return sorted(set(path.resolve() for path in found))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    rows = [validate_manifest(path) for path in discover_manifests(args.paths)]
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["manifest"])
            writer.writeheader()
            writer.writerows(rows)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 1 if any(row["identity_status"] == "INVALID_MULTI_TRIP" for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
