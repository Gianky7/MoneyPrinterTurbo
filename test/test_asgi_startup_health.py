import asyncio
import time
from unittest.mock import patch

from fastapi.testclient import TestClient


def test_healthz_returns_200_without_external_backends():
    from app import asgi
    from app.services import task as task_service

    with patch.object(task_service, "recover_interrupted_cross_posts", return_value=None):
        with TestClient(asgi.app) as client:
            response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_slow_startup_recovery_does_not_block_lifespan_ready():
    from app import asgi
    from app.services import task as task_service

    def slow_recovery():
        time.sleep(1)

    async def enter_lifespan():
        started_at = time.perf_counter()
        with patch.object(task_service, "recover_interrupted_cross_posts", slow_recovery):
            async with asgi.application_lifespan(asgi.app):
                return time.perf_counter() - started_at

    elapsed = asyncio.run(enter_lifespan())

    assert elapsed < 0.5


def test_recovery_exception_does_not_block_lifespan_ready():
    from app import asgi
    from app.services import task as task_service

    def failing_recovery():
        raise RuntimeError("redis unavailable")

    async def enter_lifespan():
        with patch.object(task_service, "recover_interrupted_cross_posts", failing_recovery):
            async with asgi.application_lifespan(asgi.app):
                return True

    assert asyncio.run(enter_lifespan()) is True


def test_app_imports_and_starts_without_redis_backend():
    from app import asgi
    from app.services import task as task_service

    with patch.object(task_service, "recover_interrupted_cross_posts", return_value=None):
        with TestClient(asgi.app) as client:
            assert client.get("/healthz").status_code == 200
