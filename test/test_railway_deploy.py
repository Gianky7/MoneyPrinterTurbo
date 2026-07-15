import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI

from app.config import config

ROOT_DIR = Path(__file__).resolve().parent.parent


def load_main_module():
    spec = importlib.util.spec_from_file_location("mpt_main_for_test", ROOT_DIR / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_port_uses_railway_port_when_present(monkeypatch):
    monkeypatch.setenv("PORT", "4567")
    module = load_main_module()

    assert module.get_runtime_port() == 4567


def test_runtime_port_falls_back_to_config_when_port_absent(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    module = load_main_module()

    with patch.object(config, "listen_port", 8765):
        assert module.get_runtime_port() == 8765


def test_runtime_host_is_public_container_host():
    module = load_main_module()

    assert module.get_runtime_host() == "0.0.0.0"


def test_runtime_reload_is_false_on_railway_even_when_config_enables_reload(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    module = load_main_module()

    with patch.object(config, "reload_debug", True):
        assert module.get_runtime_reload() is False


def test_runtime_reload_uses_config_outside_railway(monkeypatch):
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    monkeypatch.delenv("RAILWAY_SERVICE_ID", raising=False)
    module = load_main_module()

    with patch.object(config, "reload_debug", True):
        assert module.get_runtime_reload() is True


def test_fastapi_app_imports_without_starting_server():
    from app.asgi import app

    assert isinstance(app, FastAPI)


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/v1/videos", "POST"),
        ("/api/v1/tasks/{task_id}", "GET"),
    ],
)
def test_primary_api_endpoints_are_registered(path, method):
    from app.asgi import app

    registered = {
        (route.path, http_method)
        for route in app.routes
        for http_method in getattr(route, "methods", set())
    }

    assert (path, method) in registered


def test_task_static_files_mount_is_registered():
    from app.asgi import app

    assert any(getattr(route, "path", None) == "/tasks" for route in app.routes)
