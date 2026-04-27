from __future__ import annotations

from typing import Any

from .models import MeshInlinePayload


def _collect_sources(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in results:
        if all(k in item for k in ("sourceX", "sourceY", "sourceZ")):
            out.append(
                {"x": item["sourceX"], "y": item["sourceY"], "z": item["sourceZ"]}
            )
    return out


def _collect_receivers(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in results:
        for response in item.get("responses") or []:
            keys = ("x", "y", "z")
            if isinstance(response, dict) and all(k in response for k in keys):
                out.append(
                    {"x": response["x"], "y": response["y"], "z": response["z"]}
                )
    return out


def build_submit_body(
    data: dict[str, Any],
    *,
    meshes: list[MeshInlinePayload],
    materials: list[dict[str, Any]],
    mesh_bindings: list[dict[str, Any]],
) -> dict[str, Any]:
    results = data.get("results")
    typed_results = results if isinstance(results, list) else []

    return {
        "simulation_settings": data.get("simulationSettings", {}),
        "payload": {
            "sources": _collect_sources(typed_results),
            "receivers": _collect_receivers(typed_results),
            "meshes": [
                {
                    "mesh_id": m.mesh_id,
                    "name": m.name,
                    "ply_b64": m.ply_b64,
                }
                for m in meshes
            ],
            "boundary_conditions": {
                "schema_version": 1,
                "materials": materials,
                "mesh_bindings": mesh_bindings,
            },
        },
    }
