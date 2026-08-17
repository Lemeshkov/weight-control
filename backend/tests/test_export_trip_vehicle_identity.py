import csv
import json
from types import SimpleNamespace

import pytest

from scripts.export_trip_vehicle_identity import (
    query_identity_rows,
    read_requested_trip_ids,
    summarize,
    write_export,
)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class ReadOnlySession:
    def __init__(self, rows):
        self.rows = rows
        self.executions = 0
        self.rolled_back = False
        self.closed = False

    def execute(self, _statement):
        self.executions += 1
        return FakeResult(self.rows)

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True

    def add(self, *_args):
        raise AssertionError("DB mutation attempted")

    def commit(self):
        raise AssertionError("DB commit attempted")


def test_export_preserves_every_requested_id_and_status():
    session = ReadOnlySession([
        SimpleNamespace(trip_id=11, vehicle_id=5, license_plate="A", uniserver_code="D11"),
        SimpleNamespace(trip_id=13, vehicle_id=6, license_plate=None, uniserver_code="D13"),
    ])
    rows = query_identity_rows([11, 12, 13], session_factory=lambda: session)
    assert [row["trip_id"] for row in rows] == [11, 12, 13]
    assert [row["status"] for row in rows] == ["FOUND", "TRIP_NOT_FOUND", "VEHICLE_NOT_FOUND"]
    assert session.executions == 1
    assert session.rolled_back and session.closed
    assert summarize(rows) == {
        "requested_count": 3,
        "found_trip_count": 2,
        "found_vehicle_count": 1,
        "missing_trip_count": 1,
        "missing_vehicle_count": 1,
    }


def test_input_validation_does_not_silently_skip_rows(tmp_path):
    source = tmp_path / "ids.csv"
    source.write_text("trip_id\n11\ninvalid\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid trip_id"):
        read_requested_trip_ids(source)


def test_csv_and_summary_are_written_without_database_details(tmp_path):
    rows = [{"trip_id": 11, "vehicle_id": 5, "license_plate": "A", "uniserver_code": "D", "status": "FOUND"}]
    output, summary_path = tmp_path / "out.csv", tmp_path / "summary.json"
    summary = write_export(output, summary_path, rows)
    with output.open(encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle)) == [{
            "trip_id": "11", "vehicle_id": "5", "license_plate": "A",
            "uniserver_code": "D", "status": "FOUND",
        }]
    assert json.loads(summary_path.read_text(encoding="utf-8")) == summary
    assert "database" not in summary_path.read_text(encoding="utf-8").lower()
