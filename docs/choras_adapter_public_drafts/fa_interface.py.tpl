from __future__ import annotations

import json
import traceback
from pathlib import Path

from choras_fa_adapter.config import AdapterConfig, load_config
from choras_fa_adapter.errors import AdapterError
from choras_fa_adapter.orchestrator import run_from_choras_json


def fa_method(json_path: str) -> None:
    """CHORAS-required interface entrypoint.

    Receives path to CHORAS JSON and updates that file with progress/results.
    """
    path = Path(json_path)

    try:
        config: AdapterConfig = load_config()
        run_from_choras_json(str(path), config=config)
    except AdapterError as exc:
        _write_failure(path, f"{exc.stage}: {exc}")
    except Exception as exc:
        # Final boundary: do best-effort writeback and keep traceback in logs.
        _write_failure(path, f"unexpected_error: {exc}")
        traceback.print_exc()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("json_path", help="Path to CHORAS input JSON")
    args = parser.parse_args()
    fa_method(args.json_path)


def _write_failure(path: Path, message: str) -> None:
    """Best-effort CHORAS-compatible failure writeback."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return

    results = data.get("results")
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict):
                # Preserve existing percentage if present; do not reset progress.
                item.setdefault("percentage", 0)
                item.setdefault("error", {})
                if isinstance(item["error"], dict):
                    item["error"]["message"] = message

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
