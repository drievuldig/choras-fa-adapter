from __future__ import annotations

import base64
import math
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any

import meshio
import numpy as np

from .errors import stage_error
from .models import MeshInlinePayload

MAX_MESH_BYTES = 5 * 1024 * 1024
MAX_TOTAL_GEOMETRY_BYTES = 5 * 1024 * 1024
MAX_SUPPORTED_BAND_HZ = 16000.0


def _normalize_frequency_key(value: int | float) -> str:
    # Use compact string keys like "125" for whole-number octave centers.
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return str(int(value))
    return str(value)


def _is_supported_band(value: int | float) -> bool:
    return math.isfinite(float(value)) and float(value) <= MAX_SUPPORTED_BAND_HZ


def _to_absorption_coefficients(
    raw_value: Any,
    *,
    frequencies: list[int | float] | None,
    boundary: str,
) -> dict[str, float]:
    if isinstance(raw_value, str):
        parts = [part.strip() for part in raw_value.split(",") if part.strip()]
        if not parts:
            raise stage_error(
                "material_mapping",
                f"invalid absorption vector for {boundary}",
            )
        raw_value = parts

    if isinstance(raw_value, dict) and raw_value:
        out: dict[str, float] = {}
        for key, coeff in raw_value.items():
            if not isinstance(key, str) or not key.strip():
                raise stage_error(
                    "material_mapping",
                    f"invalid absorption frequency key for {boundary}",
                )
            try:
                freq_value = float(key)
            except ValueError as exc:
                raise stage_error(
                    "material_mapping",
                    f"invalid absorption frequency key for {boundary}",
                    cause=exc,
                ) from exc
            if not _is_supported_band(freq_value):
                continue
            if not isinstance(coeff, int | float):
                raise stage_error(
                    "material_mapping",
                    f"invalid absorption coefficient value for {boundary}",
                )
            out[key] = float(coeff)
        if not out:
            raise stage_error(
                "material_mapping",
                f"no supported absorption bands for {boundary}",
            )
        return out

    if isinstance(raw_value, list):
        if not raw_value:
            raise stage_error(
                "material_mapping", f"invalid absorption vector for {boundary}"
            )
        if not isinstance(frequencies, list) or not frequencies:
            raise stage_error(
                "material_mapping",
                "frequencies must be provided when absorption is a list",
            )
        if len(raw_value) != len(frequencies):
            raise stage_error(
                "material_mapping",
                f"absorption/frequencies length mismatch for {boundary}",
            )

        out: dict[str, float] = {}
        for freq, coeff in zip(frequencies, raw_value, strict=True):
            if not isinstance(freq, int | float):
                raise stage_error(
                    "material_mapping",
                    f"invalid frequency value for {boundary}",
                )
            if not _is_supported_band(freq):
                continue
            if not isinstance(coeff, int | float | str):
                raise stage_error(
                    "material_mapping",
                    f"invalid absorption coefficient value for {boundary}",
                )
            try:
                parsed_coeff = float(coeff)
            except (TypeError, ValueError) as exc:
                raise stage_error(
                    "material_mapping",
                    f"invalid absorption coefficient value for {boundary}",
                    cause=exc,
                ) from exc
            out[_normalize_frequency_key(freq)] = parsed_coeff
        if not out:
            raise stage_error(
                "material_mapping",
                f"no supported absorption bands for {boundary}",
            )
        return out

    raise stage_error("material_mapping", f"invalid absorption vector for {boundary}")


def _extract_frequencies(data: dict[str, Any]) -> list[int | float] | None:
    raw_frequencies = data.get("frequencies")
    if isinstance(raw_frequencies, list) and raw_frequencies:
        return raw_frequencies

    results = data.get("results")
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, dict):
                continue
            item_frequencies = item.get("frequencies")
            if isinstance(item_frequencies, list) and item_frequencies:
                return item_frequencies

    return None


def extract_required_boundaries(msh_path: str) -> set[str]:
    try:
        mesh = meshio.read(msh_path)
    except Exception as exc:
        raise stage_error(
            "material_mapping",
            "failed reading msh for physical-group resolution",
            cause=exc,
        ) from exc

    field_data = getattr(mesh, "field_data", None)
    if not isinstance(field_data, dict) or not field_data:
        raise stage_error("material_mapping", "unresolved physical groups in msh")

    cell_data_dict = getattr(mesh, "cell_data_dict", None)
    if not isinstance(cell_data_dict, dict):
        raise stage_error("material_mapping", "unresolved physical groups in msh")

    gmsh_physical = cell_data_dict.get("gmsh:physical")
    if not isinstance(gmsh_physical, dict) or not gmsh_physical:
        raise stage_error("material_mapping", "unresolved physical groups in msh")

    physical_ids: set[int] = set()
    for values in gmsh_physical.values():
        for raw in values:
            try:
                physical_ids.add(int(raw))
            except (TypeError, ValueError) as exc:
                raise stage_error(
                    "material_mapping",
                    "malformed physical-group identifiers in msh",
                    cause=exc,
                ) from exc

    if not physical_ids:
        raise stage_error("material_mapping", "unresolved physical groups in msh")

    # field_data values are [physical_id, dimension].
    # dimension == 2 means surface; 1 == line/curve, 3 == volume.
    # Only surfaces are acoustic boundaries requiring absorption coefficients.
    resolved: set[str] = set()
    for name, descriptor in field_data.items():
        if not isinstance(name, str) or not name:
            continue
        try:
            physical_id = int(descriptor[0])
            dimension = int(descriptor[1])
        except (TypeError, ValueError, IndexError):
            continue
        if physical_id in physical_ids and dimension == 2:
            resolved.add(name)

    if not resolved:
        raise stage_error("material_mapping", "unresolved physical groups in msh")

    return resolved


def build_inline_mesh_payload(msh_path: str) -> list[MeshInlinePayload]:
    try:
        mesh = meshio.read(msh_path)
    except Exception as exc:  # meshio can raise mixed exceptions
        raise stage_error(
            "mesh_conversion", "failed reading msh input", cause=exc
        ) from exc

    try:
        points, faces = _extract_surface_mesh(mesh)
        ply_bytes = _encode_binary_triangle_ply(points, faces)
        _validate_ply_size(ply_bytes, points_count=points.shape[0], faces_count=faces.shape[0])
    except Exception as exc:
        raise stage_error(
            "mesh_conversion", "failed converting msh to ply", cause=exc
        ) from exc

    size = len(ply_bytes)
    if size > MAX_MESH_BYTES:
        raise stage_error("mesh_conversion", "decoded PLY size exceeds 5MB")
    if size > MAX_TOTAL_GEOMETRY_BYTES:
        raise stage_error("mesh_conversion", "cumulative geometry size exceeds 5MB")

    b64 = base64.b64encode(ply_bytes).decode("ascii")
    mesh_name = Path(msh_path).name
    return [
        MeshInlinePayload(
            mesh_id="mesh-0",
            name=mesh_name,
            ply_b64=b64,
            decoded_size_bytes=size,
        )
    ]


def _extract_surface_mesh(mesh: Any) -> tuple[np.ndarray, np.ndarray]:
    points_raw = getattr(mesh, "points", None)
    if points_raw is None:
        raise stage_error("mesh_conversion", "msh mesh has no points")

    points = np.asarray(points_raw, dtype=np.float32)
    if points.ndim != 2 or points.shape[0] == 0 or points.shape[1] < 3:
        raise stage_error("mesh_conversion", "msh points are malformed")
    points_xyz = points[:, :3]

    cells = getattr(mesh, "cells", None)
    if not isinstance(cells, list) or not cells:
        raise stage_error("mesh_conversion", "msh mesh has no cells")

    triangles: list[list[int]] = []
    tetra_blocks: list[np.ndarray] = []

    for cell_block in cells:
        cell_type = getattr(cell_block, "type", "")
        data = np.asarray(getattr(cell_block, "data", []), dtype=np.int64)
        if data.size == 0:
            continue

        if cell_type in {"triangle", "triangle6"}:
            if data.shape[1] < 3:
                raise stage_error("mesh_conversion", f"malformed {cell_type} cell block")
            triangles.extend(data[:, :3].tolist())
            continue

        if cell_type in {"quad", "quad8", "quad9"}:
            if data.shape[1] < 4:
                raise stage_error("mesh_conversion", f"malformed {cell_type} cell block")
            triangles.extend(data[:, [0, 1, 2]].tolist())
            triangles.extend(data[:, [0, 2, 3]].tolist())
            continue

        if cell_type in {"tetra", "tetra10"}:
            if data.shape[1] < 4:
                raise stage_error("mesh_conversion", f"malformed {cell_type} cell block")
            tetra_blocks.append(data[:, :4])

    if not triangles and tetra_blocks:
        triangles = _extract_boundary_triangles_from_tetra(tetra_blocks)

    if not triangles:
        raise stage_error("mesh_conversion", "no triangle surface faces found in msh")

    face_array = np.asarray(triangles, dtype=np.int64)
    if face_array.ndim != 2 or face_array.shape[1] != 3:
        raise stage_error("mesh_conversion", "surface faces are malformed")
    if np.any(face_array < 0) or np.any(face_array >= points_xyz.shape[0]):
        raise stage_error("mesh_conversion", "surface faces reference invalid vertex indices")

    used = np.unique(face_array.reshape(-1))
    remap = np.full(points_xyz.shape[0], -1, dtype=np.int64)
    remap[used] = np.arange(used.shape[0], dtype=np.int64)

    compact_points = points_xyz[used]
    compact_faces = remap[face_array]

    return compact_points.astype(np.float32), compact_faces.astype(np.int32)


def _extract_boundary_triangles_from_tetra(tetra_blocks: list[np.ndarray]) -> list[list[int]]:
    face_counts: dict[tuple[int, int, int], int] = defaultdict(int)
    oriented_face: dict[tuple[int, int, int], tuple[int, int, int]] = {}

    for tetra in tetra_blocks:
        for a, b, c, d in tetra.tolist():
            tet_faces = ((a, b, c), (a, d, b), (b, d, c), (a, c, d))
            for face in tet_faces:
                key = tuple(sorted(face))
                face_counts[key] += 1
                if key not in oriented_face:
                    oriented_face[key] = face

    out: list[list[int]] = []
    for key, count in face_counts.items():
        if count == 1:
            out.append(list(oriented_face[key]))
    return out


def _encode_binary_triangle_ply(points: np.ndarray, faces: np.ndarray) -> bytes:
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {points.shape[0]}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        f"element face {faces.shape[0]}\n"
        "property list uchar int vertex_indices\n"
        "end_header\n"
    ).encode("ascii")

    vertex_blob = np.asarray(points, dtype="<f4").tobytes(order="C")

    face_blob = bytearray()
    for i0, i1, i2 in np.asarray(faces, dtype=np.int32):
        face_blob.extend(struct.pack("<Biii", 3, int(i0), int(i1), int(i2)))

    return header + vertex_blob + bytes(face_blob)


def _validate_ply_size(ply_bytes: bytes, *, points_count: int, faces_count: int) -> None:
    marker = b"end_header\n"
    header_end = ply_bytes.find(marker)
    if header_end < 0:
        raise stage_error("mesh_conversion", "generated PLY missing end_header marker")
    header_bytes = header_end + len(marker)
    expected_payload = (points_count * 12) + (faces_count * 13)
    payload_bytes = len(ply_bytes) - header_bytes
    if payload_bytes != expected_payload:
        raise stage_error(
            "mesh_conversion",
            "generated PLY payload size does not match header declarations",
        )


def resolve_materials(
    data: dict[str, Any],
    *,
    required_boundaries: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    coeffs = data.get("absorption_coefficients")
    frequencies = _extract_frequencies(data)
    if not isinstance(coeffs, dict) or not coeffs:
        raise stage_error(
            "material_mapping", "absorption_coefficients missing or empty"
        )

    boundaries_to_map = (
        sorted(required_boundaries)
        if required_boundaries
        else sorted(coeffs.keys())
    )

    if required_boundaries:
        missing = sorted(required_boundaries - set(coeffs.keys()))
        if missing:
            joined = ", ".join(missing)
            raise stage_error(
                "material_mapping", f"missing absorption entry for boundaries: {joined}"
            )

    materials: list[dict[str, Any]] = []
    mesh_bindings: list[dict[str, Any]] = []

    for boundary in boundaries_to_map:
        value = coeffs.get(boundary)
        if not isinstance(boundary, str) or not boundary:
            raise stage_error("material_mapping", "invalid absorption boundary name")
        absorption_coefficients = _to_absorption_coefficients(
            value,
            frequencies=frequencies,
            boundary=boundary,
        )

        materials.append(
            {
                "name": boundary,
                "material_id": boundary,
                "absorption": value,
                "absorption_coefficients": absorption_coefficients,
            }
        )
    # FA requires unique mesh_id entries in mesh_bindings. For the current
    # single-mesh flow, emit exactly one binding for mesh-0.
    if materials:
        mesh_bindings.append(
            {
                "mesh_id": "mesh-0",
                "material_id": materials[0]["material_id"],
                "source": "simulation_default",
            }
        )

    return materials, mesh_bindings
