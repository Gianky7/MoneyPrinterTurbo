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


if __name__ == "__main__":
    host = get_runtime_host()
    port = get_runtime_port()
    logger.info("start server, docs: http://" + host + ":" + str(port) + "/docs")
    uvicorn.run(
        app="app.asgi:app",
        host=host,
        port=port,
        reload=config.reload_debug,
        log_level="warning",
    )
