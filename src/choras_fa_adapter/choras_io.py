from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import stage_error


class ChorasJson:
    def __init__(self, path: Path, data: dict[str, Any]):
        self.path = path
        self.data = data

    @property
    def results(self) -> list[dict[str, Any]]:
        results = self.data.get("results")
        if not isinstance(results, list) or not results:
            raise stage_error("input_validation", "results must be a non-empty list")
        typed_results: list[dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                raise stage_error("input_validation", "results entries must be objects")
            typed_results.append(item)
        return typed_results

    def set_percentage(self, percentage: int) -> None:
        for item in self.results:
            item["percentage"] = max(0, min(100, percentage))

    def set_result(self, result: dict[str, Any]) -> None:
        for item in self.results:
            item["result"] = result

    def set_result_with_receiver_mapping(
        self, result: dict[str, Any]
    ) -> None:
        """Map receiver results from FA worker to individual response items.

        Expects result to have structure:
        {
            "worker": {
                "receivers": [
                    {"x": float, "y": float, "z": float,
                     "uncorrected": [...], "corrected": [...]}
                ]
            }
        }

        For each response in each result item, matches by coordinates and
        populates with the corresponding receiver result data.
        """
        worker = result.get("worker")
        if not isinstance(worker, dict):
            raise stage_error("result_mapping", "result.worker must be an object")
        receivers = worker.get("receivers")
        if not isinstance(receivers, list) or not receivers:
            raise stage_error("result_mapping", "result.worker.receivers must be non-empty")

        # Build a map of coordinates to receiver data for fast lookup
        coord_map: dict[tuple, dict[str, Any]] = {}
        for rcv in receivers:
            try:
                x = float(rcv.get("x") or 0)
                y = float(rcv.get("y") or 0)
                z = float(rcv.get("z") or 0)
                key = (round(x, 6), round(y, 6), round(z, 6))
                coord_map[key] = rcv
            except (TypeError, ValueError):
                pass

        # Map receivers to response items
        matched_count = 0
        expected_count = 0
        for item in self.results:
            responses = item.get("responses")
            if not isinstance(responses, list):
                raise stage_error("result_mapping", "results[].responses must be a list")
            if not responses:
                raise stage_error("result_mapping", "results[].responses must be non-empty")

            for response in responses:
                if not isinstance(response, dict):
                    raise stage_error("result_mapping", "responses[] entries must be objects")
                expected_count += 1
                try:
                    x = float(response.get("x") or 0)
                    y = float(response.get("y") or 0)
                    z = float(response.get("z") or 0)
                    key = (round(x, 6), round(y, 6), round(z, 6))
                    if key not in coord_map:
                        raise stage_error(
                            "result_mapping",
                            f"no receiver match for response at ({x}, {y}, {z})",
                        )

                    rcv_data = coord_map[key]
                    corrected = rcv_data.get("corrected")
                    uncorrected = rcv_data.get("uncorrected")
                    if not isinstance(corrected, list) or not corrected:
                        raise stage_error(
                            "result_mapping",
                            "receiver corrected impulse response missing or empty",
                        )
                    if not isinstance(uncorrected, list) or not uncorrected:
                        raise stage_error(
                            "result_mapping",
                            "receiver uncorrected impulse response missing or empty",
                        )

                    response["receiverResults"] = corrected
                    response["receiverResultsUncorrected"] = uncorrected
                    response["result"] = {
                        "corrected": corrected,
                        "uncorrected": uncorrected,
                    }
                    matched_count += 1
                except (TypeError, ValueError):
                    raise stage_error(
                        "result_mapping",
                        "response coordinates x/y/z must be numeric",
                    )

            # Set overall result for the item too
            item["result"] = result

        if matched_count != expected_count:
            raise stage_error(
                "result_mapping",
                f"receiver mapping incomplete: {matched_count}/{expected_count} responses",
            )

    def set_error(self, message: str, correlation_id: str | None = None) -> None:
        for item in self.results:
            err = item.get("error")
            if not isinstance(err, dict):
                err = {}
                item["error"] = err
            err["message"] = message
            if correlation_id:
                err["correlation_id"] = correlation_id

    def persist(self) -> None:
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            tmp_path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            tmp_path.replace(self.path)
        except OSError as exc:
            raise stage_error(
                "result_writeback", "failed to write CHORAS JSON", cause=exc
            ) from exc


def load_choras_json(path: str) -> ChorasJson:
    p = Path(path)
    if not p.exists():
        raise stage_error("input_validation", f"json path does not exist: {path}")

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise stage_error("input_validation", "invalid JSON input", cause=exc) from exc

    if not isinstance(data, dict):
        raise stage_error("input_validation", "top-level JSON must be an object")

    return ChorasJson(path=p, data=data)
