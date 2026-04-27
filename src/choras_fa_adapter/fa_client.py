from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import AdapterConfig
from .errors import stage_error
from .models import FaRunStatus


@dataclass(frozen=True)
class SubmitResult:
    run_id: str
    correlation_id: str | None


class FaClient:
    def __init__(self, config: AdapterConfig, client: httpx.Client | None = None):
        self._config = config
        self._owns_client = client is None
        self._access_token_cache: str | None = None
        self._client = client or httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            verify=config.verify_tls,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        stage: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            headers = {"Authorization": f"Bearer {self._get_access_token()}"}
            if method == "POST":
                response = self._client.post(path, json=body, headers=headers)
            else:
                response = self._client.get(path, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 401:
                raise stage_error(
                    stage,
                    "token invalid or expired (status 401)",
                ) from exc
            if status_code == 403:
                raise stage_error(
                    stage,
                    "token lacks required scope or account SDK access (status 403)",
                ) from exc
            raise stage_error(stage, self._http_status_message(exc)) from exc
        except httpx.HTTPError as exc:
            raise stage_error(stage, "request failed", cause=exc) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise stage_error(
                stage,
                "response body is not valid JSON",
                cause=exc,
            ) from exc

        if not isinstance(payload, dict):
            raise stage_error(stage, "response body must be a JSON object")

        return payload

    def _http_status_message(self, exc: httpx.HTTPStatusError) -> str:
        status = exc.response.status_code
        detail = self._extract_error_detail(exc.response)
        if detail:
            return f"request failed (status {status}): {detail}"
        return f"request failed (status {status})"

    def _extract_error_detail(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            primary: str | None = None
            for key in ("detail", "message", "error"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    primary = value.strip()
                    break
                if isinstance(value, list) and value:
                    primary = self._truncate(json.dumps(value, ensure_ascii=True))
                    break

            nested = payload.get("errors")
            if nested is None:
                nested = payload.get("details")

            if primary and nested is not None:
                nested_text = self._truncate(json.dumps(nested, ensure_ascii=True))
                return f"{primary}; details={nested_text}"

            if primary:
                return primary

            if nested is not None:
                return self._truncate(json.dumps(nested, ensure_ascii=True))

            return self._truncate(json.dumps(payload, ensure_ascii=True))

        text = response.text.strip()
        if text:
            return self._truncate(text)

        return ""

    @staticmethod
    def _truncate(text: str, *, limit: int = 300) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    def _get_access_token(self) -> str:
        if self._access_token_cache is not None:
            return self._access_token_cache

        token_mode = self._config.token_mode
        token = self._config.token

        if token_mode == "access":
            self._access_token_cache = token
            return token

        if token_mode == "pat" or not self._looks_like_jwt(token):
            self._access_token_cache = self._exchange_pat_for_access(token)
            return self._access_token_cache

        self._access_token_cache = token
        return token

    @staticmethod
    def _looks_like_jwt(token: str) -> bool:
        return token.count(".") == 2

    def _exchange_pat_for_access(self, pat_token: str) -> str:
        try:
            response = self._client.post(
                self._config.auth_refresh_path,
                json={"token": pat_token},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise stage_error(
                "fa_submit",
                "failed exchanging PAT for access token",
                cause=exc,
            ) from exc
        except httpx.HTTPError as exc:
            raise stage_error(
                "fa_submit",
                "failed exchanging PAT for access token",
                cause=exc,
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise stage_error(
                "fa_submit",
                "refresh response body is not valid JSON",
                cause=exc,
            ) from exc

        if not isinstance(payload, dict):
            raise stage_error(
                "fa_submit", "refresh response body must be a JSON object"
            )

        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise stage_error("fa_submit", "refresh response missing access_token")

        return access_token

    def submit_run(self, body: dict[str, Any]) -> SubmitResult:
        payload = self._request_json(
            method="POST",
            path=self._config.submit_path,
            stage="fa_submit",
            body=body,
        )

        run_id = payload.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise stage_error("fa_submit", "submit response missing run_id")

        correlation_id = payload.get("correlation_id")
        corr = correlation_id if isinstance(correlation_id, str) else None
        return SubmitResult(run_id=run_id, correlation_id=corr)

    def get_run_status(self, run_id: str) -> FaRunStatus:
        path = f"{self._config.submit_path}/{run_id}"
        payload = self._request_json(
            method="GET",
            path=path,
            stage="fa_status_poll",
        )

        status = payload.get("status")
        if status not in {"queued", "running", "completed", "failed"}:
            raise stage_error(
                "fa_status_poll", "status response contains invalid status"
            )

        progress = payload.get("progress")
        if progress is not None and not isinstance(progress, float | int):
            raise stage_error("fa_status_poll", "progress must be float or null")

        result = payload.get("result")
        error = payload.get("error")
        corr = payload.get("correlation_id")

        return FaRunStatus(
            status=status,
            progress=float(progress) if progress is not None else None,
            result=result if isinstance(result, dict) else None,
            error=error if isinstance(error, dict) else None,
            correlation_id=corr if isinstance(corr, str) else None,
        )

    def poll_until_terminal(self, run_id: str) -> FaRunStatus:
        for _ in range(self._config.max_polls):
            status = self.get_run_status(run_id)
            if status.status in {"completed", "failed"}:
                return status
            time.sleep(self._config.poll_interval_seconds)

        raise stage_error("fa_status_poll", "poll timeout exceeded")
