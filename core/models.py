# core/models.py
"""MediaPipe model files: bundled with the installed app, or downloaded on first use."""

from __future__ import annotations

import logging
import os
import urllib.request

from core import paths

logger = logging.getLogger(__name__)


def ensure_model(path: str, url: str, name: str = "MediaPipe") -> str:
    """
    Path of a usable copy of the model: ``path`` itself, the copy bundled with
    the installed app, or a fresh download to ``path`` (atomic: no half files).
    """
    if os.path.exists(path):
        return path
    bundled = paths.resource(path)
    if not os.path.isabs(path) and bundled.exists():
        return str(bundled)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    logger.info("Downloading the %s model to %s …", name, path)
    tmp = path + ".part"
    try:
        urllib.request.urlretrieve(url, tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def load_model(path: str, url: str, name: str = "MediaPipe") -> bytes:
    """
    The model's bytes. MediaPipe gets a buffer instead of a file name because
    it can fail to open paths with accents (C:\\Users\\João\\…) on Windows.
    """
    with open(ensure_model(path, url, name), "rb") as f:
        return f.read()
