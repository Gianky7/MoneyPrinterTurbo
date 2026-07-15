import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from types import SimpleNamespace

import pytest
from fastapi import UploadFile

from app.models.exception import HttpException
from app.models.schema import MaterialInfo, TaskVideoRequest
from app.services import external_media, task as task_service
from app.utils import utils


def make_upload(name, content_type, data=b"abc"):
    return UploadFile(
        filename=name, file=io.BytesIO(data), headers={"content-type": content_type}
    )


def test_upload_audio_valid_task_isolated_server_name(monkeypatch, tmp_path):
    monkeypatch.setattr(
        utils, "storage_dir", lambda sub_dir="", create=False: str(tmp_path / sub_dir)
    )
    saved = external_media.save_task_upload(
        "task1", make_upload("voice.mp3", "audio/mpeg"), "audio"
    )
    assert saved.startswith("uploads/audio/")
    assert saved.endswith(".mp3")
    assert "voice" not in saved
    assert os.path.isfile(tmp_path / "tasks" / "task1" / saved)


def test_upload_video_valid(monkeypatch, tmp_path):
    monkeypatch.setattr(
        utils, "storage_dir", lambda sub_dir="", create=False: str(tmp_path / sub_dir)
    )
    saved = external_media.save_task_upload(
        "task1", make_upload("clip.mp4", "video/mp4"), "video"
    )
    assert saved.startswith("uploads/video/")
    assert os.path.isfile(tmp_path / "tasks" / "task1" / saved)


@pytest.mark.parametrize(
    "filename", ["../voice.mp3", "nested/clip.mp4", "..\\clip.mp4"]
)
def test_reject_path_traversal(filename):
    with pytest.raises(HttpException):
        external_media.save_task_upload(
            "task1", make_upload(filename, "audio/mpeg"), "audio"
        )


def test_reject_extension():
    with pytest.raises(HttpException):
        external_media.save_task_upload(
            "task1", make_upload("voice.exe", "audio/mpeg"), "audio"
        )


def test_reject_mime_type():
    with pytest.raises(HttpException):
        external_media.save_task_upload(
            "task1", make_upload("voice.mp3", "application/octet-stream"), "audio"
        )


def test_reject_size_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(
        utils, "storage_dir", lambda sub_dir="", create=False: str(tmp_path / sub_dir)
    )
    monkeypatch.setattr(external_media, "max_audio_upload_bytes", lambda: 2)
    with pytest.raises(HttpException):
        external_media.save_task_upload(
            "task1", make_upload("voice.mp3", "audio/mpeg", b"abcd"), "audio"
        )


def test_pregenerated_audio_skips_tts(monkeypatch, tmp_path):
    monkeypatch.setattr(
        utils, "storage_dir", lambda sub_dir="", create=False: str(tmp_path / sub_dir)
    )
    audio = tmp_path / "tasks" / "task1" / "uploads" / "audio" / "a.mp3"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"fake")
    monkeypatch.setattr(task_service.voice, "get_audio_duration", lambda _: 7)
    monkeypatch.setattr(
        task_service.voice, "tts", lambda **_: pytest.fail("TTS must not run")
    )
    params = TaskVideoRequest(
        video_subject="s",
        custom_audio_file="uploads/audio/a.mp3",
        voice_name="elevenlabs-pre-generated-audio",
    )
    audio_file, duration, sub_maker = task_service.generate_audio(
        "task1", params, "script"
    )
    assert audio_file == str(audio)
    assert duration == 7
    assert sub_maker is None


def test_legacy_without_audio_uses_tts(monkeypatch, tmp_path):
    monkeypatch.setattr(
        utils, "storage_dir", lambda sub_dir="", create=False: str(tmp_path / sub_dir)
    )
    monkeypatch.setattr(task_service.voice, "get_audio_duration", lambda _: 5)
    monkeypatch.setattr(task_service.voice, "tts", lambda **_: SimpleNamespace())
    params = TaskVideoRequest(
        video_subject="s", voice_name="zh-CN-XiaoxiaoNeural-Female"
    )
    audio_file, duration, sub_maker = task_service.generate_audio(
        "task1", params, "script"
    )
    assert audio_file.endswith("audio.mp3")
    assert duration == 5
    assert sub_maker is not None


def test_task_uploaded_clips_skip_download_and_image_generation(monkeypatch, tmp_path):
    monkeypatch.setattr(
        utils, "storage_dir", lambda sub_dir="", create=False: str(tmp_path / sub_dir)
    )
    monkeypatch.setattr(
        task_service.material,
        "download_videos",
        lambda **_: pytest.fail("download must not run"),
    )
    called = {}

    def fake_preprocess(materials, clip_duration=4, base_dir=None):
        called["base_dir"] = base_dir
        return materials

    monkeypatch.setattr(task_service.video, "preprocess_video", fake_preprocess)
    params = TaskVideoRequest(
        video_subject="s",
        video_source="local",
        video_materials=[
            MaterialInfo(provider="task-upload", url="uploads/video/c.mp4")
        ],
    )
    assert task_service.get_video_materials("task1", params, "", 10) == [
        "uploads/video/c.mp4"
    ]
    assert called["base_dir"] == str(tmp_path / "tasks" / "task1")


def test_no_social_upload_when_service_disabled(monkeypatch):
    monkeypatch.setattr(
        task_service.upload_post.upload_post_service, "is_configured", lambda: False
    )
    assert not task_service.upload_post.upload_post_service.is_configured()
