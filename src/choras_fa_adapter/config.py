from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import stage_error


@dataclass(frozen=True)
class AdapterConfig:
    base_url: str
    token: str
    submit_path: str = "/choras/runs"
    auth_refresh_path: str = "/auth/refresh"
    token_mode: str = "auto"
    verify_tls: bool = True
    timeout_seconds: float = 30.0
    poll_interval_seconds: float = 2.0
    max_polls: int = 300
    enable_capability_probe: bool = False
    log_poll_status: bool = False


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _read_token_from_credentials_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise stage_error(
            "environment",
            f"failed reading credentials file: {path}",
            cause=exc,
        ) from exc

    valid_keys = {"token", "fa_token", "choras_fa_token"}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        normalized = line
        if normalized.startswith("export "):
            normalized = normalized[len("export ") :].strip()

        if "=" in normalized:
            key, value = normalized.split("=", 1)
            if key.strip().lower() in valid_keys:
                return value.strip().strip('"').strip("'")
            continue

        return normalized

    return ""


def _read_base_url_from_config_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise stage_error(
            "environment",
            f"failed reading config file: {path}",
            cause=exc,
        ) from exc

    valid_keys = {
        "choras_fa_base_url",
        "fa_base_url",
        "base_url",
        "api_url",
        "url",
    }
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        normalized = line
        if normalized.startswith("export "):
            normalized = normalized[len("export ") :].strip()

        if "=" not in normalized:
            continue

        key, value = normalized.split("=", 1)
        if key.strip().lower() in valid_keys:
            return value.strip().strip('"').strip("'")

    return ""


def load_config() -> AdapterConfig:
    base_url = os.getenv("CHORAS_FA_BASE_URL", "").strip()
    token = os.getenv("CHORAS_FA_TOKEN", "").strip()

    config_file = Path(
        os.getenv("CHORAS_FA_CONFIG_FILE", "~/.config/fa-sdk/config")
    ).expanduser()
    if not base_url:
        base_url = _read_base_url_from_config_file(config_file)
    if not base_url:
        raise stage_error(
            "environment",
            "missing CHORAS_FA_BASE_URL and no base URL found in config file",
        )

    credentials_file = Path(
        os.getenv("CHORAS_FA_CREDENTIALS_FILE", "~/.config/fa-sdk/credentials")
    ).expanduser()

    if not token:
        token = _read_token_from_credentials_file(credentials_file)
    if not token:
        raise stage_error(
            "environment",
            "missing CHORAS_FA_TOKEN and no token found in credentials file",
        )

    submit_path = os.getenv("CHORAS_FA_SUBMIT_PATH", "/choras/runs").strip()
    auth_refresh_path = os.getenv(
        "CHORAS_FA_AUTH_REFRESH_PATH", "/auth/refresh"
    ).strip()
    token_mode = os.getenv("CHORAS_FA_TOKEN_MODE", "auto").strip().lower()
    if token_mode not in {"auto", "access", "pat"}:
        raise stage_error(
            "environment",
            "invalid CHORAS_FA_TOKEN_MODE (expected: auto, access, pat)",
        )

    try:
        timeout_seconds = float(os.getenv("CHORAS_FA_TIMEOUT_SECONDS", "30"))
        poll_interval_seconds = float(os.getenv("CHORAS_FA_POLL_INTERVAL_SECONDS", "2"))
        max_polls = int(os.getenv("CHORAS_FA_MAX_POLLS", "300"))
    except ValueError as exc:
        raise stage_error(
            "environment", "invalid numeric configuration", cause=exc
        ) from exc

    return AdapterConfig(
        base_url=base_url.rstrip("/"),
        token=token,
        submit_path=submit_path,
        auth_refresh_path=auth_refresh_path,
        token_mode=token_mode,
        verify_tls=_env_bool("CHORAS_FA_VERIFY_TLS", True),
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        max_polls=max_polls,
        enable_capability_probe=_env_bool("CHORAS_FA_ENABLE_CAPABILITY_PROBE", False),
        log_poll_status=_env_bool("CHORAS_FA_LOG_POLL_STATUS", False),
    )
