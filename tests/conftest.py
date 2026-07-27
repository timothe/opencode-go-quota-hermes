"""Load plugin package once for the test session."""

from __future__ import annotations

import pytest

from plugin_loader import PACKAGE_NAME, load_plugin_module

__all__ = ["PACKAGE_NAME", "load_plugin_module"]


@pytest.fixture(scope="session", autouse=True)
def _load_plugin_package():
    load_plugin_module()
