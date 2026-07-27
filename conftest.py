"""Root pytest config — ignore Hermes plugin entry as a test module."""

from pathlib import Path

collect_ignore = [
    "__init__.py",
    "ogq_hooks.py",
    "ogq_tools.py",
    "plugin_loader.py",
]


def pytest_ignore_collect(collection_path: Path, config) -> bool:  # noqa: ARG001
    # Prevent treating the plugin root as a pytest Package (which imports __init__.py).
    name = collection_path.name
    if name in {"__init__.py", "ogq_hooks.py", "ogq_tools.py", "plugin_loader.py"}:
        return True
    return False
