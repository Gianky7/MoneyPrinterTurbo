import os
import pathlib
import uuid
from typing import BinaryIO

from fastapi import UploadFile

from app.config import config
from app.models.exception import HttpException
from app.utils import file_security, utils

AUDIO_EXTENSIONS = {".mp3", ".wav"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
AUDIO_MIME_TYPES = {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/wave"}
VIDEO_MIME_TYPES = {"video/mp4", "video/quicktime", "video/webm", "video/x-m4v"}
DEFAULT_MAX_AUDIO_BYTES = 100 * 1024 * 1024
DEFAULT_MAX_VIDEO_BYTES = 500 * 1024 * 1024


def max_audio_upload_bytes() -> int:
    return int(
        config.app.get("external_audio_upload_max_bytes", DEFAULT_MAX_AUDIO_BYTES)
    )


def max_video_upload_bytes() -> int:
    return int(
        config.app.get("external_video_upload_max_bytes", DEFAULT_MAX_VIDEO_BYTES)
    )


def _reject_unsafe_original_name(filename: str | None, task_id: str) -> str:
    name = (filename or "").strip()
    normalized = name.replace("\\", "/")
    if (
        not name
        or normalized in {".", ".."}
        or "/" in normalized
        or ".." in pathlib.PurePosixPath(normalized).parts
    ):
        raise HttpException(
            task_id=task_id,
            status_code=400,
            message=f"{task_id}: invalid upload filename",
        )
    return pathlib.Path(name).suffix.lower()


def _require_allowed_upload(
    upload: UploadFile, task_id: str, extensions: set[str], mime_types: set[str]
) -> str:
    suffix = _reject_unsafe_original_name(upload.filename, task_id)
    if suffix not in extensions:
        raise HttpException(
            task_id=task_id,
            status_code=400,
            message=f"{task_id}: unsupported upload extension",
        )
    content_type = (upload.content_type or "").split(";", 1)[0].strip().lower()
    if content_type not in mime_types:
        raise HttpException(
            task_id=task_id,
            status_code=400,
            message=f"{task_id}: unsupported upload MIME type",
        )
    return suffix


def _task_upload_dir(task_id: str, kind: str) -> str:
    base_dir = utils.task_dir(task_id)
    upload_dir = os.path.join(base_dir, "uploads", kind)
    os.makedirs(upload_dir, exist_ok=True)
    file_security.resolve_path_within_directory(
        base_dir, upload_dir, require_file=False
    )
    return upload_dir


def _copy_limited(
    source: BinaryIO, target_path: str, max_bytes: int, task_id: str
) -> int:
    total = 0
    with open(target_path, "wb") as target:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            if not isinstance(chunk, bytes):
                raise HttpException(
                    task_id=task_id,
                    status_code=400,
                    message=f"{task_id}: upload stream must be binary",
                )
            total += len(chunk)
            if total > max_bytes:
                raise HttpException(
                    task_id=task_id,
                    status_code=413,
                    message=f"{task_id}: upload exceeds size limit",
                )
            target.write(chunk)
    return total


def save_task_upload(task_id: str, upload: UploadFile, kind: str) -> str:
    if kind == "audio":
        suffix = _require_allowed_upload(
            upload, task_id, AUDIO_EXTENSIONS, AUDIO_MIME_TYPES
        )
        max_bytes = max_audio_upload_bytes()
    elif kind == "video":
        suffix = _require_allowed_upload(
            upload, task_id, VIDEO_EXTENSIONS, VIDEO_MIME_TYPES
        )
        max_bytes = max_video_upload_bytes()
    else:
        raise ValueError("unsupported upload kind")

    upload_dir = _task_upload_dir(task_id, kind)
    filename = f"{uuid.uuid4().hex}{suffix}"
    target_path = os.path.join(upload_dir, filename)
    file_security.resolve_path_within_directory(
        upload_dir, target_path, require_file=False
    )
    try:
        upload.file.seek(0)
        _copy_limited(upload.file, target_path, max_bytes, task_id)
    except Exception:
        if os.path.exists(target_path):
            os.remove(target_path)
        raise
    return os.path.relpath(target_path, utils.task_dir(task_id)).replace("\\", "/")
