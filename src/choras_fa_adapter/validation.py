from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import stage_error

REQUIRED_SIM_FIELDS = {
    "simulationSettings",
    "results",
    "absorption_coefficients",
    "msh_path",
}

REQUIRED_SIMULATION_SETTINGS_FIELDS = {
    "fa_c0_mps",
    "fa_rho0_kgpm3",
    "fa_ir_length_s",
    "fa_max_gridstep_cm",
    "fa_freq_limit_hz",
}


def validate_input(data: dict[str, Any]) -> None:
    missing = [key for key in REQUIRED_SIM_FIELDS if key not in data]
    if missing:
        raise stage_error(
            "input_validation", f"missing required fields: {', '.join(sorted(missing))}"
        )

    msh_path = data.get("msh_path")
    if not isinstance(msh_path, str) or not msh_path.strip():
        raise stage_error("input_validation", "msh_path must be a non-empty string")
    if not Path(msh_path).exists():
        raise stage_error("input_validation", f"msh_path does not exist: {msh_path}")

    coeffs = data.get("absorption_coefficients")
    if not isinstance(coeffs, dict) or not coeffs:
        raise stage_error(
            "input_validation", "absorption_coefficients must be a non-empty object"
        )

    simulation_settings = data.get("simulationSettings")
    if not isinstance(simulation_settings, dict) or not simulation_settings:
        raise stage_error(
            "input_validation", "simulationSettings must be a non-empty object"
        )

    missing_simulation_settings = [
        key
        for key in sorted(REQUIRED_SIMULATION_SETTINGS_FIELDS)
        if key not in simulation_settings
    ]
    if missing_simulation_settings:
        raise stage_error(
            "input_validation",
            "missing required simulationSettings fields: "
            + ", ".join(missing_simulation_settings),
        )

    for key in REQUIRED_SIMULATION_SETTINGS_FIELDS:
        value = simulation_settings.get(key)
        if not isinstance(value, int | float):
            raise stage_error(
                "input_validation",
                f"simulationSettings.{key} must be numeric",
            )

    for boundary, vec in coeffs.items():
        if not isinstance(boundary, str) or not boundary:
            raise stage_error(
                "input_validation", "absorption boundary keys must be strings"
            )
        if not isinstance(vec, list) or not vec:
            raise stage_error(
                "input_validation",
                f"absorption for {boundary} must be a non-empty list",
            )
        for entry in vec:
            if not isinstance(entry, int | float):
                raise stage_error(
                    "input_validation",
                    f"absorption for {boundary} has non-numeric value",
                )
            if entry < 0 or entry > 1:
                raise stage_error(
                    "input_validation", f"absorption for {boundary} out of range [0,1]"
                )

    results = data.get("results")
    if not isinstance(results, list) or not results:
        raise stage_error("input_validation", "results must be a non-empty list")

    found_source = False
    found_receivers = False
    for item in results:
        if not isinstance(item, dict):
            raise stage_error("input_validation", "results entries must be objects")
        if all(k in item for k in ("sourceX", "sourceY", "sourceZ")):
            found_source = True
        if isinstance(item.get("responses"), list) and item["responses"]:
            found_receivers = True

    if not found_source:
        raise stage_error(
            "input_validation",
            "results missing source position (sourceX/sourceY/sourceZ)",
        )
    if not found_receivers:
        raise stage_error(
            "input_validation",
            "results missing receiver definitions (responses)",
        )
