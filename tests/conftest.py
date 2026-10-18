"""Make the project root importable (``import config``, ``import core``) from the tests."""

import os
import sys

# Tests always run against the defaults in config.py, never a user's config_local.py.
os.environ["AIRMOUSE_IGNORE_LOCAL_CONFIG"] = "1"
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
