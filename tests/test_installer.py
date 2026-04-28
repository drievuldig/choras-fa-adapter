from __future__ import annotations

import json
from pathlib import Path

from choras_fa_adapter.installer import install_interface, install_settings_boilerplate


def test_install_interface_dry_run(tmp_path: Path) -> None:
    sim_pkg = tmp_path / "simulation-backend" / "simulation_backend"
    sim_pkg.mkdir(parents=True)

    result = install_interface(
        target=tmp_path,
        method="fa",
        force=False,
        dry_run=True,
        backup=True,
    )

    assert result.success is True
    assert result.exit_code == 0
    assert any("dry-run" in line for line in result.messages)
    assert not (sim_pkg / "FAinterface.py").exists()


def test_install_interface_missing_sim_pkg_dir(tmp_path: Path) -> None:
    # target exists but simulation-backend/simulation_backend subdir is absent
    result = install_interface(
        target=tmp_path,
        method="fa",
        force=False,
        dry_run=False,
        backup=False,
    )

    assert result.success is False
    assert result.exit_code == 2
    assert any("simulation package directory not found" in m for m in result.messages)


def test_install_interface_writes_files(tmp_path: Path) -> None:
    sim_pkg = tmp_path / "simulation-backend" / "simulation_backend"
    sim_pkg.mkdir(parents=True)

    result = install_interface(
        target=tmp_path,
        method="fa",
        force=False,
        dry_run=False,
        backup=True,
    )

    interface_path = sim_pkg / "FAinterface.py"
    init_path = sim_pkg / "__init__.py"

    assert result.success is True
    assert result.exit_code == 0
    assert interface_path.exists()
    assert init_path.exists()

    init_text = init_path.read_text(encoding="utf-8")
    assert "from .FAinterface import fa_method" in init_text

    interface_text = interface_path.read_text(encoding="utf-8")
    assert "find_input_file_in_subfolders" in interface_text
    assert "create_tmp_from_input" in interface_text
    assert "save_results" in interface_text
    assert "plot_results" in interface_text
    assert "exampleInput_FA.json" in interface_text


def test_install_interface_import_dedup(tmp_path: Path) -> None:
    sim_pkg = tmp_path / "simulation-backend" / "simulation_backend"
    sim_pkg.mkdir(parents=True)

    first = install_interface(
        target=tmp_path,
        method="fa",
        force=False,
        dry_run=False,
        backup=True,
    )
    assert first.success is True

    second = install_interface(
        target=tmp_path,
        method="fa",
        force=True,
        dry_run=False,
        backup=False,
    )
    assert second.success is True

    init_text = (sim_pkg / "__init__.py").read_text(encoding="utf-8")
    assert init_text.count("from .FAinterface import fa_method") == 1


def test_install_settings_boilerplate_dry_run(tmp_path: Path) -> None:
    result = install_settings_boilerplate(
        target=tmp_path,
        method="fa",
        force=False,
        dry_run=True,
        backup=True,
    )

    assert result.success is True
    assert result.exit_code == 0
    assert any("dry-run" in line for line in result.messages)
    assert not (tmp_path / "example_settings" / "fa_setting.json").exists()


def test_install_settings_boilerplate_writes_schema_and_snippet(tmp_path: Path) -> None:
    result = install_settings_boilerplate(
        target=tmp_path,
        method="fa",
        force=False,
        dry_run=False,
        backup=True,
    )

    schema_path = tmp_path / "example_settings" / "fa_setting.json"
    registry_path = tmp_path / "FA_simulation_settings_registration.snippet.json"
    tasktype_path = tmp_path / "FA_task_type.snippet.txt"

    assert result.success is True
    assert result.exit_code == 0
    assert schema_path.exists()
    assert registry_path.exists()
    assert tasktype_path.exists()

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["type"] == "simulationSettings"
    option_ids = [opt["id"] for opt in schema["options"]]
    assert "fa_c0_mps" in option_ids
    assert "fa_freq_limit_hz" in option_ids
    # every option must have required CHORAS fields
    for opt in schema["options"]:
        for field in ("name", "id", "type", "display", "min", "max", "default", "step"):
            assert field in opt, f"option {opt.get('id')} missing field {field!r}"

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry["simulationType"] == "FA"
    assert registry["name"] == "fa_setting.json"
    required_fields = (
        "description", "label", "name", "simulationType",
        "repositoryURL", "documentationURL",
    )
    for field in required_fields:
        assert field in registry, f"registry missing field {field!r}"

    tasktype_text = tasktype_path.read_text(encoding="utf-8")
    assert 'FA = "FA"' in tasktype_text
    assert "TaskType" in tasktype_text
