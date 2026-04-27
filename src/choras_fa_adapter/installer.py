from __future__ import annotations

import shutil
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


def install_interface(
    *,
    target: Path,
    method: str,
    force: bool,
    dry_run: bool,
    backup: bool,
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

    interface_path = target / f"{method}interface.py"
    init_path = target / "__init__.py"

    rendered = _render_interface_template(method=method)
    import_line = f"from .{method}interface import {method}_method"

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
        if interface_path.exists() and backup:
            backup_path = interface_path.with_suffix(
                interface_path.suffix
                + f".bak.{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
            )
            shutil.copy2(interface_path, backup_path)
            messages.append(f"created backup: {backup_path}")

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
    return f'''from __future__ import annotations

# generated-by: choras-fa-adapter
# adapter-version: {version}
# generated-at: {timestamp}
# warning: local edits may be overwritten by install-interface

import json
import traceback
from pathlib import Path

from choras_fa_adapter.config import AdapterConfig, load_config
from choras_fa_adapter.errors import AdapterError
from choras_fa_adapter.orchestrator import run_from_choras_json


def {method}_method(json_path: str) -> None:
    """CHORAS-required interface entrypoint."""
    path = Path(json_path)

    try:
        config: AdapterConfig = load_config()
        run_from_choras_json(str(path), config=config)
    except AdapterError as exc:
        _write_failure(path, f"{{exc.stage}}: {{exc}}")
    except Exception as exc:
        _write_failure(path, f"unexpected_error: {{exc}}")
        traceback.print_exc()


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


if __name__ == "__main__":
    main()
'''
