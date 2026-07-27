"""Resolve OpenCode Go workspace id + auth cookie."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Union


@dataclass(frozen=True)
class GoConfig:
    workspace_id: str
    auth_cookie: str


@dataclass(frozen=True)
class ConfigNone:
    state: Literal["none"] = "none"


@dataclass(frozen=True)
class ConfigConfigured:
    config: GoConfig
    source: str
    state: Literal["configured"] = "configured"


@dataclass(frozen=True)
class ConfigIncomplete:
    state: Literal["incomplete"] = "incomplete"
    source: str = ""
    missing: str = ""


@dataclass(frozen=True)
class ConfigInvalid:
    state: Literal["invalid"] = "invalid"
    source: str = ""
    error: str = ""


ResolvedConfig = Union[ConfigNone, ConfigConfigured, ConfigIncomplete, ConfigInvalid]


def _config_file_candidates() -> list[Path]:
    paths: list[Path] = []
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        paths.append(Path(xdg) / "opencode" / "opencode-quota" / "opencode-go.json")
    home = Path.home()
    paths.append(home / ".config" / "opencode" / "opencode-quota" / "opencode-go.json")
    return paths


def resolve_from_env(env: Optional[dict[str, str]] = None) -> Optional[ResolvedConfig]:
    e = env if env is not None else os.environ
    workspace_id = (e.get("OPENCODE_GO_WORKSPACE_ID") or "").strip()
    auth_cookie = (e.get("OPENCODE_GO_AUTH_COOKIE") or "").strip()
    if not workspace_id and not auth_cookie:
        return None
    if workspace_id and auth_cookie:
        return ConfigConfigured(
            config=GoConfig(workspace_id=workspace_id, auth_cookie=auth_cookie),
            source="env",
        )
    return ConfigIncomplete(
        source="env",
        missing="OPENCODE_GO_AUTH_COOKIE" if workspace_id else "OPENCODE_GO_WORKSPACE_ID",
    )


def _read_config_file(path: Path) -> ResolvedConfig:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ConfigNone()
    except json.JSONDecodeError as exc:
        return ConfigInvalid(source=str(path), error=f"Failed to parse JSON: {exc.msg}")
    except OSError as exc:
        return ConfigInvalid(source=str(path), error=f"Failed to read config file: {exc}")

    if not isinstance(data, dict):
        return ConfigInvalid(source=str(path), error="Config file must contain a JSON object")

    workspace_id = str(data.get("workspaceId") or "").strip()
    auth_cookie = str(data.get("authCookie") or "").strip()
    if workspace_id and auth_cookie:
        return ConfigConfigured(
            config=GoConfig(workspace_id=workspace_id, auth_cookie=auth_cookie),
            source=str(path),
        )
    missing = "workspaceId" if not workspace_id else "authCookie"
    return ConfigIncomplete(source=str(path), missing=missing)


def resolve_config(
    env: Optional[dict[str, str]] = None,
    config_paths: Optional[list[Path]] = None,
) -> ResolvedConfig:
    """Env wins over JSON file. Mirrors opencode-quota resolveOpenCodeGoConfig."""
    env_result = resolve_from_env(env)
    if env_result is not None:
        return env_result

    for path in config_paths if config_paths is not None else _config_file_candidates():
        if not path.exists():
            continue
        result = _read_config_file(path)
        if result.state == "none":
            continue
        return result
    return ConfigNone()
