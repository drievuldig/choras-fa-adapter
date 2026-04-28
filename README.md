# choras-fa-adapter

Thin public adapter between CHORAS JSON inputs and FA v1 endpoints.

## Client Install

Use this section for CHORAS runtime environments (non-dev installs).

Expected Python version:

- Python `>=3.11`

Install pinned adapter version:

```bash
python -m pip install "choras-fa-adapter==0.1.0"
```

Required environment variables:

Base URL source (in precedence order):

1. `CHORAS_FA_BASE_URL`
2. `~/.config/fa-sdk/config` (or `CHORAS_FA_CONFIG_FILE` override)

Token source (in precedence order):

1. `CHORAS_FA_TOKEN`
2. `~/.config/fa-sdk/credentials` (or `CHORAS_FA_CREDENTIALS_FILE` override)

One-command smoke check:

```bash
python -c "import choras_fa_adapter; print(choras_fa_adapter.__version__)" && choras-fa-adapter --help
```

## Quickstart

1. Install dependencies:

```bash
pip install -e .[dev]
```

2. Run adapter against a CHORAS JSON file:

```bash
choras-fa-adapter run --json /path/to/input.json
```

3. Install generated CHORAS interface shim:

```bash
choras-fa-adapter install-interface --target /path/to/simulation_backend --method fa
```

4. Install CHORAS settings-schema boilerplate for UI wiring:

```bash
choras-fa-adapter install-settings-boilerplate --target /path/to/simulation_backend --method fa
```

## Sample Input

A ready-to-edit CHORAS JSON example is available at `samples/choras_input.example.json`.

Typical run flow:

1. Copy `samples/choras_input.example.json` to a local working file.
2. Update `msh_path` to a real mesh file.
3. Ensure absorption boundary keys match mesh physical-group names.
4. Run:

```bash
choras-fa-adapter run --json /path/to/your/input.json
```

See `samples/README.md` for a concise checklist.

## Configuration

The adapter reads config from environment variables:

- `CHORAS_FA_BASE_URL` (optional if config file contains base URL)
- `CHORAS_FA_CONFIG_FILE` (optional, default `~/.config/fa-sdk/config`)
- `CHORAS_FA_TOKEN` (optional if credentials file contains token)
- `CHORAS_FA_CREDENTIALS_FILE` (optional, default `~/.config/fa-sdk/credentials`)
- `CHORAS_FA_SUBMIT_PATH` (default `/choras/runs`, relative to `CHORAS_FA_BASE_URL`)
- `CHORAS_FA_AUTH_REFRESH_PATH` (default `/auth/refresh`, used when exchanging PAT for access JWT)
- `CHORAS_FA_TOKEN_MODE` (default `auto`; one of `auto`, `access`, `pat`)
- `CHORAS_FA_VERIFY_TLS` (default `true`)
- `CHORAS_FA_TIMEOUT_SECONDS` (default `30`)
- `CHORAS_FA_POLL_INTERVAL_SECONDS` (default `2`)
- `CHORAS_FA_MAX_POLLS` (default `300`)
- `CHORAS_FA_ENABLE_CAPABILITY_PROBE` (default `false`)
- `CHORAS_FA_LOG_POLL_STATUS` (default `false`; logs each polled status/progress pair)

## Error stages

Errors are stage-prefixed:

- `input_validation`
- `mesh_conversion`
- `material_mapping`
- `fa_submit`
- `fa_status_poll`
- `result_writeback`
- `installer`
- `environment`

## Progress phase mapping

Adapter writes CHORAS results percentage using this phase model:

- 0-1: parse/validate input
- 1-2: msh conversion + material mapping
- 2-3: FA submit
- 3-99: poll running
- 100: completed

## Development

```bash
pytest
ruff check .
```
