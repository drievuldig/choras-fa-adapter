from __future__ import annotations

from choras_fa_adapter.models import MeshInlinePayload
from choras_fa_adapter.payload_builder import build_submit_body


def test_build_submit_body_matches_contract_shape() -> None:
    data = {
        "simulationSettings": {
            "fa_c0_mps": 343.0,
            "fa_rho0_kgpm3": 1.2,
            "fa_ir_length_s": 1.5,
            "fa_max_gridstep_cm": 2.0,
            "fa_freq_limit_hz": 4000.0,
            "iterations": 50,
        },
        "results": [
            {
                "sourceX": 2.0,
                "sourceY": 2.0,
                "sourceZ": 1.5,
                "responses": [
                    {"x": 1.0, "y": 1.0, "z": 1.5},
                ],
            }
        ],
    }
    meshes = [
        MeshInlinePayload(
            mesh_id="mesh-0",
            name="room.ply",
            ply_b64="cGx5LWRhdGE=",
            decoded_size_bytes=8,
        )
    ]
    materials = [
        {
            "name": "wall",
            "material_id": "wall",
            "absorption": [0.1, 0.2, 0.3],
            "absorption_coefficients": {"125": 0.1, "250": 0.2, "500": 0.3},
        }
    ]
    mesh_bindings = [
        {
            "mesh_id": "mesh-0",
            "material_id": "wall",
            "source": "simulation_default",
        }
    ]

    payload = build_submit_body(
        data,
        meshes=meshes,
        materials=materials,
        mesh_bindings=mesh_bindings,
    )

    assert payload == {
        "simulation_settings": {
            "fa_c0_mps": 343.0,
            "fa_rho0_kgpm3": 1.2,
            "fa_ir_length_s": 1.5,
            "fa_max_gridstep_cm": 2.0,
            "fa_freq_limit_hz": 4000.0,
            "iterations": 50,
        },
        "payload": {
            "sources": [{"x": 2.0, "y": 2.0, "z": 1.5}],
            "receivers": [{"x": 1.0, "y": 1.0, "z": 1.5}],
            "meshes": [
                {
                    "mesh_id": "mesh-0",
                    "name": "room.ply",
                    "ply_b64": "cGx5LWRhdGE=",
                }
            ],
            "boundary_conditions": {
                "schema_version": 1,
                "materials": materials,
                "mesh_bindings": mesh_bindings,
            },
        },
    }

    assert "simulation" not in payload["payload"]
    assert "source" not in payload["payload"]
    assert "postprocessing" not in payload["payload"]


def test_build_submit_body_defaults_missing_optional_sections() -> None:
    payload = build_submit_body(
        {"simulationSettings": {}, "results": []},
        meshes=[],
        materials=[],
        mesh_bindings=[],
    )

    assert payload["simulation_settings"] == {}
    assert payload["payload"]["sources"] == []
    assert payload["payload"]["receivers"] == []
    assert payload["payload"]["meshes"] == []
    assert payload["payload"]["boundary_conditions"] == {
        "schema_version": 1,
        "materials": [],
        "mesh_bindings": [],
    }
