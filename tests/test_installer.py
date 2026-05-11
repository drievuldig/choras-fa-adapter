from __future__ import annotations

import json
from pathlib import Path

from choras_fa_adapter.installer import install_interface, install_settings_boilerplate


def test_install_interface_dry_run(tmp_path: Path) -> None:
    sim_backend = tmp_path / "simulation-backend"
    sim_backend.mkdir(parents=True)

    result = install_interface(
        target=tmp_path,
        method="fa",
        force=False,
        dry_run=True,
    )

    assert result.success is True
    assert result.exit_code == 0
    assert any("dry-run" in line for line in result.messages)
    assert not (
        sim_backend / "fa_method" / "fa_interface" / "FAinterface.py"
    ).exists()


def test_install_interface_missing_sim_backend_dir(tmp_path: Path) -> None:
    # target exists but simulation-backend subdir is absent
    result = install_interface(
        target=tmp_path,
        method="fa",
        force=False,
        dry_run=False,
    )

    assert result.success is False
    assert result.exit_code == 2
    assert any("simulation backend directory not found" in m for m in result.messages)


def test_install_interface_writes_files(tmp_path: Path) -> None:
    sim_backend = tmp_path / "simulation-backend"
    sim_backend.mkdir(parents=True)

    result = install_interface(
        target=tmp_path,
        method="fa",
        force=False,
        dry_run=False,
    )

    method_pkg = sim_backend / "fa_method"
    interface_pkg = method_pkg / "fa_interface"
    interface_path = interface_pkg / "FAinterface.py"
    init_path = interface_pkg / "__init__.py"
    method_init_path = method_pkg / "__init__.py"

    assert result.success is True
    assert result.exit_code == 0
    assert interface_path.exists()
    assert init_path.exists()
    assert method_init_path.exists()

    init_text = init_path.read_text(encoding="utf-8")
    assert "from .FAinterface import fa_method" in init_text

    interface_text = interface_path.read_text(encoding="utf-8")
    assert 'json_path = os.environ.get("JSON_PATH")' in interface_text
    assert 'raise stage_error("environment", "JSON_PATH environment variable is required")' in interface_text
    assert "def _write_success(path: Path, *, status: str) -> None:" in interface_text
    assert 'first["percentage"] = 100' in interface_text
    assert "if __name__ == \"__main__\":" in interface_text
    assert "main()" in interface_text
    assert '_write_pressure_csv(path)' in interface_text
    assert 'import pandas as pd' in interface_text
    assert 'df.to_csv(csv_path, index=False)' in interface_text
    assert 'pressure_values = data["results"][0]["responses"][0]["receiverResults"]' in interface_text
    assert 'impulse_length = float(data["simulationSettings"]["fa_ir_length_s"])' in interface_text
    assert 'step = impulse_length / len(pressure)' in interface_text
    assert 't_values = [idx * step for idx in range(len(pressure))]' in interface_text
    assert '"missing required receiverResults/fa_ir_length_s for pressure CSV"' in interface_text
    assert '"receiverResults is empty"' in interface_text
    assert '"fa_ir_length_s must be > 0"' in interface_text
    assert 'path.stem + "_pressure.csv"' in interface_text
    assert 'raise stage_error(' in interface_text
    assert '"result_export", "failed to export CHORAS result files"' in interface_text
    assert 'except AdapterError as exc:' in interface_text
    assert (
        '_write_failure(path, f"{exc.stage}: {exc}")\n        raise'
        in interface_text
    )
    assert 'traceback.print_exc()\n        raise' in interface_text


def test_install_interface_import_dedup(tmp_path: Path) -> None:
    sim_backend = tmp_path / "simulation-backend"
    sim_backend.mkdir(parents=True)

    first = install_interface(
        target=tmp_path,
        method="fa",
        force=False,
        dry_run=False,
    )
    assert first.success is True

    second = install_interface(
        target=tmp_path,
        method="fa",
        force=True,
        dry_run=False,
    )
    assert second.success is True

    init_text = (
        sim_backend / "fa_method" / "fa_interface" / "__init__.py"
    ).read_text(encoding="utf-8")
    assert init_text.count("from .FAinterface import fa_method") == 1


def test_install_settings_boilerplate_dry_run(tmp_path: Path) -> None:
    sim_backend = tmp_path / "simulation-backend"
    sim_backend.mkdir(parents=True)

    result = install_settings_boilerplate(
        target=tmp_path,
        method="fa",
        force=False,
        dry_run=True,
    )

    assert result.success is True
    assert result.exit_code == 0
    assert any("dry-run" in line for line in result.messages)
    assert any("target methods-config snippet" in line for line in result.messages)
    assert not (sim_backend / "example_settings" / "fa_setting.json").exists()


def test_install_settings_boilerplate_missing_sim_backend_dir(tmp_path: Path) -> None:
    result = install_settings_boilerplate(
        target=tmp_path,
        method="fa",
        force=False,
        dry_run=False,
    )

    assert result.success is False
    assert result.exit_code == 2
    assert any("simulation backend directory not found" in m for m in result.messages)


def test_install_settings_boilerplate_writes_schema_and_snippet(tmp_path: Path) -> None:
    sim_backend = tmp_path / "simulation-backend"
    sim_backend.mkdir(parents=True)

    result = install_settings_boilerplate(
        target=tmp_path,
        method="fa",
        force=False,
        dry_run=False,
    )

    schema_path = sim_backend / "example_settings" / "fa_setting.json"
    methods_config_path = sim_backend / "FA_methods_config.snippet.json"

    assert result.success is True
    assert result.exit_code == 0
    assert schema_path.exists()
    assert methods_config_path.exists()
    assert any("target methods-config snippet" in line for line in result.messages)

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["type"] == "simulationSettings"
    option_ids = [opt["id"] for opt in schema["options"]]
    assert "fa_c0_mps" in option_ids
    assert "fa_freq_limit_hz" in option_ids
    # every option must have required CHORAS fields
    for opt in schema["options"]:
        for field in ("name", "id", "type", "display", "min", "max", "default", "step"):
            assert field in opt, f"option {opt.get('id')} missing field {field!r}"

    methods_cfg = json.loads(methods_config_path.read_text(encoding="utf-8"))
    assert methods_cfg["simulationType"] == "FA"
    assert methods_cfg["settings"] == "fa_setting.json"
    assert methods_cfg["containerImage"] == "fa_image:latest"
    assert methods_cfg["entryFile"] == "fa_method/fa_interface/FAinterface.py"
    required_fields = (
        "description", "label", "simulationType", "containerImage", "entryFile", "settings",
        "repositoryURL", "documentationURL",
    )
    for field in required_fields:
        assert field in methods_cfg, f"methods-config snippet missing field {field!r}"
