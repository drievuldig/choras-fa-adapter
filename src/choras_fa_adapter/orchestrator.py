from __future__ import annotations

import logging
from typing import Any

from .choras_io import load_choras_json
from .config import AdapterConfig
from .errors import AdapterError, stage_error
from .fa_client import FaClient
from .mesh import (
    build_inline_mesh_payload,
    extract_required_boundaries,
    resolve_materials,
)
from .models import AdapterOutcome
from .payload_builder import build_submit_body
from .validation import validate_input

logger = logging.getLogger(__name__)


def _progress_from_status(progress: float | None) -> int:
    if progress is None:
        return 3
    # Reserve [0,1,2] for local adapter phases and [100] for terminal success.
    return max(3, min(99, 3 + round(float(progress) * 96)))


def run_from_choras_json(json_path: str, *, config: AdapterConfig) -> AdapterOutcome:
    choras = load_choras_json(json_path)
    data = choras.data
    last_correlation_id: str | None = None

    try:
        choras.set_percentage(0)
        choras.persist()

        validate_input(data)
        choras.set_percentage(1)
        choras.persist()

        if data.get("should_cancel"):
            raise stage_error("input_validation", "execution canceled by should_cancel")

        msh_path = data["msh_path"]
        meshes = build_inline_mesh_payload(msh_path)
        required_boundaries = extract_required_boundaries(msh_path)
        materials, mesh_bindings = resolve_materials(
            data,
            required_boundaries=required_boundaries,
        )

        choras.set_percentage(2)
        choras.persist()

        body = build_submit_body(
            data,
            meshes=meshes,
            materials=materials,
            mesh_bindings=mesh_bindings,
        )

        choras.set_percentage(3)
        choras.persist()

        client = FaClient(config)
        try:
            submit = client.submit_run(body)
            last_correlation_id = submit.correlation_id
            status = client.get_run_status(submit.run_id)

            while status.status in {"queued", "running"}:
                last_correlation_id = status.correlation_id or last_correlation_id
                if config.log_poll_status:
                    logger.info(
                        "poll run_id=%s status=%s progress=%s correlation_id=%s",
                        submit.run_id,
                        status.status,
                        status.progress,
                        last_correlation_id,
                    )
                choras.set_percentage(_progress_from_status(status.progress))
                choras.persist()
                status = client.get_run_status(submit.run_id)

            correlation_id = status.correlation_id or submit.correlation_id
            last_correlation_id = correlation_id
            if status.status == "failed":
                message = "backend failure"
                if status.error:
                    for key in ("detail", "message"):
                        value = status.error.get(key)
                        if isinstance(value, str) and value.strip():
                            message = value
                            break
                raise stage_error("fa_status_poll", message)

            choras.set_percentage(100)
            if status.result is not None:
                choras.set_result_with_receiver_mapping(status.result)
            choras.persist()

            return AdapterOutcome(
                run_id=submit.run_id,
                status=status.status,
                correlation_id=correlation_id,
            )
        finally:
            client.close()

    except AdapterError as exc:
        _set_error_writeback(
            choras,
            f"{exc.stage}: {exc}",
            correlation_id=last_correlation_id,
        )
        raise
    except Exception as exc:
        _set_error_writeback(
            choras,
            f"unexpected_error: {exc}",
            correlation_id=last_correlation_id,
        )
        raise


def _set_error_writeback(
    choras: Any,
    message: str,
    *,
    correlation_id: str | None = None,
) -> None:
    try:
        choras.set_error(message, correlation_id=correlation_id)
        choras.persist()
    except Exception as write_exc:
        raise stage_error(
            "result_writeback", "failed to persist error writeback", cause=write_exc
        ) from write_exc
