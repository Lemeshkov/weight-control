import importlib
import json
import subprocess
import sys

from fastapi.testclient import TestClient


HARDWARE_MODULES = {
    "routers.lidar", "routers.weighing", "routers.camera", "routers.scan_3d",
    "services.lidar_client", "services.camera_client", "services.scale_monitor",
    "services.uniserver_client",
}


def test_laboratory_app_imports_without_network_or_hardware_modules():
    code = """
import json, socket, sys
def forbidden(*args, **kwargs): raise AssertionError('network access during import')
socket.socket.connect = forbidden
import laboratory_main
print(json.dumps({'title': laboratory_main.app.title, 'modules': sorted(sys.modules)}))
"""
    result = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout.strip())
    assert not (HARDWARE_MODULES & set(payload["modules"]))
    assert payload["title"] == "Weight Control — Laboratory"


def test_laboratory_routes_and_health_are_available():
    module = importlib.import_module("laboratory_main")
    paths = {route.path for route in module.app.routes}
    assert "/api/health" in paths
    assert "/api/v1/laboratory/experiments" in paths
    assert not any(path.startswith(("/api/lidar", "/api/weighing", "/api/camera", "/api/scan3d")) for path in paths)
    response = TestClient(module.app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["service"] == "laboratory"


def test_main_backend_import_does_not_connect_to_lidar():
    code = """
import socket
def forbidden(*args, **kwargs): raise AssertionError('network access during import')
socket.socket.connect = forbidden
import main
print(main.app.title)
"""
    result = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    assert result.stdout.strip() == "Weight Control System - Уголь-Контроль"
