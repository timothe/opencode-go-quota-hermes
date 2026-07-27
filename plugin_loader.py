"""Shared Hermes-style plugin loader for tests."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PACKAGE_NAME = "opencode_go_quota"


def load_plugin_module():
    if PACKAGE_NAME in sys.modules and hasattr(sys.modules[PACKAGE_NAME], "register"):
        return sys.modules[PACKAGE_NAME]

    importlib.invalidate_caches()
    import hooks as _hooks  # noqa: F401
    import tools as _tools  # noqa: F401

    init_file = ROOT / "__init__.py"
    spec = importlib.util.spec_from_file_location(PACKAGE_NAME, init_file)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE_NAME] = module
    spec.loader.exec_module(module)
    sys.modules[f"{PACKAGE_NAME}.hooks"] = sys.modules["hooks"]
    sys.modules[f"{PACKAGE_NAME}.tools"] = sys.modules["tools"]
    sys.modules[f"{PACKAGE_NAME}.quota"] = sys.modules["quota"]
    for sub in ("types", "scrape", "check", "format", "cache", "config"):
        sys.modules[f"{PACKAGE_NAME}.quota.{sub}"] = sys.modules[f"quota.{sub}"]
    return module
