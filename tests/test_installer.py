from __future__ import annotations

from pathlib import Path

from choras_fa_adapter.installer import install_interface


def test_install_interface_dry_run(tmp_path: Path) -> None:
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
    assert not (tmp_path / "fainterface.py").exists()


def test_install_interface_writes_files(tmp_path: Path) -> None:
    result = install_interface(
        target=tmp_path,
        method="fa",
        force=False,
        dry_run=False,
        backup=True,
    )

    interface_path = tmp_path / "fainterface.py"
    init_path = tmp_path / "__init__.py"

    assert result.success is True
    assert result.exit_code == 0
    assert interface_path.exists()
    assert init_path.exists()

    init_text = init_path.read_text(encoding="utf-8")
    assert "from .fainterface import fa_method" in init_text


def test_install_interface_import_dedup(tmp_path: Path) -> None:
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

    init_text = (tmp_path / "__init__.py").read_text(encoding="utf-8")
    assert init_text.count("from .fainterface import fa_method") == 1
