"""Synthetic geometry tests; these do not measure accuracy on camera footage."""
import base64

import cv2
import numpy as np
import pytest

from apps.api.config import Settings
from services.vision.auto_calibration import find_table_surfaces, propose_table_zones
from services.vision.auto_roi_config import AutoRoiConfig
from services.vision.calibration import CalibrationConfig, TableZone, polygon_area


@pytest.fixture
def cloth_frame():
    frame = np.full((600, 1000, 3), 60, dtype=np.uint8)
    far = [[460, 80], [720, 100], [700, 185], [440, 155]]
    near = [[180, 290], [640, 330], [600, 510], [100, 430]]
    cv2.fillConvexPoly(frame, np.array(far), (190, 105, 25))
    cv2.fillConvexPoly(frame, np.array(near), (30, 170, 40))
    cv2.rectangle(frame, (300, 350), (370, 390), (30, 30, 30), -1)  # partial occlusion
    cv2.rectangle(frame, (10, 10), (35, 25), (190, 105, 25), -1)  # small coloured distractor
    return frame, near, far


def test_attached_blue_sleeve_does_not_expand_the_table_to_the_person(cloth_frame):
    frame, _, far = cloth_frame
    cv2.rectangle(frame, (495, 20), (530, 110), (190, 105, 25), -1)
    surfaces = find_table_surfaces(frame, AutoRoiConfig())
    assert len(surfaces) == 2
    found = surfaces[1] * np.array([1000, 600], dtype=np.float32)
    expected = np.array(far, dtype=np.float32)
    intersection, _ = cv2.intersectConvexConvex(found, expected)
    union = cv2.contourArea(found) + cv2.contourArea(expected) - intersection
    assert intersection / union > 0.85


def test_upright_blue_clothing_is_rejected_for_landscape_table_views(cloth_frame):
    frame, _, _ = cloth_frame
    cv2.rectangle(frame, (820, 210), (930, 530), (190, 105, 25), -1)
    assert len(find_table_surfaces(frame, AutoRoiConfig())) == 2
    assert len(find_table_surfaces(frame, AutoRoiConfig(max_long_edge_angle_degrees=90))) == 3


def test_detects_perspective_surfaces_and_surrounding_zones(cloth_frame):
    frame, _, _ = cloth_frame
    result = propose_table_zones(frame, CalibrationConfig(tables=[]), 4, AutoRoiConfig())
    assert result["detected_count"] == 2
    assert result["updated_table_ids"] == [1, 2]
    assert result["method"] == "opencv_cloth_contours_v1"
    assert result["requires_review"] is True
    validated = CalibrationConfig.model_validate(result["config"])
    assert len(validated.tables) == 2
    for table in validated.tables:
        assert len(table.play_polygon) == 4
        assert polygon_area(table.standing_polygon) > polygon_area(table.play_polygon)
        standing = np.array(table.standing_polygon, dtype=np.float32)
        assert all(cv2.pointPolygonTest(standing, tuple(point), False) >= 0 for point in table.play_polygon)
    assert np.mean(validated.tables[0].play_polygon, axis=0)[1] > np.mean(validated.tables[1].play_polygon, axis=0)[1]
    jpeg = base64.b64decode(result["preview_data_url"].split(",", 1)[1])
    assert cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR).shape == frame.shape


def test_keeps_table_ids_enabled_flags_and_unmatched_manual_roi(cloth_frame):
    frame, near, far = cloth_frame
    normalize = lambda points: (np.array(points) / [1000, 600]).tolist()
    current = CalibrationConfig(tables=[
        TableZone(table_id=4, enabled=False, play_polygon=normalize(far), standing_polygon=normalize(far)),
        TableZone(table_id=2, play_polygon=normalize(near), standing_polygon=normalize(near)),
        TableZone(table_id=3, play_polygon=[[.8, .7], [.95, .7], [.95, .95], [.8, .95]],
                  standing_polygon=[[.75, .65], [1, .65], [1, 1], [.75, 1]]),
    ])
    original = current.model_dump()
    result = propose_table_zones(frame, current, 4, AutoRoiConfig())
    tables = {table["table_id"]: table for table in result["config"]["tables"]}
    assert result["updated_table_ids"] == [2, 4]
    assert tables[4]["enabled"] is False
    assert tables[3] == original["tables"][2]
    assert current.model_dump() == original


def test_no_surface_and_capacity_limits_preserve_existing_roi(cloth_frame):
    frame, _, _ = cloth_frame
    current = CalibrationConfig(tables=[
        TableZone(table_id=1, play_polygon=[[.8, .7], [.95, .7], [.95, .95], [.8, .95]],
                  standing_polygon=[[.75, .65], [1, .65], [1, 1], [.75, 1]]),
    ])
    full = propose_table_zones(frame, current, 1, AutoRoiConfig())
    assert full["detected_count"] == 2 and full["updated_table_ids"] == []
    assert full["config"] == current.model_dump()
    blank = propose_table_zones(np.full_like(frame, 60), current, 4, AutoRoiConfig())
    assert blank["detected_count"] == 0 and blank["config"] == current.model_dump()
    with pytest.raises(ValueError):
        find_table_surfaces(np.array([]), AutoRoiConfig())


@pytest.mark.parametrize("overrides", [
    {"hue_min": 135, "hue_max": 35}, {"morphology_size": 4},
    {"min_area_ratio": .6}, {"standing_margin": -1}, {"min_aspect_ratio": 10},
])
def test_invalid_auto_roi_thresholds_are_rejected(overrides):
    with pytest.raises(ValueError):
        AutoRoiConfig(**overrides)


def test_invalid_auto_roi_file_fails_startup(tmp_path, monkeypatch):
    path = tmp_path / "invalid_auto_roi.toml"
    path.write_text("standing_margin = -1\n", encoding="utf-8")
    monkeypatch.setenv("AUTO_ROI_CONFIG", str(path))
    with pytest.raises(ValueError):
        Settings.from_env()
