from __future__ import annotations

import json
from pathlib import Path

import pytest
from choras_fa_adapter.config import AdapterConfig
from choras_fa_adapter.errors import AdapterError
from choras_fa_adapter.models import FaRunStatus, MeshInlinePayload
from choras_fa_adapter.orchestrator import _progress_from_status, run_from_choras_json


class FakeClient:
    def __init__(self, statuses: list[FaRunStatus]):
        self._statuses = statuses
        self._idx = 0

    def submit_run(self, body: dict) -> object:
        class Submit:
            run_id = "run-1"
            correlation_id = "corr-1"

        return Submit()

    def get_run_status(self, run_id: str) -> FaRunStatus:
        status = self._statuses[self._idx]
        if self._idx < len(self._statuses) - 1:
            self._idx += 1
        return status

    def close(self) -> None:
        return None


@pytest.fixture
def valid_json(tmp_path: Path) -> Path:
    msh = tmp_path / "mesh.msh"
    msh.write_text("dummy", encoding="utf-8")
    payload = {
        "msh_path": str(msh),
        "frequencies": [125, 250, 500],
        "absorption_coefficients": {"wall": [0.1, 0.2, 0.3]},
        "simulationSettings": {
            "fa_c0_mps": 343.0,
            "fa_rho0_kgpm3": 1.2,
            "fa_ir_length_s": 1.5,
            "fa_max_gridstep_cm": 2.0,
            "fa_freq_limit_hz": 4000.0,
            "iterations": 100,
        },
        "results": [
            {
                "sourceX": 2.0,
                "sourceY": 2.0,
                "sourceZ": 1.5,
                "responses": [{"x": 1.0, "y": 1.0, "z": 1.5}],
            }
        ],
    }
    json_path = tmp_path / "input.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    return json_path


def _config() -> AdapterConfig:
    return AdapterConfig(base_url="http://example", token="token")


def test_orchestrator_success(
    monkeypatch: pytest.MonkeyPatch, valid_json: Path
) -> None:
    def fake_mesh(_msh_path: str) -> list[MeshInlinePayload]:
        return [
            MeshInlinePayload(
                mesh_id="mesh-0", name="mesh", ply_b64="ZGF0YQ==", decoded_size_bytes=4
            )
        ]

    statuses = [
        FaRunStatus("queued", 0.1, None, None, "corr-1"),
        FaRunStatus("running", 0.6, None, None, "corr-1"),
        FaRunStatus(
            "completed",
            1.0,
            {
                "mode": "local",
                "status": "completed",
                "worker": {
                    "receivers": [
                        {
                            "x": 1.0,
                            "y": 1.0,
                            "z": 1.5,
                            "corrected": [0.1, 0.2, 0.3],
                            "uncorrected": [0.09, 0.19, 0.29],
                        }
                    ]
                },
            },
            None,
            "corr-1",
        ),
    ]

    monkeypatch.setattr(
        "choras_fa_adapter.orchestrator.build_inline_mesh_payload", fake_mesh
    )
    monkeypatch.setattr(
        "choras_fa_adapter.orchestrator.extract_required_boundaries",
        lambda _msh_path: {"wall"},
    )
    monkeypatch.setattr(
        "choras_fa_adapter.orchestrator.FaClient", lambda _cfg: FakeClient(statuses)
    )

    outcome = run_from_choras_json(str(valid_json), config=_config())
    assert outcome.status == "completed"
    assert outcome.run_id == "run-1"

    final_json = json.loads(valid_json.read_text(encoding="utf-8"))
    assert final_json["results"][0]["percentage"] == 100


def test_orchestrator_failed_status(
    monkeypatch: pytest.MonkeyPatch, valid_json: Path
) -> None:
    def fake_mesh(_msh_path: str) -> list[MeshInlinePayload]:
        return [
            MeshInlinePayload(
                mesh_id="mesh-0", name="mesh", ply_b64="ZGF0YQ==", decoded_size_bytes=4
            )
        ]

    statuses = [
        FaRunStatus(
            "failed",
            0.2,
            None,
            {
                "detail": (
                    "ASYNC worker_execution 500: "
                    "choras_local_execution_failed: RuntimeError: boom"
                )
            },
            "corr-1",
        )
    ]

    monkeypatch.setattr(
        "choras_fa_adapter.orchestrator.build_inline_mesh_payload", fake_mesh
    )
    monkeypatch.setattr(
        "choras_fa_adapter.orchestrator.extract_required_boundaries",
        lambda _msh_path: {"wall"},
    )
    monkeypatch.setattr(
        "choras_fa_adapter.orchestrator.FaClient",
        lambda _cfg: FakeClient(statuses),
    )

    with pytest.raises(AdapterError) as exc:
        run_from_choras_json(str(valid_json), config=_config())

    assert exc.value.stage == "fa_status_poll"
    expected_message = (
        "ASYNC worker_execution 500: "
        "choras_local_execution_failed: RuntimeError: boom"
    )
    assert (
        str(exc.value)
        == expected_message
    )
    final_json = json.loads(valid_json.read_text(encoding="utf-8"))
    assert "fa_status_poll" in final_json["results"][0]["error"]["message"]
    assert final_json["results"][0]["error"]["correlation_id"] == "corr-1"


def test_orchestrator_missing_required_boundary_absorption(
    monkeypatch: pytest.MonkeyPatch,
    valid_json: Path,
) -> None:
    def fake_mesh(_msh_path: str) -> list[MeshInlinePayload]:
        return [
            MeshInlinePayload(
                mesh_id="mesh-0",
                name="mesh",
                ply_b64="ZGF0YQ==",
                decoded_size_bytes=4,
            )
        ]

    monkeypatch.setattr(
        "choras_fa_adapter.orchestrator.build_inline_mesh_payload", fake_mesh
    )
    monkeypatch.setattr(
        "choras_fa_adapter.orchestrator.extract_required_boundaries",
        lambda _msh_path: {"wall", "ceiling"},
    )

    with pytest.raises(AdapterError) as exc:
        run_from_choras_json(str(valid_json), config=_config())

    assert exc.value.stage == "material_mapping"
    final_json = json.loads(valid_json.read_text(encoding="utf-8"))
    assert "missing absorption entry for boundaries" in (
        final_json["results"][0]["error"]["message"]
    )


def test_orchestrator_logs_poll_status_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    valid_json: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fake_mesh(_msh_path: str) -> list[MeshInlinePayload]:
        return [
            MeshInlinePayload(
                mesh_id="mesh-0",
                name="mesh",
                ply_b64="ZGF0YQ==",
                decoded_size_bytes=4,
            )
        ]

    statuses = [
        FaRunStatus("queued", None, None, None, "corr-1"),
        FaRunStatus("running", 0.5, None, None, "corr-1"),
        FaRunStatus(
            "completed",
            1.0,
            {
                "mode": "local",
                "status": "completed",
                "worker": {
                    "receivers": [
                        {
                            "x": 1.0,
                            "y": 1.0,
                            "z": 1.5,
                            "corrected": [0.1, 0.2, 0.3],
                            "uncorrected": [0.09, 0.19, 0.29],
                        }
                    ]
                },
            },
            None,
            "corr-1",
        ),
    ]

    monkeypatch.setattr(
        "choras_fa_adapter.orchestrator.build_inline_mesh_payload", fake_mesh
    )
    monkeypatch.setattr(
        "choras_fa_adapter.orchestrator.extract_required_boundaries",
        lambda _msh_path: {"wall"},
    )
    monkeypatch.setattr(
        "choras_fa_adapter.orchestrator.FaClient", lambda _cfg: FakeClient(statuses)
    )

    with caplog.at_level("INFO", logger="choras_fa_adapter.orchestrator"):
        run_from_choras_json(
            str(valid_json),
            config=AdapterConfig(
                base_url="http://example",
                token="token",
                log_poll_status=True,
            ),
        )

    messages = [record.getMessage() for record in caplog.records]
    assert any("status=queued progress=None" in msg for msg in messages)
    assert any("status=running progress=0.5" in msg for msg in messages)


def test_orchestrator_uses_configured_poll_interval(
    monkeypatch: pytest.MonkeyPatch,
    valid_json: Path,
) -> None:
    def fake_mesh(_msh_path: str) -> list[MeshInlinePayload]:
        return [
            MeshInlinePayload(
                mesh_id="mesh-0",
                name="mesh",
                ply_b64="ZGF0YQ==",
                decoded_size_bytes=4,
            )
        ]

    statuses = [
        FaRunStatus("queued", None, None, None, "corr-1"),
        FaRunStatus("running", 0.5, None, None, "corr-1"),
        FaRunStatus(
            "completed",
            1.0,
            {
                "mode": "local",
                "status": "completed",
                "worker": {
                    "receivers": [
                        {
                            "x": 1.0,
                            "y": 1.0,
                            "z": 1.5,
                            "corrected": [0.1, 0.2, 0.3],
                            "uncorrected": [0.09, 0.19, 0.29],
                        }
                    ]
                },
            },
            None,
            "corr-1",
        ),
    ]
    sleep_calls: list[float] = []

    monkeypatch.setattr(
        "choras_fa_adapter.orchestrator.build_inline_mesh_payload", fake_mesh
    )
    monkeypatch.setattr(
        "choras_fa_adapter.orchestrator.extract_required_boundaries",
        lambda _msh_path: {"wall"},
    )
    monkeypatch.setattr(
        "choras_fa_adapter.orchestrator.FaClient", lambda _cfg: FakeClient(statuses)
    )
    monkeypatch.setattr(
        "choras_fa_adapter.orchestrator.time.sleep",
        lambda seconds: sleep_calls.append(seconds),
    )

    run_from_choras_json(
        str(valid_json),
        config=AdapterConfig(
            base_url="http://example",
            token="token",
            poll_interval_seconds=1.25,
        ),
    )

    assert sleep_calls == [1.25, 1.25]


def test_progress_from_status_phase_floor_and_ceiling() -> None:
    assert _progress_from_status(None) == 3
    assert _progress_from_status(0.0) == 3
    assert _progress_from_status(1.0) == 99


def test_progress_from_status_midpoint_maps_to_poll_band() -> None:
    assert _progress_from_status(0.5) == 51
