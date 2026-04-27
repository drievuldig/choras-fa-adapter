from __future__ import annotations

import base64
import math
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import meshio

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
            if not isinstance(coeff, int | float):
                raise stage_error(
                    "material_mapping",
                    f"invalid absorption coefficient value for {boundary}",
                )
            out[_normalize_frequency_key(freq)] = float(coeff)
        if not out:
            raise stage_error(
                "material_mapping",
                f"no supported absorption bands for {boundary}",
            )
        return out

    raise stage_error("material_mapping", f"invalid absorption vector for {boundary}")


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
        with NamedTemporaryFile(suffix=".ply", delete=True) as tmp:
            meshio.write(tmp.name, mesh, file_format="ply")
            ply_bytes = Path(tmp.name).read_bytes()
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


def resolve_materials(
    data: dict[str, Any],
    *,
    required_boundaries: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    coeffs = data.get("absorption_coefficients")
    raw_frequencies = data.get("frequencies")
    frequencies = raw_frequencies if isinstance(raw_frequencies, list) else None
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
        mesh_bindings.append(
            {
                "mesh_id": "mesh-0",
                "material_id": boundary,
                "source": "simulation_default",
            }
        )

    return materials, mesh_bindings
