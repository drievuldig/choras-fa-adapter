from __future__ import annotations

from pathlib import Path

import pytest
from choras_fa_adapter.errors import AdapterError
from choras_fa_adapter.validation import validate_input


def _valid_input(tmp_path: Path) -> dict:
    msh = tmp_path / "mesh.msh"
    msh.write_text("dummy", encoding="utf-8")
    return {
        "msh_path": str(msh),
        "absorption_coefficients": {"wall": [0.1, 0.2, 0.3]},
        "simulationSettings": {
            "fa_c0_mps": 343.0,
            "fa_rho0_kgpm3": 1.2,
            "fa_ir_length_s": 1.5,
            "fa_max_gridstep_cm": 2.0,
            "fa_freq_limit_hz": 4000.0,
            "frequency": 500,
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


def test_validate_input_happy_path(tmp_path: Path) -> None:
    validate_input(_valid_input(tmp_path))


def test_validate_input_missing_field(tmp_path: Path) -> None:
    data = _valid_input(tmp_path)
    del data["msh_path"]

    with pytest.raises(AdapterError) as exc:
        validate_input(data)

    assert exc.value.stage == "input_validation"
    assert "missing required fields" in str(exc.value)


def test_validate_input_invalid_absorption_value(tmp_path: Path) -> None:
    data = _valid_input(tmp_path)
    data["absorption_coefficients"]["wall"] = [1.2]

    with pytest.raises(AdapterError) as exc:
        validate_input(data)

    assert exc.value.stage == "input_validation"
    assert "out of range" in str(exc.value)


def test_validate_input_missing_simulation_param_field(tmp_path: Path) -> None:
    data = _valid_input(tmp_path)
    del data["simulationSettings"]["fa_freq_limit_hz"]

    with pytest.raises(AdapterError) as exc:
        validate_input(data)

    assert exc.value.stage == "input_validation"
    assert "missing required simulationSettings fields" in str(exc.value)


def test_validate_input_invalid_simulation_param_type(tmp_path: Path) -> None:
    data = _valid_input(tmp_path)
    data["simulationSettings"]["fa_c0_mps"] = "fast"

    with pytest.raises(AdapterError) as exc:
        validate_input(data)

    assert exc.value.stage == "input_validation"
    assert "simulationSettings.fa_c0_mps must be numeric" in str(exc.value)


@pytest.mark.parametrize(
    ("key", "bad_value"),
    [
        ("fa_c0_mps", 299.9),       # below min 300
        ("fa_c0_mps", 400.1),       # above max 400
        ("fa_rho0_kgpm3", 1.09),    # below min 1.1
        ("fa_rho0_kgpm3", 1.31),    # above max 1.3
        ("fa_ir_length_s", 0.0),    # exclusive lower bound (must be > 0)
        ("fa_ir_length_s", 10.1),   # above max 10
        ("fa_max_gridstep_cm", 0.9),  # below min 1.0
        ("fa_max_gridstep_cm", 10.1), # above max 10
        ("fa_freq_limit_hz", 499.9),  # below min 500
        ("fa_freq_limit_hz", 20001.0),  # above max 20000
    ],
)
def test_validate_simulation_settings_range(
    tmp_path: Path, key: str, bad_value: float
) -> None:
    data = _valid_input(tmp_path)
    data["simulationSettings"][key] = bad_value

    with pytest.raises(AdapterError) as exc:
        validate_input(data)

    assert exc.value.stage == "input_validation"
    assert key in str(exc.value)
