"""Camera letterboxing, model files and app paths — no hardware needed."""

import importlib
import sys

from core import models, paths, startup
from core.camera import letterbox_padding


def test_matching_aspect_needs_no_borders():
    assert letterbox_padding(1280, 720, 1280, 720) is None
    assert letterbox_padding(1920, 1080, 1280, 720) is None
    assert letterbox_padding(854, 480, 1280, 720) is None  # within 1 %


def test_four_by_three_gets_side_borders():
    top, bottom, left, right = letterbox_padding(640, 480, 1280, 720)
    assert (top, bottom) == (0, 0)
    assert left + 640 + right == 853 and abs(left - right) <= 1


def test_wider_than_target_gets_top_and_bottom_borders():
    top, bottom, left, right = letterbox_padding(2560, 1080, 1280, 720)
    assert (left, right) == (0, 0)
    assert abs((2560 / (1080 + top + bottom)) - 16 / 9) < 0.01


def test_model_is_downloaded_once(tmp_path):
    source = tmp_path / "remote.task"
    source.write_bytes(b"model")
    target = tmp_path / "models" / "hand.task"
    models.ensure_model(str(target), source.as_uri(), "test")
    assert target.read_bytes() == b"model"
    source.write_bytes(b"changed")
    models.ensure_model(str(target), source.as_uri(), "test")
    assert target.read_bytes() == b"model"  # already there: not downloaded again
    assert not (tmp_path / "models" / "hand.task.part").exists()


def test_bundled_model_is_used_when_there_is_no_local_copy(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    (bundle / "models").mkdir(parents=True)
    (bundle / "models" / "hand.task").write_bytes(b"bundled")
    monkeypatch.setattr(paths, "RESOURCE_DIR", bundle)
    monkeypatch.chdir(tmp_path)
    url = (tmp_path / "missing.task").as_uri()  # would fail if a download were tried
    assert models.load_model("models/hand.task", url, "test") == b"bundled"
    assert not (tmp_path / "models").exists()  # nothing downloaded or copied


def test_source_checkout_paths_point_at_the_repository():
    assert not paths.FROZEN
    assert paths.resource("core/web/settings.html").exists()
    assert paths.DATA_DIR == paths.SOURCE_DIR or "AIRMOUSE_DATA_DIR" in __import__("os").environ


def test_installed_app_writes_to_local_appdata(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.delenv("AIRMOUSE_DATA_DIR", raising=False)
    try:
        frozen = importlib.reload(paths)
        assert frozen.FROZEN
        assert frozen.RESOURCE_DIR == tmp_path / "_internal"
        assert frozen.DATA_DIR == tmp_path / "Local" / "AirMouse"
    finally:
        monkeypatch.undo()
        importlib.reload(paths)


def test_installed_app_starts_itself_with_windows():
    assert startup.launch_command(python=r"C:\Apps\AirMouse\AirMouse.exe", frozen=True) == r'"C:\Apps\AirMouse\AirMouse.exe"'
