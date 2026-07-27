"""Root pytest config — ignore Hermes plugin entry modules as tests."""

collect_ignore = [
    "__init__.py",
    "hooks.py",
    "tools.py",
    "plugin_loader.py",
]
