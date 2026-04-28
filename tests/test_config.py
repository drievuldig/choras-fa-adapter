from __future__ import annotations

from pathlib import Path

import pytest
from choras_fa_adapter.config import load_config
from choras_fa_adapter.errors import AdapterError


def _set_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHORAS_FA_BASE_URL", "https://fa.example")


def _clear_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHORAS_FA_TOKEN", raising=False)
    monkeypatch.delenv("CHORAS_FA_CREDENTIALS_FILE", raising=False)


def _clear_base_url_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHORAS_FA_BASE_URL", raising=False)
    monkeypatch.delenv("CHORAS_FA_CONFIG_FILE", raising=False)


def test_load_config_prefers_env_token_over_credentials_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    creds = tmp_path / "credentials"
    creds.write_text("token=file-token\n", encoding="utf-8")

    _set_base_url(monkeypatch)
    monkeypatch.setenv("CHORAS_FA_TOKEN", "env-token")
    monkeypatch.setenv("CHORAS_FA_CREDENTIALS_FILE", str(creds))

    config = load_config()
    assert config.token == "env-token"


def test_load_config_uses_credentials_file_plain_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    creds = tmp_path / "credentials"
    creds.write_text("plain-token\n", encoding="utf-8")

    _set_base_url(monkeypatch)
    _clear_token_env(monkeypatch)
    monkeypatch.setenv("CHORAS_FA_CREDENTIALS_FILE", str(creds))

    config = load_config()
    assert config.token == "plain-token"


def test_load_config_uses_credentials_file_key_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    creds = tmp_path / "credentials"
    creds.write_text(
        "# comment\nexport CHORAS_FA_TOKEN=key-value-token\n",
        encoding="utf-8",
    )

    _set_base_url(monkeypatch)
    _clear_token_env(monkeypatch)
    monkeypatch.setenv("CHORAS_FA_CREDENTIALS_FILE", str(creds))

    config = load_config()
    assert config.token == "key-value-token"


def test_load_config_missing_token_in_env_and_credentials_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    creds = tmp_path / "credentials"
    creds.write_text("# no token here\n", encoding="utf-8")

    _set_base_url(monkeypatch)
    _clear_token_env(monkeypatch)
    monkeypatch.setenv("CHORAS_FA_CREDENTIALS_FILE", str(creds))

    with pytest.raises(AdapterError) as exc:
        load_config()

    assert exc.value.stage == "environment"
    assert "missing CHORAS_FA_TOKEN" in str(exc.value)


def test_load_config_missing_base_url_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    creds = tmp_path / "credentials"
    creds.write_text("token=abc\n", encoding="utf-8")

    _clear_base_url_env(monkeypatch)
    _clear_token_env(monkeypatch)
    monkeypatch.setenv("CHORAS_FA_CREDENTIALS_FILE", str(creds))
    monkeypatch.setenv("CHORAS_FA_CONFIG_FILE", str(tmp_path / "missing-config"))

    with pytest.raises(AdapterError) as exc:
        load_config()

    assert exc.value.stage == "environment"
    assert "missing CHORAS_FA_BASE_URL" in str(exc.value)


def test_load_config_uses_config_file_base_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    creds = tmp_path / "credentials"
    cfg = tmp_path / "config"
    creds.write_text("token=abc\n", encoding="utf-8")
    cfg.write_text("CHORAS_FA_BASE_URL=http://localhost:8000\n", encoding="utf-8")

    _clear_base_url_env(monkeypatch)
    _clear_token_env(monkeypatch)
    monkeypatch.setenv("CHORAS_FA_CREDENTIALS_FILE", str(creds))
    monkeypatch.setenv("CHORAS_FA_CONFIG_FILE", str(cfg))

    config = load_config()
    assert config.base_url == "http://localhost:8000"


def test_load_config_prefers_env_base_url_over_config_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    creds = tmp_path / "credentials"
    cfg = tmp_path / "config"
    creds.write_text("token=abc\n", encoding="utf-8")
    cfg.write_text("CHORAS_FA_BASE_URL=http://localhost:8000\n", encoding="utf-8")

    _set_base_url(monkeypatch)
    _clear_token_env(monkeypatch)
    monkeypatch.setenv("CHORAS_FA_CREDENTIALS_FILE", str(creds))
    monkeypatch.setenv("CHORAS_FA_CONFIG_FILE", str(cfg))

    config = load_config()
    assert config.base_url == "https://fa.example"


def test_load_config_default_auth_refresh_and_token_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    creds = tmp_path / "credentials"
    creds.write_text("token=abc\n", encoding="utf-8")

    _set_base_url(monkeypatch)
    _clear_token_env(monkeypatch)
    monkeypatch.setenv("CHORAS_FA_CREDENTIALS_FILE", str(creds))

    config = load_config()
    assert config.auth_refresh_path == "/auth/refresh"
    assert config.token_mode == "auto"
    assert config.log_poll_status is False


def test_load_config_enables_poll_status_logging(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    creds = tmp_path / "credentials"
    creds.write_text("token=abc\n", encoding="utf-8")

    _set_base_url(monkeypatch)
    _clear_token_env(monkeypatch)
    monkeypatch.setenv("CHORAS_FA_CREDENTIALS_FILE", str(creds))
    monkeypatch.setenv("CHORAS_FA_LOG_POLL_STATUS", "true")

    config = load_config()
    assert config.log_poll_status is True


def test_load_config_invalid_token_mode_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    creds = tmp_path / "credentials"
    creds.write_text("token=abc\n", encoding="utf-8")

    _set_base_url(monkeypatch)
    _clear_token_env(monkeypatch)
    monkeypatch.setenv("CHORAS_FA_CREDENTIALS_FILE", str(creds))
    monkeypatch.setenv("CHORAS_FA_TOKEN_MODE", "nope")

    with pytest.raises(AdapterError) as exc:
        load_config()

    assert exc.value.stage == "environment"
    assert "invalid CHORAS_FA_TOKEN_MODE" in str(exc.value)
