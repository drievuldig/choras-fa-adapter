from __future__ import annotations

import base64

import pytest
from choras_fa_adapter.errors import AdapterError
from choras_fa_adapter.mesh import (
    build_inline_mesh_payload,
    extract_required_boundaries,
    resolve_materials,
)


class FakeMesh:
    def __init__(self, field_data: dict, cell_data_dict: dict):
        self.field_data = field_data
        self.cell_data_dict = cell_data_dict


class FakeCellBlock:
    def __init__(self, cell_type: str, data: list[list[int]]):
        self.type = cell_type
        self.data = data


class FakeGeometryMesh:
    def __init__(self, points: list[list[float]], cells: list[FakeCellBlock]):
        self.points = points
        self.cells = cells


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
    assert material_names == {"wall", "ceiling"}
    assert len(mesh_bindings) == 1
    assert mesh_bindings[0]["mesh_id"] == "mesh-0"
    assert mesh_bindings[0]["material_id"] in {"wall", "ceiling"}
    assert materials[0]["material_id"] in {"wall", "ceiling"}
    assert materials[0]["absorption_coefficients"]


def test_resolve_materials_emits_unique_mesh_binding_for_single_mesh() -> None:
    data = {
        "frequencies": [125, 250, 500],
        "absorption_coefficients": {
            "floor": [0.1, 0.2, 0.3],
            "wall1": [0.2, 0.3, 0.4],
            "ceiling": [0.3, 0.4, 0.5],
            "wall2": [0.4, 0.5, 0.6],
            "wall3": [0.5, 0.6, 0.7],
            "wall4": [0.6, 0.7, 0.8],
        },
    }

    materials, mesh_bindings = resolve_materials(
        data,
        required_boundaries={"floor", "wall1", "ceiling", "wall2", "wall3", "wall4"},
    )

    assert len(materials) == 6
    assert len(mesh_bindings) == 1
    assert mesh_bindings[0]["mesh_id"] == "mesh-0"
    assert mesh_bindings[0]["material_id"] in {
        "floor",
        "wall1",
        "ceiling",
        "wall2",
        "wall3",
        "wall4",
    }


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


def test_resolve_materials_accepts_csv_absorption_and_result_frequencies() -> None:
    data = {
        "results": [{"frequencies": [125, 250, 500]}],
        "absorption_coefficients": {
            "wall": "0.1, 0.2, 0.3",
        },
    }

    materials, _ = resolve_materials(data, required_boundaries={"wall"})
    coeffs = materials[0]["absorption_coefficients"]
    assert coeffs == {"125": 0.1, "250": 0.2, "500": 0.3}


def test_resolve_materials_rejects_bad_csv_absorption() -> None:
    data = {
        "results": [{"frequencies": [125, 250, 500]}],
        "absorption_coefficients": {
            "wall": "0.1, bad, 0.3",
        },
    }

    with pytest.raises(AdapterError) as exc:
        resolve_materials(data, required_boundaries={"wall"})

    assert exc.value.stage == "material_mapping"
    assert "invalid absorption coefficient value" in str(exc.value)


def test_build_inline_mesh_payload_emits_valid_binary_triangle_ply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mesh = FakeGeometryMesh(
        points=[
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
        cells=[
            FakeCellBlock("triangle", [[0, 1, 2], [0, 2, 3]]),
        ],
    )

    monkeypatch.setattr("choras_fa_adapter.mesh.meshio.read", lambda _path: mesh)

    payload = build_inline_mesh_payload("/tmp/cube.msh")
    assert len(payload) == 1
    encoded = payload[0]
    assert encoded.name == "cube.msh"

    ply_bytes = base64.b64decode(encoded.ply_b64)
    assert encoded.decoded_size_bytes == len(ply_bytes)

    header_end = ply_bytes.index(b"end_header\n") + len(b"end_header\n")
    header = ply_bytes[:header_end].decode("ascii")
    assert "format binary_little_endian 1.0" in header
    assert "property float x" in header
    assert "property list uchar int vertex_indices" in header
    assert "element vertex 4" in header
    assert "element face 2" in header

    payload_bytes = len(ply_bytes) - header_end
    # 4 vertices * 12 bytes + 2 faces * (1 + 3*4) bytes
    assert payload_bytes == (4 * 12) + (2 * 13)


def test_build_inline_mesh_payload_extracts_surface_from_tetra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mesh = FakeGeometryMesh(
        points=[
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        cells=[
            FakeCellBlock("tetra", [[0, 1, 2, 3]]),
        ],
    )

    monkeypatch.setattr("choras_fa_adapter.mesh.meshio.read", lambda _path: mesh)

    payload = build_inline_mesh_payload("/tmp/tetra.msh")
    ply_bytes = base64.b64decode(payload[0].ply_b64)
    header_end = ply_bytes.index(b"end_header\n") + len(b"end_header\n")
    header = ply_bytes[:header_end].decode("ascii")

    assert "element vertex 4" in header
    assert "element face 4" in header


def test_build_inline_mesh_payload_without_surface_faces_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mesh = FakeGeometryMesh(
        points=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        cells=[FakeCellBlock("line", [[0, 1]])],
    )

    monkeypatch.setattr("choras_fa_adapter.mesh.meshio.read", lambda _path: mesh)

    with pytest.raises(AdapterError) as exc:
        build_inline_mesh_payload("/tmp/line_only.msh")

    assert exc.value.stage == "mesh_conversion"
    assert "no triangle surface faces" in str(exc.value)
