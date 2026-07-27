from __future__ import annotations

import json
from pathlib import Path

from quota.config import resolve_config, resolve_from_env


def test_env_both_set():
    r = resolve_from_env(
        {"OPENCODE_GO_WORKSPACE_ID": "ws", "OPENCODE_GO_AUTH_COOKIE": "tok"}
    )
    assert r is not None
    assert r.state == "configured"
    assert r.config.workspace_id == "ws"
    assert r.source == "env"


def test_env_incomplete():
    r = resolve_from_env({"OPENCODE_GO_WORKSPACE_ID": "ws"})
    assert r is not None
    assert r.state == "incomplete"
    assert r.missing == "OPENCODE_GO_AUTH_COOKIE"


def test_env_neither_returns_none():
    assert resolve_from_env({}) is None


def test_env_overrides_file(tmp_path: Path, monkeypatch):
    path = tmp_path / "opencode-go.json"
    path.write_text(json.dumps({"workspaceId": "file-ws", "authCookie": "file-tok"}))
    monkeypatch.setenv("OPENCODE_GO_WORKSPACE_ID", "env-ws")
    monkeypatch.setenv("OPENCODE_GO_AUTH_COOKIE", "env-tok")
    r = resolve_config(config_paths=[path])
    assert r.state == "configured"
    assert r.config.workspace_id == "env-ws"
    assert r.source == "env"


def test_file_configured(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENCODE_GO_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("OPENCODE_GO_AUTH_COOKIE", raising=False)
    path = tmp_path / "opencode-go.json"
    path.write_text(json.dumps({"workspaceId": "ws", "authCookie": "tok"}))
    r = resolve_config(env={}, config_paths=[path])
    assert r.state == "configured"
    assert r.source == str(path)


def test_file_incomplete(tmp_path: Path):
    path = tmp_path / "opencode-go.json"
    path.write_text(json.dumps({"workspaceId": "ws"}))
    r = resolve_config(env={}, config_paths=[path])
    assert r.state == "incomplete"
    assert r.missing == "authCookie"


def test_file_invalid_json(tmp_path: Path):
    path = tmp_path / "opencode-go.json"
    path.write_text("{not json")
    r = resolve_config(env={}, config_paths=[path])
    assert r.state == "invalid"


def test_missing_everywhere():
    r = resolve_config(env={}, config_paths=[Path("/nonexistent/opencode-go.json")])
    assert r.state == "none"
