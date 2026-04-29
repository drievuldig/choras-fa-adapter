from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .errors import stage_error


@dataclass(frozen=True)
class InstallResult:
    success: bool
    exit_code: int
    messages: list[str]


def install_settings_boilerplate(
    *,
    target: Path,
    method: str,
    force: bool,
    dry_run: bool,
    json_logs: bool = False,
) -> InstallResult:
    messages: list[str] = []

    if not target.exists() or not target.is_dir():
        return InstallResult(False, 2, [f"invalid target directory: {target}"])
    if not method.isidentifier():
        return InstallResult(False, 2, [f"invalid method name: {method!r}"])

    try:
        __import__("choras_fa_adapter")
    except Exception as exc:
        return InstallResult(False, 4, [f"environment check failed: {exc}"])

    method_upper = method.upper()

    example_settings_dir = target / "example_settings"
    schema_path = example_settings_dir / f"{method}_setting.json"
    registry_path = (  # noqa: E501
        target / f"{method_upper}_simulation_settings_registration.snippet.json"
    )

    schema_payload = _render_settings_schema_payload(method=method)
    registry_payload = _render_settings_registry_entry(method=method)

    messages.append(f"target UI schema: {schema_path}")
    messages.append(f"target registry snippet: {registry_path}")
    messages.append("TaskType update required in app/types/Task.py:")
    messages.append(f'{method_upper} = "{method_upper}"')

    if dry_run:
        messages.append("dry-run: no files written")
        return InstallResult(True, 0, messages)

    existing = [path for path in (schema_path, registry_path) if path.exists()]
    if existing and not force:
        joined = ", ".join(str(path) for path in existing)
        return InstallResult(
            False,
            3,
            messages + [f"target files already exist: {joined}; rerun with --force"],
        )

    try:
        example_settings_dir.mkdir(parents=False, exist_ok=True)

        schema_path.write_text(
            json.dumps(schema_payload, indent=2) + "\n", encoding="utf-8"
        )
        messages.append(f"wrote {schema_path}")

        registry_path.write_text(
            json.dumps(registry_payload, indent=2) + "\n", encoding="utf-8"
        )
        messages.append(f"wrote {registry_path}")
    except OSError as exc:
        err = stage_error("installer", "write failure", cause=exc)
        return InstallResult(False, 3, messages + [f"{err.stage}: {err}"])

    if json_logs:
        messages.append("json logging mode active")

    return InstallResult(True, 0, messages)


def install_interface(
    *,
    target: Path,
    method: str,
    force: bool,
    dry_run: bool,
    json_logs: bool = False,
) -> InstallResult:
    messages: list[str] = []

    if not target.exists() or not target.is_dir():
        return InstallResult(False, 2, [f"invalid target directory: {target}"])
    if not method.isidentifier():
        return InstallResult(False, 2, [f"invalid method name: {method!r}"])

    try:
        __import__("choras_fa_adapter")
    except Exception as exc:
        return InstallResult(False, 4, [f"environment check failed: {exc}"])

    method_upper = method.upper()

    # The interface lives in the Python package inside the CHORAS backend:
    #   <backend>/simulation-backend/simulation_backend/
    sim_pkg_dir = target / "simulation-backend" / "simulation_backend"
    if not sim_pkg_dir.exists() or not sim_pkg_dir.is_dir():
        return InstallResult(
            False,
            2,
            [
                f"simulation package directory not found: {sim_pkg_dir}",
                "expected layout: <backend>/simulation-backend/simulation_backend/",
            ],
        )

    interface_path = sim_pkg_dir / f"{method_upper}interface.py"
    init_path = sim_pkg_dir / "__init__.py"

    rendered = _render_interface_template(method=method)
    import_line = f"from .{method_upper}interface import {method}_method"

    messages.append(f"target interface file: {interface_path}")
    messages.append(f"target __init__.py: {init_path}")

    if dry_run:
        messages.append("dry-run: no files written")
        return InstallResult(True, 0, messages)

    if interface_path.exists() and not force:
        return InstallResult(
            False,
            3,
            messages
            + ["interface file already exists; rerun with --force to overwrite"],
        )

    try:
        interface_path.write_text(rendered, encoding="utf-8")
        messages.append(f"wrote {interface_path}")

        if init_path.exists():
            init_text = init_path.read_text(encoding="utf-8")
            if import_line not in init_text:
                suffix = "\n" if init_text and not init_text.endswith("\n") else ""
                init_path.write_text(
                    init_text + suffix + import_line + "\n", encoding="utf-8"
                )
                messages.append(f"updated {init_path}")
            else:
                messages.append(f"import already present in {init_path}")
        else:
            init_path.write_text(import_line + "\n", encoding="utf-8")
            messages.append(f"created {init_path}")
    except OSError as exc:
        err = stage_error("installer", "write failure", cause=exc)
        return InstallResult(False, 3, messages + [f"{err.stage}: {err}"])

    if json_logs:
        # Reserved for future structured event emission in CLI.
        messages.append("json logging mode active")

    return InstallResult(True, 0, messages)


def _render_interface_template(*, method: str) -> str:
    timestamp = datetime.now(UTC).isoformat()
    version = __version__
    method_upper = method.upper()
    return f'''from __future__ import annotations

# generated-by: choras-fa-adapter
# adapter-version: {version}
# generated-at: {timestamp}
# warning: local edits may be overwritten by install-interface

import json
import traceback
from pathlib import Path

from choras_fa_adapter.config import AdapterConfig, load_config
from choras_fa_adapter.errors import AdapterError, stage_error
from choras_fa_adapter.orchestrator import run_from_choras_json


def {method}_method(json_path: str) -> None:
    """CHORAS-required interface entrypoint."""
    path = Path(json_path)

    try:
        config: AdapterConfig = load_config()
        run_from_choras_json(str(path), config=config)
        from simulation_backend import save_results

        try:
            save_results(str(path))
            _write_pressure_csv(path)
        except Exception as exc:
            raise stage_error(
                "result_export", "failed to export CHORAS result files", cause=exc
            )
    except AdapterError as exc:
        _write_failure(path, f"{{exc.stage}}: {{exc}}")
        raise
    except Exception as exc:
        _write_failure(path, f"unexpected_error: {{exc}}")
        traceback.print_exc()
        raise


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("json_path", help="Path to CHORAS input JSON")
    args = parser.parse_args()
    {method}_method(args.json_path)


def _write_failure(path: Path, message: str) -> None:
    """Best-effort CHORAS-compatible failure writeback."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return

    results = data.get("results")
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict):
                item.setdefault("percentage", 0)
                item.setdefault("error", {{}})
                if isinstance(item["error"], dict):
                    item["error"]["message"] = message

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_pressure_csv(path: Path) -> None:
    """Write CHORAS-compatible pressure CSV next to JSON output."""
    import pandas as pd

    data = json.loads(path.read_text(encoding="utf-8"))
    try:
        pressure_values = data["results"][0]["responses"][0]["receiverResults"]
        impulse_length = float(data["simulationSettings"]["fa_ir_length_s"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise stage_error(
            "result_export",
            "missing required receiverResults/fa_ir_length_s for pressure CSV",
            cause=exc,
        ) from exc

    try:
        pressure = [float(v) for v in pressure_values]
    except (TypeError, ValueError) as exc:
        raise stage_error("result_export", "pressure trace contains non-numeric values") from exc
    if not pressure:
        raise stage_error("result_export", "receiverResults is empty")
    if impulse_length <= 0:
        raise stage_error("result_export", "fa_ir_length_s must be > 0")

    step = impulse_length / len(pressure)
    t_values = [idx * step for idx in range(len(pressure))]
    df = pd.DataFrame({{"t": t_values, "pressure": pressure}})
    csv_path = path.with_name(path.stem + "_pressure.csv")
    df.to_csv(csv_path, index=False)


if __name__ == "__main__":
    import os

    from simulation_backend import (
        create_tmp_from_input,
        find_input_file_in_subfolders,
        plot_results,
        save_results,
    )

    json_file_name = find_input_file_in_subfolders(
        os.path.dirname(__file__), "exampleInput_{method_upper}.json"
    )
    json_tmp_file = create_tmp_from_input(json_file_name)

    {method}_method(json_tmp_file)

    plot_results(json_tmp_file)
'''


def _render_settings_schema_payload(*, method: str) -> dict[str, object]:  # noqa: ARG001
    """Return the CHORAS simulationSettings UI schema read by the frontend."""
    return {
        "type": "simulationSettings",
        "options": [
            {
                "name": "Speed of Sound",
                "id": "fa_c0_mps",
                "type": "float",
                "display": "text",
                "min": 300.0,
                "max": 400.0,
                "default": 343.0,
                "step": 0.1,
                "endAdornment": "m/s",
            },
            {
                "name": "Air Density",
                "id": "fa_rho0_kgpm3",
                "type": "float",
                "display": "text",
                "min": 1.1,
                "max": 1.3,
                "default": 1.2,
                "step": 0.01,
                "endAdornment": "kg/m\u00b3",
            },
            {
                "name": "Impulse Response Length",
                "id": "fa_ir_length_s",
                "type": "float",
                "display": "text",
                "min": 0.1,
                "max": 10.0,
                "default": 1.5,
                "step": 0.1,
                "endAdornment": "s",
            },
            {
                "name": "Max Grid Step",
                "id": "fa_max_gridstep_cm",
                "type": "float",
                "display": "text",
                "min": 1.0,
                "max": 10.0,
                "default": 2.0,
                "step": 0.1,
                "endAdornment": "cm",
            },
            {
                "name": "Frequency Limit",
                "id": "fa_freq_limit_hz",
                "type": "float",
                "display": "text",
                "min": 1000.0,
                "max": 16000.0,
                "default": 4000.0,
                "step": 100.0,
                "endAdornment": "Hz",
            },
        ],
    }


def _render_settings_registry_entry(*, method: str) -> dict[str, object]:
    """Return the entry to paste into simulation_settings.json."""
    method_upper = method.upper()
    return {
        "description": "Finite-difference time-domain room acoustics simulation via FA",
        "label": f"Finite-Difference Time-Domain for Room Acoustics ({method_upper})",
        "name": f"{method}_setting.json",
        "simulationType": method_upper,
        "repositoryURL": "https://github.com/drievuldig/choras-fa-adapter",
        "documentationURL": "https://github.com/drievuldig/choras-fa-adapter#readme",
    }


def _render_task_type_snippet(*, method: str) -> str:
    method_upper = method.upper()
    timestamp = datetime.now(UTC).isoformat()
    version = __version__
    return (
        f"# generated-by: choras-fa-adapter\n"
        f"# adapter-version: {version}\n"
        f"# generated-at: {timestamp}\n"
        f"#\n"
        f"# Add the following value to the TaskType enum\n"
        f"# in app/types/Task.py:\n"
        f"#\n"
        f"#   {method_upper} = \"{method_upper}\"\n"
        f"#\n"
        f"# The simulationType field in the registry snippet above must match this.\\n"
    )
