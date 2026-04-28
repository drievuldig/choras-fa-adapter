from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from .config import load_config
from .errors import AdapterError
from .installer import install_interface, install_settings_boilerplate
from .orchestrator import run_from_choras_json


@click.group()
def main() -> None:
    """CHORAS thin adapter CLI for the FA backend."""


@main.command("run")
@click.option("--json", "json_path", required=True, type=click.Path(exists=True))
def run_command(json_path: str) -> None:
    """Run full CHORAS -> FA orchestration for a single input JSON."""
    config = load_config()
    if config.log_poll_status:
        logging.basicConfig(level=logging.INFO, format="%(message)s", force=True)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
    outcome = run_from_choras_json(json_path, config=config)
    click.echo(f"completed: run_id={outcome.run_id} status={outcome.status}")


@main.command("install-interface")
@click.option(
    "--target",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option("--method", default="fa", show_default=True)
@click.option("--force", is_flag=True, default=False)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--backup/--no-backup", default=True, show_default=True)
@click.option("--json-logs", is_flag=True, default=False)
def install_interface_command(
    target: Path,
    method: str,
    force: bool,
    dry_run: bool,
    backup: bool,
    json_logs: bool,
) -> None:
    """Install or update the CHORAS-required interface file."""
    result = install_interface(
        target=target,
        method=method,
        force=force,
        dry_run=dry_run,
        backup=backup,
        json_logs=json_logs,
    )

    if json_logs:
        payload = {
            "success": result.success,
            "exit_code": result.exit_code,
            "messages": result.messages,
        }
        click.echo(json.dumps(payload))
    else:
        for line in result.messages:
            click.echo(line)

    if not result.success:
        raise SystemExit(result.exit_code)


@main.command("install-settings-boilerplate")
@click.option(
    "--target",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option("--method", default="fa", show_default=True)
@click.option("--force", is_flag=True, default=False)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--backup/--no-backup", default=True, show_default=True)
@click.option("--json-logs", is_flag=True, default=False)
def install_settings_boilerplate_command(
    target: Path,
    method: str,
    force: bool,
    dry_run: bool,
    backup: bool,
    json_logs: bool,
) -> None:
    """Install CHORAS settings schema + registration boilerplate for FA."""
    result = install_settings_boilerplate(
        target=target,
        method=method,
        force=force,
        dry_run=dry_run,
        backup=backup,
        json_logs=json_logs,
    )

    if json_logs:
        payload = {
            "success": result.success,
            "exit_code": result.exit_code,
            "messages": result.messages,
        }
        click.echo(json.dumps(payload))
    else:
        for line in result.messages:
            click.echo(line)

    if not result.success:
        raise SystemExit(result.exit_code)


if __name__ == "__main__":
    try:
        main()
    except AdapterError as exc:
        click.echo(f"{exc.stage}: {exc}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("aborted", err=True)
        sys.exit(130)
