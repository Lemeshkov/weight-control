import os
import subprocess
import sys
from pathlib import Path


def test_standalone_importer_registers_all_fks_and_applies_idempotently(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "standalone-import.sqlite"
    code = f"""
import runpy
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

namespace = runpy.run_path(r"{backend_dir / 'scripts' / 'import_fuel_quality_history.py'}", run_name="standalone_import_test")
from database import Base
import lab_models as lm

# Resolving sorted_tables traverses every ForeignKey registered in metadata.
table_names = {{table.name for table in Base.metadata.sorted_tables}}
assert "users" in table_names
for table in Base.metadata.tables.values():
    for foreign_key in table.foreign_keys:
        assert foreign_key.column.table.name in table_names

engine = create_engine(r"sqlite:///{database_path.as_posix()}")
Base.metadata.create_all(engine)
namespace["main"].__globals__["SessionLocal"] = sessionmaker(bind=engine)

sys.argv = ["import_fuel_quality_history.py", "--apply"]
assert namespace["main"]() == 0
with sessionmaker(bind=engine)() as db:
    assert db.query(lm.LabFuelQualityTest).count() == 31
    assert db.query(lm.LabFuelQualityAuditLog).filter_by(action="IMPORT_EXCEL").count() == 31

sys.argv = ["import_fuel_quality_history.py"]
assert namespace["main"]() == 0
"""
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=backend_dir, capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert "APPLY: найдено=31, уже_есть=0, импортировано=31" in result.stdout
    assert "DRY-RUN: найдено=31, уже_есть=31, импортировано=0" in result.stdout
