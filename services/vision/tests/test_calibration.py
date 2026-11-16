"""Unit tests for Zone Calibration & Geometry Validation (SB-10)."""
import json
from pathlib import Path
import pytest
from pydantic import ValidationError

from services.vision.calibration import (
    CalibrationConfig,
    TableZone,
    is_self_intersecting,
    load_calibration_config,
    point_in_polygon,
    polygon_area,
    polygons_overlap,
    save_calibration_config,
    validate_normalized_polygon,
)


def test_polygon_area_shoelace():
    # Unit square
    square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    assert pytest.approx(polygon_area(square)) == 1.0

    # Triangle
    triangle = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    assert pytest.approx(polygon_area(triangle)) == 0.5

    # Degenerate collinear points
    line = [(0.1, 0.1), (0.5, 0.5), (0.9, 0.9)]
    assert pytest.approx(polygon_area(line)) == 0.0


def test_self_intersection_detection():
    # Simple rectangle
    rect = [(0.1, 0.1), (0.4, 0.1), (0.4, 0.4), (0.1, 0.4)]
    assert is_self_intersecting(rect) is False

    # Bowtie / figure-8 self-intersecting polygon
    bowtie = [(0.1, 0.1), (0.4, 0.4), (0.4, 0.1), (0.1, 0.4)]
    assert is_self_intersecting(bowtie) is True


def test_point_in_polygon():
    square = [(0.2, 0.2), (0.6, 0.2), (0.6, 0.6), (0.2, 0.6)]
    assert point_in_polygon((0.4, 0.4), square) is True
    assert point_in_polygon((0.1, 0.1), square) is False
    assert point_in_polygon((0.8, 0.8), square) is False


def test_polygons_overlap():
    poly_a = [(0.1, 0.1), (0.4, 0.1), (0.4, 0.4), (0.1, 0.4)]
    poly_b = [(0.3, 0.3), (0.6, 0.3), (0.6, 0.6), (0.3, 0.6)]  # Overlaps in (0.3..0.4, 0.3..0.4)
    poly_c = [(0.7, 0.7), (0.9, 0.7), (0.9, 0.9), (0.7, 0.9)]  # Disjoint

    assert polygons_overlap(poly_a, poly_b) is True
    assert polygons_overlap(poly_a, poly_c) is False


def test_validate_normalized_polygon():
    # Valid
    assert validate_normalized_polygon([(0.1, 0.1), (0.3, 0.1), (0.3, 0.3), (0.1, 0.3)]) == []

    # Fewer than 3 points
    errs_count = validate_normalized_polygon([(0.1, 0.1), (0.2, 0.2)])
    assert any("ít nhất 3 đỉnh" in e for e in errs_count)

    # Out of bounds
    errs_oob = validate_normalized_polygon([(0.1, 0.1), (1.5, 0.1), (0.3, 0.3)])
    assert any("ngoài khoảng" in e for e in errs_oob)

    # Self-intersecting
    errs_self = validate_normalized_polygon([(0.1, 0.1), (0.4, 0.4), (0.4, 0.1), (0.1, 0.4)])
    assert any("tự cắt" in e for e in errs_self)


def test_table_zone_model_validation():
    valid_data = {
        "table_id": 1,
        "enabled": True,
        "play_polygon": [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]],
        "standing_polygon": [[0.05, 0.05], [0.35, 0.05], [0.35, 0.35], [0.05, 0.35]],
    }
    tz = TableZone.model_validate(valid_data)
    assert tz.table_id == 1

    # Invalid play polygon raises ValidationError
    invalid_data = dict(valid_data)
    invalid_data["play_polygon"] = [[0.1, 0.1], [0.4, 0.4], [0.4, 0.1], [0.1, 0.4]]
    with pytest.raises(ValidationError):
        TableZone.model_validate(invalid_data)


def test_calibration_config_overlap_detection():
    # Table 1 and Table 2 overlapping standing zones
    data = {
        "camera_id": "cam-test",
        "calibration_status": "CALIBRATED",
        "coordinate_system": "normalized_xy_0_1",
        "tables": [
            {
                "table_id": 1,
                "enabled": True,
                "play_polygon": [[0.1, 0.1], [0.25, 0.1], [0.25, 0.25], [0.1, 0.25]],
                "standing_polygon": [[0.05, 0.05], [0.35, 0.05], [0.35, 0.35], [0.05, 0.35]],
            },
            {
                "table_id": 2,
                "enabled": True,
                "play_polygon": [[0.3, 0.1], [0.45, 0.1], [0.45, 0.25], [0.3, 0.25]],
                "standing_polygon": [[0.25, 0.05], [0.55, 0.05], [0.55, 0.35], [0.25, 0.35]],  # Overlaps Table 1
            },
        ],
    }
    cfg = CalibrationConfig.model_validate(data)
    overlaps = cfg.detect_overlaps()
    assert len(overlaps) == 1
    assert overlaps[0].table_a == 1
    assert overlaps[0].table_b == 2
    assert "giao nhau" in overlaps[0].message


def test_load_and_save_calibration(tmp_path: Path):
    sample_file = tmp_path / "zones.json"
    data = {
        "camera_id": "cam-01",
        "calibration_status": "CALIBRATED",
        "coordinate_system": "normalized_xy_0_1",
        "tables": [
            {
                "table_id": 1,
                "enabled": True,
                "play_polygon": [[0.12, 0.12], [0.35, 0.12], [0.35, 0.35], [0.12, 0.35]],
                "standing_polygon": [[0.03, 0.03], [0.47, 0.03], [0.47, 0.47], [0.03, 0.47]],
            }
        ],
    }
    cfg = CalibrationConfig.model_validate(data)
    save_calibration_config(cfg, sample_file)

    loaded = load_calibration_config(sample_file)
    assert loaded.camera_id == "cam-01"
    assert len(loaded.tables) == 1
    assert loaded.tables[0].table_id == 1
