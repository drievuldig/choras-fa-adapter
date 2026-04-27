from __future__ import annotations

import pytest
from choras_fa_adapter.errors import AdapterError
from choras_fa_adapter.mesh import extract_required_boundaries, resolve_materials


class FakeMesh:
    def __init__(self, field_data: dict, cell_data_dict: dict):
        self.field_data = field_data
        self.cell_data_dict = cell_data_dict


def test_extract_required_boundaries_from_physical_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mesh = FakeMesh(
        field_data={"wall": [1, 2], "ceiling": [2, 2], "volume": [99, 3]},
        cell_data_dict={"gmsh:physical": {"triangle": [1, 2, 2]}},
    )

    monkeypatch.setattr("choras_fa_adapter.mesh.meshio.read", lambda _path: fake_mesh)

    boundaries = extract_required_boundaries("/tmp/mesh.msh")
    assert boundaries == {"wall", "ceiling"}


def test_extract_required_boundaries_ignores_volume_and_line_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # RoomVolume (dim 3) and default (dim 1) present in physical IDs — must be excluded.
    fake_mesh = FakeMesh(
        field_data={
            "floor": [1, 2],
            "wall1": [2, 2],
            "RoomVolume": [3, 3],
            "default": [4, 1],
        },
        cell_data_dict={
            "gmsh:physical": {"triangle": [1, 2], "tetra": [3], "line": [4]}
        },
    )

    monkeypatch.setattr("choras_fa_adapter.mesh.meshio.read", lambda _path: fake_mesh)

    boundaries = extract_required_boundaries("/tmp/mesh.msh")
    assert boundaries == {"floor", "wall1"}
    assert "RoomVolume" not in boundaries
    assert "default" not in boundaries


def test_extract_required_boundaries_unresolved_groups_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mesh = FakeMesh(
        field_data={},
        cell_data_dict={"gmsh:physical": {"triangle": [1]}},
    )
    monkeypatch.setattr("choras_fa_adapter.mesh.meshio.read", lambda _path: fake_mesh)

    with pytest.raises(AdapterError) as exc:
        extract_required_boundaries("/tmp/mesh.msh")

    assert exc.value.stage == "material_mapping"
    assert "unresolved physical groups" in str(exc.value)


def test_resolve_materials_requires_absorption_for_all_boundaries() -> None:
    data = {
        "absorption_coefficients": {
            "wall": [0.1, 0.2, 0.3],
        }
    }

    with pytest.raises(AdapterError) as exc:
        resolve_materials(data, required_boundaries={"wall", "ceiling"})

    assert exc.value.stage == "material_mapping"
    assert "missing absorption entry for boundaries: ceiling" in str(exc.value)


def test_resolve_materials_uses_only_required_boundaries() -> None:
    data = {
        "frequencies": [125, 250, 500],
        "absorption_coefficients": {
            "wall": [0.1, 0.2, 0.3],
            "ceiling": [0.4, 0.5, 0.6],
            "unused": [0.9, 0.9, 0.9],
        }
    }

    materials, mesh_bindings = resolve_materials(
        data,
        required_boundaries={"wall", "ceiling"},
    )

    material_names = {item["name"] for item in materials}
    bound_ids = {item["material_id"] for item in mesh_bindings}
    assert material_names == {"wall", "ceiling"}
    assert bound_ids == {"wall", "ceiling"}
    assert materials[0]["material_id"] in {"wall", "ceiling"}
    assert materials[0]["absorption_coefficients"]


def test_resolve_materials_drops_bands_above_16000_hz() -> None:
    data = {
        "frequencies": [
            125,
            250,
            500,
            1000,
            2000,
            4000,
            8000,
            16000,
            32000,
        ],
        "absorption_coefficients": {
            "wall": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
        },
    }

    materials, _ = resolve_materials(data, required_boundaries={"wall"})

    coeffs = materials[0]["absorption_coefficients"]
    assert "32000" not in coeffs
    assert set(coeffs.keys()) == {
        "125",
        "250",
        "500",
        "1000",
        "2000",
        "4000",
        "8000",
        "16000",
    }
