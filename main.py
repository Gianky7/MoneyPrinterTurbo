import os

import uvicorn
from loguru import logger

from app.config import config


def get_runtime_host() -> str:
    """Return the host required by API/container deployments."""
    return "0.0.0.0"


def get_runtime_port() -> int:
    """Return Railway's PORT when provided, otherwise the configured port."""
    port = os.getenv("PORT")
    if port:
        return int(port)
    return int(config.listen_port)


def is_railway_environment() -> bool:
    """Return True when running inside Railway's production container."""
    return any(
        os.getenv(name)
        for name in ("RAILWAY_ENVIRONMENT", "RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_ID")
    )


def get_runtime_reload() -> bool:
    """Disable reload on Railway so the production worker is never restarted by dev reload."""
    if is_railway_environment():
        return False
    return bool(config.reload_debug)


if __name__ == "__main__":
    host = get_runtime_host()
    port = get_runtime_port()
    reload = get_runtime_reload()
    logger.info(f"start server, host={host}, port={port}, reload={reload}, docs=/docs")
    uvicorn.run(
        app="app.asgi:app",
        host=host,
        port=port,
        reload=reload,
        log_level="warning",
    )
