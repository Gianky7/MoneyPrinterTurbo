"""Application implementation - ASGI."""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.config import config
from app.models.exception import HttpException
from app.router import root_api_router
from app.utils import utils

RECOVERY_TIMEOUT_SECONDS = 30


async def _run_startup_recovery() -> None:
    """Run best-effort startup recovery without blocking API readiness."""
    logger.info("MPT_RECOVERY_STARTED")
    try:
        from app.services import task as task_service

        await asyncio.wait_for(
            asyncio.to_thread(task_service.recover_interrupted_cross_posts),
            timeout=RECOVERY_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.exception("MPT_RECOVERY_FAILED")
    else:
        logger.info("MPT_RECOVERY_COMPLETE")


@asynccontextmanager
async def application_lifespan(_: FastAPI):
    """集中处理 API 进程启动恢复和关闭日志。"""
    logger.info("MPT_STARTUP_BEGIN")

    # 跨平台发布由当前进程线程池执行，不会在服务重启后恢复。恢复任务只做
    # best-effort 后台处理，不能阻塞 FastAPI lifespan yield，否则 Railway
    # 会在应用尚未 ready 时返回 502。
    recovery_task = asyncio.create_task(_run_startup_recovery())
    try:
        logger.info("MPT_API_READY")
        yield
    finally:
        if not recovery_task.done():
            recovery_task.cancel()
        logger.info("shutdown event")


def exception_handler(request: Request, e: HttpException):
    return JSONResponse(
        status_code=e.status_code,
        content=utils.get_response(e.status_code, e.data, e.message),
    )


def validation_exception_handler(request: Request, e: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content=utils.get_response(
            status=400, data=e.errors(), message="field required"
        ),
    )


def get_application() -> FastAPI:
    """Initialize FastAPI application.

    Returns:
       FastAPI: Application object instance.

    """
    instance = FastAPI(
        title=config.project_name,
        description=config.project_description,
        version=config.project_version,
        debug=False,
        lifespan=application_lifespan,
    )
    instance.include_router(root_api_router)

    @instance.get("/healthz", tags=["Health Check"])
    def healthz() -> dict[str, str]:
        """Lightweight readiness endpoint with no external dependencies."""
        return {"status": "ok"}

    instance.add_exception_handler(HttpException, exception_handler)
    instance.add_exception_handler(RequestValidationError, validation_exception_handler)
    return instance


app = get_application()

# Configures the CORS middleware for the FastAPI app
cors_allowed_origins_str = os.getenv("CORS_ALLOWED_ORIGINS", "")
origins = cors_allowed_origins_str.split(",") if cors_allowed_origins_str else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

task_dir = utils.task_dir()
app.mount(
    "/tasks", StaticFiles(directory=task_dir, html=True, follow_symlink=True), name=""
)

public_dir = utils.public_dir()
app.mount("/", StaticFiles(directory=public_dir, html=True), name="")
