import json
import subprocess
import sys
from pathlib import Path


def test_laboratory_app_import_does_not_load_hardware_modules():
    backend=Path(__file__).resolve().parents[1]
    code="""import json,sys
import laboratory_main
blocked=['services.uniserver_client','services.lidar_client','services.camera_client','services.scale_monitor','services.weighing_lidar_coordinator']
routes={route.path for route in laboratory_main.app.routes}
print(json.dumps({'loaded':[name for name in blocked if name in sys.modules],'routes':sorted(routes)}))
"""
    result=subprocess.run([sys.executable,"-c",code],cwd=backend,text=True,capture_output=True,check=True)
    data=json.loads(result.stdout.strip().splitlines()[-1])
    assert data["loaded"]==[]
    assert "/api/v1/laboratory/fuel-quality" in data["routes"]
    assert "/api/v1/laboratory/fuel-quality/calculate" in data["routes"]
    assert "/api/v1/laboratory/fuel-quality/export.xlsx" in data["routes"]


def test_main_app_does_not_register_laboratory_routes():
    source=(Path(__file__).resolve().parents[1]/"main.py").read_text(encoding="utf-8")
    assert "include_router(laboratory.router)" not in source
