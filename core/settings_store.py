# core/settings_store.py
"""
The settings people change in the settings page, saved as a small JSON file.

Precedence, later wins:  config.py defaults → config_local.py (developer
overrides) → settings.json (written by the settings page).

Only the keys in SCHEMA are read from the file and each value is validated,
so an old or hand-edited file can never stop AirMouse from starting: bad
entries are skipped and reported in ``problems`` (main.py logs them once
logging is set up — this module runs while config.py is being imported).

This module must not import config.py (config.py imports it).
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

SETUP_DONE_KEY = "_setup_done"  # keys starting with "_" are metadata, not settings


def default_path() -> Path:
    """%APPDATA%\\AirMouse\\settings.json (survives updates); AIRMOUSE_SETTINGS overrides it."""
    override = os.environ.get("AIRMOUSE_SETTINGS")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "AirMouse" / "settings.json"
    return Path.home() / ".airmouse" / "settings.json"


@dataclass(frozen=True)
class Setting:
    key: str
    kind: str  # "bool" | "int" | "float" | "choice" | "multi"
    choices: tuple = ()
    min: float | None = None
    max: float | None = None
    step: float | None = None

    def to_json(self) -> dict:
        data = {"key": self.key, "kind": self.kind}
        if self.choices:
            data["choices"] = list(self.choices)
        for name in ("min", "max", "step"):
            if getattr(self, name) is not None:
                data[name] = getattr(self, name)
        return data


SCHEMA: tuple[Setting, ...] = (
    Setting("CAMERA_INDEX", "int", min=0, max=9),
    Setting("DOMINANT_HAND", "choice", ("right", "left")),
    Setting("LEFT_HAND_ENABLED", "bool"),
    Setting("MODES_ENABLED", "multi", ("move", "scroll", "shortcuts", "media", "windows")),
    Setting("CURSOR_MAPPING", "choice", ("relative", "absolute")),
    Setting("POINTER_SPEED", "float", min=150, max=1000, step=25),
    Setting("PINCH_INDEX_ENTER_RATIO", "float", min=0.20, max=0.40, step=0.01),
    Setting("ARM_HOLD_S", "float", min=0.3, max=1.5, step=0.05),
    Setting("DISARM_HOLD_S", "float", min=0.6, max=3.0, step=0.1),
    Setting("SCROLL_TICKS_PER_HAND_LENGTH", "float", min=2, max=15, step=0.5),
    Setting("ATTENTION_GATE", "choice", ("always", "start", "off")),
    Setting("ATTENTION_MAX_ANGLE", "float", min=15, max=60, step=1),
    Setting("HUD_ENABLED", "bool"),
    Setting("HUD_POSITION", "choice", ("bottom-right", "bottom-left", "top-right", "top-left")),
    Setting("SOUNDS_ENABLED", "bool"),
)
BY_KEY = {s.key: s for s in SCHEMA}
# Settings the page used to offer: still in old files, silently ignored
RETIRED = frozenset({"INTERACTION_MODE"})

DEFAULTS: dict = {}       # config.py values before any override (filled by config.py)
problems: list[str] = []  # what was wrong with the file at the last load


def coerce(setting: Setting, value):
    """The validated value, or ValueError with a short reason."""
    kind = setting.kind
    if kind == "bool":
        if isinstance(value, bool):
            return value
        raise ValueError("expected true or false")
    if kind in ("int", "float"):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("expected a number")
        if kind == "int":
            if value != int(value):
                raise ValueError("expected a whole number")
            value = int(value)
        else:
            value = float(value)
        if setting.min is not None and value < setting.min or setting.max is not None and value > setting.max:
            raise ValueError(f"expected {setting.min}–{setting.max}")
        return value
    if kind == "choice":
        if value in setting.choices:
            return value
        raise ValueError("expected one of " + ", ".join(setting.choices))
    if kind == "multi":
        if (
            isinstance(value, (list, tuple))
            and value
            and all(isinstance(v, str) and v in setting.choices for v in value)
            and len(set(value)) == len(value)
        ):
            return tuple(c for c in setting.choices if c in value)  # canonical order
        raise ValueError("expected a non-empty list of " + ", ".join(setting.choices))
    raise ValueError(f"unknown kind {kind}")


def validate(values: dict) -> tuple[dict, dict]:
    """(valid values, {key: reason}) — metadata keys pass through untouched."""
    valid, errors = {}, {}
    for key, value in values.items():
        if key.startswith("_"):
            valid[key] = value
            continue
        setting = BY_KEY.get(key)
        if setting is None:
            errors[key] = "unknown setting"
            continue
        try:
            valid[key] = coerce(setting, value)
        except ValueError as exc:
            errors[key] = str(exc)
    return valid, errors


def load(path: Path | None = None) -> dict:
    """Valid entries of the settings file ({} when there is none); problems go to ``problems``."""
    path = Path(path) if path is not None else default_path()
    problems.clear()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        problems.append(f"{path}: unreadable, ignored ({exc})")
        return {}
    if not isinstance(data, dict):
        problems.append(f"{path}: not a JSON object, ignored")
        return {}
    valid, errors = validate({k: v for k, v in data.items() if k not in RETIRED})
    problems.extend(f"{path}: {key} ignored ({reason})" for key, reason in errors.items())
    return valid


def save(values: dict, path: Path | None = None) -> Path:
    """Write the file atomically (a crash mid-write never leaves half a file)."""
    path = Path(path) if path is not None else default_path()
    valid, errors = validate(values)
    if errors:
        raise ValueError(errors)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {k: list(v) if isinstance(v, tuple) else v for k, v in valid.items()}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def update(changes: dict, path: Path | None = None) -> dict:
    """Merge validated changes into the file and return everything it now holds."""
    valid, errors = validate(changes)
    if errors:
        raise ValueError(errors)
    merged = load(path)
    merged.update(valid)
    save(merged, path)
    return merged


def snapshot(namespace) -> dict:
    """Current value of every schema setting, from config's globals() or the config module."""
    get = namespace.get if isinstance(namespace, dict) else lambda k, d=None: getattr(namespace, k, d)
    return {s.key: get(s.key) for s in SCHEMA if get(s.key) is not None}


def apply(namespace: dict, values: dict) -> list[str]:
    """Set the settings (not the metadata) into config's globals(); returns the keys applied."""
    applied = []
    for key, value in values.items():
        if key in BY_KEY:
            namespace[key] = value
            applied.append(key)
    return applied


def apply_saved(namespace: dict, path: Path | None = None) -> list[str]:
    return apply(namespace, load(path))


def setup_done(path: Path | None = None) -> bool:
    return load(path).get(SETUP_DONE_KEY) is True


def to_json(values: dict) -> dict:
    return {k: list(v) if isinstance(v, tuple) else v for k, v in values.items()}
