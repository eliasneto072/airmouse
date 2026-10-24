"""Camera letterboxing and model download — no hardware needed."""

from core import models
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
