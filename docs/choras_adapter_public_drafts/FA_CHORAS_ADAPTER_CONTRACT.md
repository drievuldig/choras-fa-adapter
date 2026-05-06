# FA-CHORAS Thin Adapter Contract (v0)

## Purpose

This document defines the API and runtime boundary between:

- CHORAS interface file
- Public FA-CHORAS thin adapter package
- Private FA backend CHORAS endpoints

The adapter must have no dependency on private FA libraries.

## Non-goals

- No simulation execution in adapter
- No private imports from FA backend/worker
- No direct dependency on rafdtd or fa_tools

## Architecture Boundary

### CHORAS interface file (inside CHORAS backend)

Responsibilities:

- Receive json_path from CHORAS
- Invoke adapter package orchestration
- Persist progress/results back to CHORAS JSON shape
- Surface errors in CHORAS-compatible fields

This file must stay thin. It must not own msh parsing, FA payload assembly,
HTTP workflow logic, or material mapping logic.

### Public adapter package

Responsibilities:

- Parse and validate CHORAS input JSON
- Convert msh to PLY via meshio
- Resolve physical-group to material assignment
- Parse absorption coefficients and map to FA payload format
- Build FA CHORAS submit body
- Submit run and poll status
- Update CHORAS results/progress fields

### Private FA backend

Responsibilities:

- Authoritative validation/admission
- Input derivation from CHORAS-provided simulation inputs
- Admittance derivation and worker dispatch
- Status/result lifecycle

## CHORAS Input Expectations (from interface JSON)

Required source fields:

- msh_path
- absorption_coefficients (keyed by boundary/physical-group name; each value may
  be a CSV string like "0.6, 0.69, 0.71" or a numeric vector)
- simulationSettings
- results list (includes source/receiver definitions and frequency bands under
  results[*].frequencies)
- should_cancel (optional)
- task_id (optional)

`simulationSettings` fields expected by FA:

- fa_c0_mps: wavespeed in air (m/s)
- fa_rho0_kgpm3: air density (kg/m^3)
- fa_ir_length_s: requested IR length (mapped to duration_s)
- fa_max_gridstep_cm: max allowed grid step for discretization (cm)
- fa_freq_limit_hz: upper frequency limit (Hz)

Adapter must fail fast on:

- missing msh_path
- missing or malformed simulationSettings fields
- unresolved physical groups
- missing absorption entry for a required boundary
- malformed absorption vectors
- invalid or empty results structure

## FA Submit Contract (adapter -> FA)

Endpoint:

- POST /api/v1/choras/runs

Body:

- simulation_settings (physical constants and simulation-control limits; mapped
  from CHORAS input key simulationSettings)
- payload
  - sources
  - receivers
  - meshes
    - mesh_id
    - name
    - ply_b64
  - boundary_conditions
    - schema_version
    - materials
    - mesh_bindings

Constraints:

- per-mesh decoded PLY size <= 5 MB
- cumulative decoded inline geometry size <= 5 MB (current backend policy)

## FA Status Contract (adapter -> FA)

Endpoint:

- GET /api/v1/choras/runs/{run_id}

Key fields consumed:

- status: queued | running | completed | failed
- progress: float in [0.0, 1.0] or null
- result: object or null
- error: object or null
- correlation_id

## FA Result Contract (result shape expected by adapter)

When status is `completed`, `result.worker.receivers` must be a non-empty list.
Each receiver entry must include:

- x, y, z: float — position, matched by adapter to CHORAS response coordinates
- corrected: list[float] — source-corrected impulse response
- uncorrected: list[float] — raw impulse response

Each receiver entry should also include:

- parameters: object — acoustic parameters, one key per metric, each value a
  list of floats positionally aligned to the `frequencies` array in the CHORAS
  input. Parameters are optional for backwards compatibility; when absent the
  adapter writes no parameters field to the CHORAS response.

Required parameter keys (when parameters is present):

- edt: Early Decay Time (extrapolated 60 dB slope from -10 dB), in seconds
- t20: Reverberation time from -5 to -25 dB extrapolated to 60 dB, in seconds
- t30: Reverberation time from -5 to -35 dB extrapolated to 60 dB, in seconds
- c80: Clarity (10 log10 of early/late energy ratio at 80 ms), in dB
- d50: Definition (early energy fraction at 50 ms), dimensionless [0, 1]
- ts: Centre time (energy-weighted centroid of h^2(t)), in seconds
- spl_t0_freq: Broadband SPL per frequency band referenced to t=0, in dB

Parameter values should be computed from the `corrected` IR. If a metric cannot
be computed for a band (e.g., insufficient IR length for T30), use null for that
position rather than omitting the key.

Adapter validates that parameters, when present, is an object; any other type
raises a result_mapping error.

## Progress and Result Mapping

Adapter writes CHORAS results.percentage as:

- percentage = round(progress * 100)

Adapter phase progress mapping:

- 0-1: parse/validate input
- 1-2: msh conversion + material mapping
- 2-3: FA submit
- 3-99: poll running
- 100: completed

On failure:

- preserve last known percentage
- write concise error message and correlation_id (if available)

## Error Handling Rules

- Fail fast; never silently continue with partial data
- Include concise stage prefix in adapter errors:
  - input_validation
  - mesh_conversion
  - material_mapping
  - fa_submit
  - fa_status_poll
  - result_writeback
- Preserve original exception detail where safe

## Versioning and Compatibility

- Adapter follows SemVer
- CHORAS deployment pins exact adapter version
- Adapter declares supported FA API compatibility range
- Optional startup probe against FA capability/version endpoint

## Security

- Use token from env/config
- Never log token or full Authorization header
- TLS verification enabled by default
- Fail fast when token or scope is invalid

## Packaging and Deployment

- Public PyPI package
- Optional Docker image for reproducible runtime
- CHORAS interface file generated via install-interface command (not manual copy
  as default path)

## Testing Requirements

- Unit tests:
  - msh parsing and physical-group resolution
  - absorption parsing and mapping
  - payload build validation
- Contract tests:
  - submit/status response parsing
- E2E smoke:
  - local mocked FA or staging FA endpoint
