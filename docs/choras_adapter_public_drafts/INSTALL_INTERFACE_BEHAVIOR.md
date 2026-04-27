# install-interface Command Behavior (Draft)

## Command

choras-fa-adapter install-interface --target <simulation_backend_dir> --method fa

## Goal

Install or update the CHORAS-required interface file with a generated thin shim
that delegates to the adapter package.

## Inputs

- --target: directory containing CHORAS simulation_backend package
- --method: method name prefix for <method>interface.py (default: fa)
- --force: overwrite without prompt
- --dry-run: print planned changes only
- --backup: create timestamped backup before overwrite (default true)

## File placement

Output file:

- <target>/<method>interface.py

Optional init update:

- Ensure import line exists in <target>/__init__.py
  - from .<method>interface import <method>_method

## Validation checks

Before writing:

- target directory exists
- writable permissions are available
- adapter package is importable in current environment
- method name is a valid Python identifier prefix

## Idempotency

- Running command repeatedly should produce identical output unless template or
  version changed.
- The command must not duplicate the import line in __init__.py.

## Overwrite policy

If destination exists:

- without --force: prompt user
- with --backup: write backup file first

If destination does not exist:

- create file directly

## Generated file metadata

Header includes:

- generated-by: choras-fa-adapter
- adapter-version
- generation timestamp
- warning that local edits may be overwritten

## Exit codes

- 0 success
- 2 invalid arguments or target
- 3 write failure
- 4 environment or import check failure

## Logging

- concise human-readable logs by default
- --json option emits machine-readable events for CI

## Security considerations

- never print token values
- no network calls required during install step
