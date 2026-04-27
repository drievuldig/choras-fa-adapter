from __future__ import annotations

import json

import httpx
import pytest
from choras_fa_adapter.config import AdapterConfig
from choras_fa_adapter.errors import AdapterError
from choras_fa_adapter.fa_client import FaClient


def _config() -> AdapterConfig:
    return AdapterConfig(base_url="http://fa.local", token="token", token_mode="access")


def _client_with_handler(handler: httpx.MockTransport) -> FaClient:
    client = httpx.Client(
        base_url="http://fa.local",
        transport=handler,
        timeout=10.0,
    )
    return FaClient(_config(), client=client)


def test_submit_run_parses_expected_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/choras/runs"
        return httpx.Response(
            200,
            json={"run_id": "run-123", "correlation_id": "corr-123"},
        )

    fa_client = _client_with_handler(httpx.MockTransport(handler))
    result = fa_client.submit_run({"simulation_settings": {}, "payload": {}})

    assert result.run_id == "run-123"
    assert result.correlation_id == "corr-123"


def test_submit_run_missing_run_id_fails_fast() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"correlation_id": "corr-123"})

    fa_client = _client_with_handler(httpx.MockTransport(handler))

    with pytest.raises(AdapterError) as exc:
        fa_client.submit_run({"simulation_settings": {}, "payload": {}})

    assert exc.value.stage == "fa_submit"
    assert "run_id" in str(exc.value)


def test_get_run_status_parses_completed_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/choras/runs/run-1"
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "progress": 1.0,
                "result": {"ok": True},
                "error": None,
                "correlation_id": "corr-1",
            },
        )

    fa_client = _client_with_handler(httpx.MockTransport(handler))
    status = fa_client.get_run_status("run-1")

    assert status.status == "completed"
    assert status.progress == 1.0
    assert status.result == {"ok": True}
    assert status.correlation_id == "corr-1"


def test_get_run_status_invalid_status_fails() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "done",
                "progress": 1.0,
                "result": {},
                "error": None,
                "correlation_id": "corr-1",
            },
        )

    fa_client = _client_with_handler(httpx.MockTransport(handler))

    with pytest.raises(AdapterError) as exc:
        fa_client.get_run_status("run-1")

    assert exc.value.stage == "fa_status_poll"
    assert "invalid status" in str(exc.value)


def test_submit_unauthorized_fails_fast_with_auth_message() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    fa_client = _client_with_handler(httpx.MockTransport(handler))

    with pytest.raises(AdapterError) as exc:
        fa_client.submit_run({"simulation_settings": {}, "payload": {}})

    assert exc.value.stage == "fa_submit"
    assert "token invalid or expired" in str(exc.value)


def test_status_forbidden_fails_fast_with_auth_message() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "forbidden"})

    fa_client = _client_with_handler(httpx.MockTransport(handler))

    with pytest.raises(AdapterError) as exc:
        fa_client.get_run_status("run-1")

    assert exc.value.stage == "fa_status_poll"
    assert "lacks required scope" in str(exc.value)


def test_submit_run_auto_exchanges_pat_for_access_token() -> None:
    seen_auth_header: str | None = None
    saw_refresh = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_auth_header, saw_refresh
        if request.url.path == "/auth/refresh":
            saw_refresh = True
            assert request.method == "POST"
            assert json.loads(request.content.decode("utf-8")) == {"token": "token"}
            return httpx.Response(200, json={"access_token": "access.jwt.token"})

        seen_auth_header = request.headers.get("Authorization")
        assert request.url.path == "/choras/runs"
        return httpx.Response(
            200,
            json={"run_id": "run-123", "correlation_id": "corr-123"},
        )

    config = AdapterConfig(base_url="http://fa.local", token="token", token_mode="auto")
    client = httpx.Client(
        base_url="http://fa.local",
        transport=httpx.MockTransport(handler),
        timeout=10.0,
    )
    fa_client = FaClient(config, client=client)

    result = fa_client.submit_run({"simulation_settings": {}, "payload": {}})

    assert saw_refresh
    assert seen_auth_header == "Bearer access.jwt.token"
    assert result.run_id == "run-123"


def test_submit_422_includes_backend_validation_detail() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={"detail": "payload.receivers[0].x must be >= 0"},
        )

    fa_client = _client_with_handler(httpx.MockTransport(handler))

    with pytest.raises(AdapterError) as exc:
        fa_client.submit_run({"simulation_settings": {}, "payload": {}})

    assert exc.value.stage == "fa_submit"
    assert "status 422" in str(exc.value)
    assert "payload.receivers[0].x must be >= 0" in str(exc.value)


def test_submit_422_includes_nested_error_details() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "detail": "invalid_params",
                "errors": [{"loc": ["payload", "sources", 0, "x"], "msg": "required"}],
            },
        )

    fa_client = _client_with_handler(httpx.MockTransport(handler))

    with pytest.raises(AdapterError) as exc:
        fa_client.submit_run({"simulation_settings": {}, "payload": {}})

    message = str(exc.value)
    assert exc.value.stage == "fa_submit"
    assert "status 422" in message
    assert "invalid_params" in message
    assert "details=" in message
    assert "sources" in message
