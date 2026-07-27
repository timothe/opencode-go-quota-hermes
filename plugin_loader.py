"""Shared Hermes-style plugin loader for tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGE_NAME = "opencode_go_quota"


def load_plugin_module():
    if PACKAGE_NAME in sys.modules and hasattr(sys.modules[PACKAGE_NAME], "register"):
        return sys.modules[PACKAGE_NAME]
    init_file = ROOT / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME,
        init_file,
        submodule_search_locations=[str(ROOT)],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    module.__package__ = PACKAGE_NAME
    module.__path__ = [str(ROOT)]  # type: ignore[attr-defined]
    sys.modules[PACKAGE_NAME] = module
    spec.loader.exec_module(module)
    return module
