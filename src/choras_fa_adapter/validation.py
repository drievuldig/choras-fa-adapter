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

# Limits accepted by the FA solver.
CHORAS_MIN_FREQ_LIMIT_HZ = 1000.0
CHORAS_MAX_FREQ_LIMIT_HZ = 16000.0
CHORAS_MIN_GRIDSTEP_CM = 1.0
CHORAS_MAX_GRIDSTEP_CM = 10.0
CHORAS_MIN_C0_MPS = 300.0
CHORAS_MAX_C0_MPS = 400.0
CHORAS_MIN_RHO0_KGPM3 = 1.1
CHORAS_MAX_RHO0_KGPM3 = 1.3
CHORAS_MIN_IR_LENGTH_S = 0.0  # exclusive lower bound
CHORAS_MAX_IR_LENGTH_S = 10.0

_SIM_SETTINGS_RANGES: dict[str, tuple[float | None, float | None, bool]] = {
    # key: (min, max, min_exclusive)
    "fa_c0_mps": (CHORAS_MIN_C0_MPS, CHORAS_MAX_C0_MPS, False),
    "fa_rho0_kgpm3": (CHORAS_MIN_RHO0_KGPM3, CHORAS_MAX_RHO0_KGPM3, False),
    "fa_ir_length_s": (CHORAS_MIN_IR_LENGTH_S, CHORAS_MAX_IR_LENGTH_S, True),
    "fa_max_gridstep_cm": (CHORAS_MIN_GRIDSTEP_CM, CHORAS_MAX_GRIDSTEP_CM, False),
    "fa_freq_limit_hz": (CHORAS_MIN_FREQ_LIMIT_HZ, CHORAS_MAX_FREQ_LIMIT_HZ, False),
}


def _parse_absorption_values(raw: Any, *, boundary: str) -> list[float]:
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, dict):
        values = list(raw.values())
    elif isinstance(raw, str):
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        if not parts:
            raise stage_error(
                "input_validation",
                f"absorption for {boundary} must be a non-empty list or CSV string",
            )
        values = parts
    else:
        raise stage_error(
            "input_validation",
            f"absorption for {boundary} must be a list, object, or CSV string",
        )

    if not values:
        raise stage_error(
            "input_validation",
            f"absorption for {boundary} must be a non-empty list or CSV string",
        )

    parsed: list[float] = []
    for entry in values:
        if isinstance(entry, str):
            entry = entry.strip()
            if not entry:
                raise stage_error(
                    "input_validation",
                    f"absorption for {boundary} has empty value",
                )
        if not isinstance(entry, int | float | str):
            raise stage_error(
                "input_validation",
                f"absorption for {boundary} has non-numeric value",
            )
        try:
            value = float(entry)
        except (TypeError, ValueError) as exc:
            raise stage_error(
                "input_validation",
                f"absorption for {boundary} has non-numeric value",
                cause=exc,
            ) from exc
        parsed.append(value)

    return parsed


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

    for key, (lo, hi, lo_exclusive) in _SIM_SETTINGS_RANGES.items():
        value = float(simulation_settings[key])
        lo_violated = (value <= lo) if lo_exclusive else (value < lo)  # type: ignore[operator]
        if lo_violated or (hi is not None and value > hi):
            op = ">" if lo_exclusive else ">="
            raise stage_error(
                "input_validation",
                f"simulationSettings.{key} must be {op}{lo} and <={hi}, got {value}",
            )

    for boundary, vec in coeffs.items():
        if not isinstance(boundary, str) or not boundary:
            raise stage_error(
                "input_validation", "absorption boundary keys must be strings"
            )
        parsed_values = _parse_absorption_values(vec, boundary=boundary)
        for entry in parsed_values:
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
