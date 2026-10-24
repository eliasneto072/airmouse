# core/models.py
"""MediaPipe model files: downloaded on first use (they are git-ignored)."""

from __future__ import annotations

import logging
import os
import urllib.request

logger = logging.getLogger(__name__)


def ensure_model(path: str, url: str, name: str = "MediaPipe") -> None:
    """Download ``url`` to ``path`` unless the file is already there (atomic: no half files)."""
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    logger.info("Downloading the %s model to %s …", name, path)
    tmp = path + ".part"
    try:
        urllib.request.urlretrieve(url, tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
