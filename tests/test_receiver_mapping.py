"""Tests for receiver result mapping in CHORAS JSON."""

import json
import tempfile
from pathlib import Path

import pytest
from choras_fa_adapter.choras_io import ChorasJson
from choras_fa_adapter.errors import AdapterError


def test_set_result_with_receiver_mapping_success():
    """Test successful mapping of receiver results to responses."""
    data = {
        "results": [
            {
                "sourceX": 0.0,
                "sourceY": 0.0,
                "sourceZ": 0.0,
                "responses": [
                    {"x": 1.0, "y": 0.0, "z": 0.0},
                    {"x": 2.0, "y": 0.0, "z": 0.0},
                ],
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        path = Path(f.name)

    try:
        choras = ChorasJson(path, data)
        result = {
            "mode": "local",
            "status": "completed",
            "worker": {
                "receivers": [
                    {
                        "x": 1.0,
                        "y": 0.0,
                        "z": 0.0,
                        "uncorrected": [0.1, 0.2, 0.3],
                        "corrected": [0.15, 0.25, 0.35],
                        "parameters": {
                            "edt": [0.4, 0.5, 0.6],
                            "t20": [0.41, 0.51, 0.61],
                            "t30": [0.42, 0.52, 0.62],
                            "c80": [1.2, 1.3, 1.4],
                            "d50": [0.55, 0.56, 0.57],
                            "ts": [0.07, 0.08, 0.09],
                            "spl_t0_freq": [65.0, 66.0, 67.0],
                        },
                    },
                    {
                        "x": 2.0,
                        "y": 0.0,
                        "z": 0.0,
                        "uncorrected": [0.2, 0.3, 0.4],
                        "corrected": [0.25, 0.35, 0.45],
                        "parameters": {
                            "edt": [0.7, 0.8, 0.9],
                            "t20": [0.71, 0.81, 0.91],
                            "t30": [0.72, 0.82, 0.92],
                            "c80": [1.5, 1.6, 1.7],
                            "d50": [0.58, 0.59, 0.60],
                            "ts": [0.10, 0.11, 0.12],
                            "spl_t0_freq": [68.0, 69.0, 70.0],
                        },
                    },
                ]
            },
        }

        choras.set_result_with_receiver_mapping(result)

        # Check that each response has its receiver data
        responses = choras.results[0]["responses"]
        assert responses[0]["result"]["corrected"] == [0.15, 0.25, 0.35]
        assert responses[0]["result"]["uncorrected"] == [0.1, 0.2, 0.3]
        assert responses[1]["result"]["corrected"] == [0.25, 0.35, 0.45]
        assert responses[1]["result"]["uncorrected"] == [0.2, 0.3, 0.4]
        assert responses[0]["receiverResults"] == [0.15, 0.25, 0.35]
        assert responses[0]["receiverResultsUncorrected"] == [0.1, 0.2, 0.3]
        assert responses[1]["receiverResults"] == [0.25, 0.35, 0.45]
        assert responses[1]["receiverResultsUncorrected"] == [0.2, 0.3, 0.4]
        assert responses[0]["parameters"]["edt"] == [0.4, 0.5, 0.6]
        assert responses[1]["parameters"]["spl_t0_freq"] == [68.0, 69.0, 70.0]

        # Check that the overall result is set
        assert choras.results[0]["result"]["status"] == "completed"

    finally:
        path.unlink()


def test_set_result_with_receiver_mapping_coordinate_rounding():
    """Test that coordinate matching works with small floating point differences."""
    data = {
        "results": [
            {
                "sourceX": 0.0,
                "sourceY": 0.0,
                "sourceZ": 0.0,
                "responses": [
                    {"x": 1.0000001, "y": 0.0000001, "z": 0.0},
                ],
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        path = Path(f.name)

    try:
        choras = ChorasJson(path, data)
        result = {
            "mode": "local",
            "status": "completed",
            "worker": {
                "receivers": [
                    {
                        "x": 1.0,
                        "y": 0.0,
                        "z": 0.0,
                        "uncorrected": [0.1],
                        "corrected": [0.15],
                        "parameters": {"edt": [0.4]},
                    },
                ]
            },
        }

        choras.set_result_with_receiver_mapping(result)

        # Should match due to rounding to 6 decimal places
        response = choras.results[0]["responses"][0]
        assert response["result"]["corrected"] == [0.15]
        assert response["receiverResults"] == [0.15]
        assert response["receiverResultsUncorrected"] == [0.1]
        assert response["parameters"]["edt"] == [0.4]

    finally:
        path.unlink()


def test_set_result_with_receiver_mapping_no_match_raises_error():
    """Test that unmapped receivers raise an error."""
    data = {
        "results": [
            {
                "sourceX": 0.0,
                "sourceY": 0.0,
                "sourceZ": 0.0,
                "responses": [
                    {"x": 1.0, "y": 0.0, "z": 0.0},
                ],
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        path = Path(f.name)

    try:
        choras = ChorasJson(path, data)
        result = {
            "mode": "local",
            "status": "completed",
            "worker": {
                "receivers": [
                    {
                        "x": 2.0,  # Different coordinate - won't match
                        "y": 0.0,
                        "z": 0.0,
                        "uncorrected": [0.1],
                        "corrected": [0.15],
                    },
                ]
            },
        }

        with pytest.raises(AdapterError) as exc_info:
            choras.set_result_with_receiver_mapping(result)
        assert exc_info.value.stage == "result_mapping"
        assert "no receiver match for response" in str(exc_info.value)

    finally:
        path.unlink()


def test_set_result_with_no_worker_receivers_falls_back():
    """Test that missing worker data fails fast."""
    data = {
        "results": [
            {
                "sourceX": 0.0,
                "sourceY": 0.0,
                "sourceZ": 0.0,
                "responses": [
                    {"x": 1.0, "y": 0.0, "z": 0.0},
                ],
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        path = Path(f.name)

    try:
        choras = ChorasJson(path, data)
        result = {
            "mode": "local",
            "status": "completed",
            "worker": {},  # No receivers
        }

        with pytest.raises(AdapterError) as exc_info:
            choras.set_result_with_receiver_mapping(result)
        assert exc_info.value.stage == "result_mapping"
        assert "receivers must be non-empty" in str(exc_info.value)

    finally:
        path.unlink()


def test_set_result_with_receiver_mapping_without_parameters_keeps_compatibility():
    """Test that parameters remain optional for backwards compatibility."""
    data = {
        "results": [
            {
                "sourceX": 0.0,
                "sourceY": 0.0,
                "sourceZ": 0.0,
                "responses": [
                    {"x": 1.0, "y": 0.0, "z": 0.0},
                ],
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        path = Path(f.name)

    try:
        choras = ChorasJson(path, data)
        result = {
            "mode": "local",
            "status": "completed",
            "worker": {
                "receivers": [
                    {
                        "x": 1.0,
                        "y": 0.0,
                        "z": 0.0,
                        "uncorrected": [0.1],
                        "corrected": [0.15],
                    },
                ]
            },
        }

        choras.set_result_with_receiver_mapping(result)

        response = choras.results[0]["responses"][0]
        assert response["receiverResults"] == [0.15]
        assert "parameters" not in response

    finally:
        path.unlink()


def test_set_result_with_receiver_mapping_missing_uncorrected_uses_fallback():
    """Test missing uncorrected falls back to corrected with provenance marker."""
    data = {
        "results": [
            {
                "sourceX": 0.0,
                "sourceY": 0.0,
                "sourceZ": 0.0,
                "responses": [
                    {"x": 1.0, "y": 0.0, "z": 0.0},
                ],
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        path = Path(f.name)

    try:
        choras = ChorasJson(path, data)
        result = {
            "mode": "local",
            "status": "completed",
            "worker": {
                "receivers": [
                    {
                        "x": 1.0,
                        "y": 0.0,
                        "z": 0.0,
                        "corrected": [0.15, 0.25],
                    },
                ]
            },
        }

        choras.set_result_with_receiver_mapping(result)

        response = choras.results[0]["responses"][0]
        assert response["receiverResults"] == [0.15, 0.25]
        assert response["receiverResultsUncorrected"] == [0.15, 0.25]
        assert response["result"]["uncorrected"] == [0.15, 0.25]
        assert response["result"]["uncorrected_fallback"] == "copied_from_corrected"

    finally:
        path.unlink()


def test_set_result_with_receiver_mapping_empty_uncorrected_uses_fallback():
    """Test empty uncorrected list falls back to corrected with marker."""
    data = {
        "results": [
            {
                "sourceX": 0.0,
                "sourceY": 0.0,
                "sourceZ": 0.0,
                "responses": [
                    {"x": 1.0, "y": 0.0, "z": 0.0},
                ],
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        path = Path(f.name)

    try:
        choras = ChorasJson(path, data)
        result = {
            "mode": "local",
            "status": "completed",
            "worker": {
                "receivers": [
                    {
                        "x": 1.0,
                        "y": 0.0,
                        "z": 0.0,
                        "corrected": [0.15, 0.25],
                        "uncorrected": [],
                    },
                ]
            },
        }

        choras.set_result_with_receiver_mapping(result)

        response = choras.results[0]["responses"][0]
        assert response["receiverResultsUncorrected"] == [0.15, 0.25]
        assert response["result"]["uncorrected_fallback"] == "copied_from_corrected"

    finally:
        path.unlink()


def test_set_result_with_receiver_mapping_invalid_parameters_raises_error():
    """Test that non-object parameters fail with result mapping error."""
    data = {
        "results": [
            {
                "sourceX": 0.0,
                "sourceY": 0.0,
                "sourceZ": 0.0,
                "responses": [
                    {"x": 1.0, "y": 0.0, "z": 0.0},
                ],
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        path = Path(f.name)

    try:
        choras = ChorasJson(path, data)
        result = {
            "mode": "local",
            "status": "completed",
            "worker": {
                "receivers": [
                    {
                        "x": 1.0,
                        "y": 0.0,
                        "z": 0.0,
                        "uncorrected": [0.1],
                        "corrected": [0.15],
                        "parameters": ["invalid"],
                    },
                ]
            },
        }

        with pytest.raises(AdapterError) as exc_info:
            choras.set_result_with_receiver_mapping(result)
        assert exc_info.value.stage == "result_mapping"
        assert "receiver parameters must be an object" in str(exc_info.value)

    finally:
        path.unlink()


def test_set_result_with_receiver_mapping_invalid_uncorrected_raises_error():
    """Test non-list uncorrected value fails with result mapping error."""
    data = {
        "results": [
            {
                "sourceX": 0.0,
                "sourceY": 0.0,
                "sourceZ": 0.0,
                "responses": [
                    {"x": 1.0, "y": 0.0, "z": 0.0},
                ],
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        path = Path(f.name)

    try:
        choras = ChorasJson(path, data)
        result = {
            "mode": "local",
            "status": "completed",
            "worker": {
                "receivers": [
                    {
                        "x": 1.0,
                        "y": 0.0,
                        "z": 0.0,
                        "corrected": [0.15],
                        "uncorrected": 0,
                    },
                ]
            },
        }

        with pytest.raises(AdapterError) as exc_info:
            choras.set_result_with_receiver_mapping(result)
        assert exc_info.value.stage == "result_mapping"
        assert "uncorrected impulse response must be a list" in str(exc_info.value)

    finally:
        path.unlink()
