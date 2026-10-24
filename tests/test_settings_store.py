"""settings.json: validation, round trip, precedence over config.py."""

import json

import pytest

import config
from core import settings_store as store
from core.settings_store import BY_KEY, SCHEMA, SETUP_DONE_KEY


def test_every_setting_exists_in_config_and_its_default_is_valid():
    for setting in SCHEMA:
        assert hasattr(config, setting.key), setting.key
        assert store.coerce(setting, getattr(config, setting.key)) == getattr(config, setting.key)


def test_config_records_the_defaults_before_any_override():
    assert store.DEFAULTS["CAMERA_INDEX"] == config.CAMERA_INDEX
    assert set(store.DEFAULTS) == {s.key for s in SCHEMA}


@pytest.mark.parametrize(
    "key, value, expected",
    [
        ("HUD_ENABLED", False, False),
        ("CAMERA_INDEX", 2, 2),
        ("CAMERA_INDEX", 2.0, 2),
        ("POINTER_SPEED", 500, 500.0),
        ("ATTENTION_GATE", "start", "start"),
        ("MODES_ENABLED", ["scroll", "move"], ("move", "scroll")),  # canonical order
    ],
)
def test_valid_values_are_coerced(key, value, expected):
    result = store.coerce(BY_KEY[key], value)
    assert result == expected and type(result) is type(expected)


@pytest.mark.parametrize(
    "key, value",
    [
        ("HUD_ENABLED", 1),
        ("CAMERA_INDEX", True),
        ("CAMERA_INDEX", 1.5),
        ("CAMERA_INDEX", 99),
        ("POINTER_SPEED", "fast"),
        ("POINTER_SPEED", float("nan")),
        ("POINTER_SPEED", 5000),
        ("ATTENTION_GATE", "turbo"),
        ("MODES_ENABLED", []),
        ("MODES_ENABLED", ["move", "move"]),
        ("MODES_ENABLED", ["move", "fly"]),
        ("MODES_ENABLED", "move"),
    ],
)
def test_invalid_values_are_rejected(key, value):
    with pytest.raises(ValueError):
        store.coerce(BY_KEY[key], value)


def test_missing_file_means_no_settings(tmp_path):
    assert store.load(tmp_path / "settings.json") == {}
    assert store.problems == []
    assert not store.setup_done(tmp_path / "settings.json")


def test_unreadable_file_is_ignored_and_reported(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert store.load(path) == {}
    assert len(store.problems) == 1


def test_bad_entries_are_skipped_good_ones_kept(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"POINTER_SPEED": 600, "CAMERA_INDEX": "one", "NOPE": 1, "_setup_done": True}))
    assert store.load(path) == {"POINTER_SPEED": 600.0, "_setup_done": True}
    assert len(store.problems) == 2


def test_retired_settings_in_old_files_are_ignored_quietly(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"INTERACTION_MODE": "classic", "HUD_ENABLED": False}))
    assert store.load(path) == {"HUD_ENABLED": False}
    assert store.problems == []
    store.update({"SOUNDS_ENABLED": False}, path)  # the next save drops it from the file
    assert "INTERACTION_MODE" not in json.loads(path.read_text())


def test_round_trip_creates_the_folder(tmp_path):
    path = tmp_path / "AirMouse" / "settings.json"
    store.save({"MODES_ENABLED": ("move", "media"), "HUD_ENABLED": False}, path)
    assert json.loads(path.read_text(encoding="utf-8"))["MODES_ENABLED"] == ["move", "media"]
    assert store.load(path) == {"MODES_ENABLED": ("move", "media"), "HUD_ENABLED": False}
    assert not (tmp_path / "AirMouse" / "settings.json.tmp").exists()


def test_save_refuses_invalid_values(tmp_path):
    with pytest.raises(ValueError):
        store.save({"POINTER_SPEED": -1}, tmp_path / "settings.json")
    assert not (tmp_path / "settings.json").exists()


def test_update_merges_and_keeps_metadata(tmp_path):
    path = tmp_path / "settings.json"
    store.update({SETUP_DONE_KEY: True}, path)
    merged = store.update({"SOUNDS_ENABLED": False}, path)
    assert merged == {SETUP_DONE_KEY: True, "SOUNDS_ENABLED": False}
    assert store.setup_done(path)


def test_apply_sets_settings_but_not_metadata():
    namespace = {"POINTER_SPEED": 450.0}
    applied = store.apply(namespace, {"POINTER_SPEED": 700.0, SETUP_DONE_KEY: True})
    assert applied == ["POINTER_SPEED"]
    assert namespace == {"POINTER_SPEED": 700.0}


def test_saved_settings_win_over_config(tmp_path):
    path = tmp_path / "settings.json"
    store.save({"CAMERA_INDEX": 3}, path)
    namespace = {"CAMERA_INDEX": 1}  # e.g. from config_local.py
    store.apply_saved(namespace, path)
    assert namespace["CAMERA_INDEX"] == 3


def test_settings_file_location(monkeypatch, tmp_path):
    monkeypatch.delenv("AIRMOUSE_SETTINGS", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert store.default_path() == tmp_path / "AirMouse" / "settings.json"
    monkeypatch.setenv("AIRMOUSE_SETTINGS", str(tmp_path / "x.json"))
    assert store.default_path() == tmp_path / "x.json"


def test_snapshot_reads_a_module_or_globals():
    snap = store.snapshot(config)
    assert snap["ATTENTION_GATE"] == config.ATTENTION_GATE
    assert store.snapshot({"HUD_ENABLED": True}) == {"HUD_ENABLED": True}
