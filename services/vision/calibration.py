"""Zone calibration data models, geometry validation, and persistence (SB-10)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator


Point = tuple[float, float]
Polygon = list[Point]


def polygon_area(poly: Polygon) -> float:
    """Calculate the signed area of a polygon using the Shoelace formula."""
    n = len(poly)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += poly[i][0] * poly[j][1]
        area -= poly[j][0] * poly[i][1]
    return abs(area) / 2.0


def _ccw(a: Point, b: Point, c: Point) -> bool:
    """Check if three points are listed in counterclockwise order."""
    return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])


def segments_intersect(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    """Check whether line segment p1-p2 strictly intersects segment p3-p4."""
    # Check if endpoints are identical
    if p1 == p3 or p1 == p4 or p2 == p3 or p2 == p4:
        return False
    return (_ccw(p1, p3, p4) != _ccw(p2, p3, p4)) and (_ccw(p1, p2, p3) != _ccw(p1, p2, p4))


def is_self_intersecting(poly: Polygon) -> bool:
    """Check if a polygon's boundary intersects itself (non-simple polygon)."""
    n = len(poly)
    if n < 4:
        return False
    for i in range(n):
        p1, p2 = poly[i], poly[(i + 1) % n]
        for j in range(i + 2, n):
            if (i == 0 and j == n - 1):
                continue
            p3, p4 = poly[j], poly[(j + 1) % n]
            if segments_intersect(p1, p2, p3, p4):
                return True
    return False


def point_in_polygon(point: Point, poly: Polygon) -> bool:
    """Ray casting algorithm to determine if point (x, y) is inside poly."""
    x, y = point
    n = len(poly)
    if n < 3:
        return False
    inside = False
    p1x, p1y = poly[0]
    for i in range(n + 1):
        p2x, p2y = poly[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xints = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xints:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def polygons_overlap(poly_a: Polygon, poly_b: Polygon) -> bool:
    """Check if two polygons overlap (either boundary segments intersect or one contains points of another)."""
    if len(poly_a) < 3 or len(poly_b) < 3:
        return False

    # Check edge-edge intersection
    for i in range(len(poly_a)):
        a1, a2 = poly_a[i], poly_a[(i + 1) % len(poly_a)]
        for j in range(len(poly_b)):
            b1, b2 = poly_b[j], poly_b[(j + 1) % len(poly_b)]
            if segments_intersect(a1, a2, b1, b2):
                return True

    # Check if a vertex of A is inside B
    for p in poly_a:
        if point_in_polygon(p, poly_b):
            return True

    # Check if a vertex of B is inside A
    for p in poly_b:
        if point_in_polygon(p, poly_a):
            return True

    return False


def validate_normalized_polygon(poly: Polygon, name: str = "polygon") -> list[str]:
    """Validate vertex count, coordinate bounds, area, and self-intersection."""
    errors = []
    if len(poly) < 3:
        errors.append(f"{name} phải có ít nhất 3 đỉnh (hiện có {len(poly)})")
        return errors

    for idx, (x, y) in enumerate(poly):
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            errors.append(f"Đỉnh #{idx + 1} của {name} có tọa độ ({x:.2f}, {y:.2f}) nằm ngoài khoảng chuẩn hóa [0.0, 1.0]")

    area = polygon_area(poly)
    if area < 0.0001:
        errors.append(f"{name} có diện tích quá nhỏ hoặc các đỉnh thẳng hàng (diện tích = {area:.6f})")

    if is_self_intersecting(poly):
        errors.append(f"{name} tự cắt chính nó (tạo thành hình không hợp lệ)")

    return errors


class TableZone(BaseModel):
    table_id: int = Field(ge=1, le=8)
    enabled: bool = True
    play_polygon: list[list[float]]
    standing_polygon: list[list[float]]

    @model_validator(mode="after")
    def check_polygons(self):
        play_pts = [tuple(p) for p in self.play_polygon]
        errors = validate_normalized_polygon(play_pts, f"Bàn {self.table_id} - Vùng chơi")
        if errors:
            raise ValueError("; ".join(errors))

        standing_pts = [tuple(p) for p in self.standing_polygon]
        errors = validate_normalized_polygon(standing_pts, f"Bàn {self.table_id} - Vùng đứng")
        if errors:
            raise ValueError("; ".join(errors))

        return self


class ZoneOverlapWarning(BaseModel):
    table_a: int
    table_b: int
    message: str


class CalibrationConfig(BaseModel):
    camera_id: str = "cam-01"
    calibration_status: str = "CALIBRATED"
    coordinate_system: str = "normalized_xy_0_1"
    tables: list[TableZone]

    def detect_overlaps(self) -> list[ZoneOverlapWarning]:
        """Detect overlapping standing zones between distinct active tables."""
        warnings: list[ZoneOverlapWarning] = []
        enabled_tables = [t for t in self.tables if t.enabled]
        n = len(enabled_tables)
        for i in range(n):
            for j in range(i + 1, n):
                t_a = enabled_tables[i]
                t_b = enabled_tables[j]
                poly_a = [tuple(p) for p in t_a.standing_polygon]
                poly_b = [tuple(p) for p in t_b.standing_polygon]
                if polygons_overlap(poly_a, poly_b):
                    warnings.append(
                        ZoneOverlapWarning(
                            table_a=t_a.table_id,
                            table_b=t_b.table_id,
                            message=f"Vùng đứng của Bàn {t_a.table_id} và Bàn {t_b.table_id} bị giao nhau. Vùng giao này sẽ kích hoạt trạng thái AMBIGUOUS khi có người xuất hiện.",
                        )
                    )
        return warnings


def load_calibration_config(config_path: str | Path, fallback_path: str | Path | None = None) -> CalibrationConfig:
    """Load calibration config from json file, falling back if not found."""
    p_config = Path(config_path)
    p_fallback = Path(fallback_path) if fallback_path else None
    target = p_config if p_config.exists() else (p_fallback if p_fallback and p_fallback.exists() else None)
    if target is None:
        raise FileNotFoundError(f"Neither {config_path} nor fallback exists")

    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)
    return CalibrationConfig.model_validate(data)


def save_calibration_config(config: CalibrationConfig, save_path: str | Path) -> None:
    """Save calibration configuration to JSON with pretty indentation."""
    p_save = Path(save_path)
    p_save.parent.mkdir(parents=True, exist_ok=True)
    with open(p_save, "w", encoding="utf-8") as f:
        json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)
