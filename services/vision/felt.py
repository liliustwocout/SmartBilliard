"""Felt Motion Detector for Billiard Cloth Activity (Balls / Cue Motion on Table).

Uses ultra-lightweight masked frame differencing on the table play_polygon to detect
ball rolling, collisions, and cue intrusion over the cloth with minimal CPU overhead (<0.5ms).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np

Point = tuple[float, float]
Polygon = Sequence[Point]


@dataclass(frozen=True)
class FeltMotionResult:
    has_motion: bool
    motion_energy: float
    active_pixels: int
    motion_ratio: float
    is_mass_disturbance: bool = False


class FeltMotionDetector:
    """Detects movement of billiard balls and cue stick tips on the table play surface."""

    def __init__(
        self,
        *,
        pixel_threshold: int = 22,
        min_active_pixels: int = 15,
        min_motion_ratio: float = 0.0003,
        min_motion_energy: float = 0.004,
        blur_kernel_size: int = 5,
        max_ball_motion_ratio: float = 0.12,
    ) -> None:
        self.pixel_threshold = pixel_threshold
        self.min_active_pixels = min_active_pixels
        self.min_motion_ratio = min_motion_ratio
        self.min_motion_energy = min_motion_energy
        self.blur_kernel_size = blur_kernel_size
        self.max_ball_motion_ratio = max_ball_motion_ratio
        self._prev_rois: dict[int, np.ndarray] = {}
        self._prev_person_masks: dict[int, np.ndarray] = {}
        self._morph_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

    def reset(self, table_id: int | None = None) -> None:
        """Reset cached previous frame for a specific table or all tables."""
        if table_id is None:
            self._prev_rois.clear()
            self._prev_person_masks.clear()
        else:
            self._prev_rois.pop(table_id, None)
            self._prev_person_masks.pop(table_id, None)

    def detect_motion(
        self,
        frame: np.ndarray,
        table_id: int,
        play_polygon: Polygon,
        *,
        exclude_bboxes: Sequence[tuple[float, float, float, float]] = (),
    ) -> FeltMotionResult:
        """Analyze motion on the cloth surface of the specified table.

        Args:
            frame: Full BGR or Grayscale frame from camera.
            table_id: Identifier of the table.
            play_polygon: Sequence of (x, y) coordinates normalized to [0.0, 1.0].

        Returns:
            FeltMotionResult containing motion state and energy metrics.
        """
        if frame is None or frame.size == 0 or len(play_polygon) < 3:
            return FeltMotionResult(
                has_motion=False,
                motion_energy=0.0,
                active_pixels=0,
                motion_ratio=0.0,
            )

        h, w = frame.shape[:2]

        # Convert normalized polygon points to pixel coordinates
        pts_px = np.array(
            [[int(x * w), int(y * h)] for x, y in play_polygon],
            dtype=np.int32,
        )

        # Bounding box of play_polygon
        min_x = max(0, int(np.min(pts_px[:, 0])))
        min_y = max(0, int(np.min(pts_px[:, 1])))
        max_x = min(w, int(np.max(pts_px[:, 0])))
        max_y = min(h, int(np.max(pts_px[:, 1])))

        roi_w = max_x - min_x
        roi_h = max_y - min_y
        if roi_w < 10 or roi_h < 10:
            return FeltMotionResult(
                has_motion=False,
                motion_energy=0.0,
                active_pixels=0,
                motion_ratio=0.0,
            )

        # Crop ROI
        roi = frame[min_y:max_y, min_x:max_x]
        if roi.ndim == 3:
            roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        else:
            roi_gray = roi

        # Gaussian blur to suppress camera noise
        ksize = self.blur_kernel_size
        if ksize % 2 == 0:
            ksize += 1
        blurred = cv2.GaussianBlur(roi_gray, (ksize, ksize), 0)

        # Build binary mask of the polygon shifted to ROI coordinates
        shifted_poly = pts_px.copy()
        shifted_poly[:, 0] -= min_x
        shifted_poly[:, 1] -= min_y

        mask = np.zeros((roi_h, roi_w), dtype=np.uint8)
        cv2.fillPoly(mask, [shifted_poly], 255)
        poly_area = cv2.countNonZero(mask)
        if poly_area < 20:
            return FeltMotionResult(
                has_motion=False,
                motion_energy=0.0,
                active_pixels=0,
                motion_ratio=0.0,
            )

        # Mask out detected person bounding boxes over the felt to suppress limb/shadow ghosts
        person_mask = np.zeros((roi_h, roi_w), dtype=np.uint8)
        for bx1, by1, bx2, by2 in exclude_bboxes:
            rx1 = max(0, int(bx1 * w) - min_x - 3)
            ry1 = max(0, int(by1 * h) - min_y - 3)
            rx2 = min(roi_w, int(bx2 * w) - min_x + 3)
            ry2 = min(roi_h, int(by2 * h) - min_y + 3)
            if rx2 > rx1 and ry2 > ry1:
                person_mask[ry1:ry2, rx1:rx2] = 255

        prev_person_mask = self._prev_person_masks.get(table_id)
        self._prev_person_masks[table_id] = person_mask

        # Compare with previous frame
        prev = self._prev_rois.get(table_id)
        self._prev_rois[table_id] = blurred

        if prev is None or prev.shape != blurred.shape:
            # First observation has no baseline for diff
            return FeltMotionResult(
                has_motion=False,
                motion_energy=0.0,
                active_pixels=0,
                motion_ratio=0.0,
            )

        combined_person_mask = person_mask
        if prev_person_mask is not None and prev_person_mask.shape == person_mask.shape:
            combined_person_mask = cv2.bitwise_or(person_mask, prev_person_mask)

        if cv2.countNonZero(combined_person_mask) > 0:
            effective_mask = cv2.bitwise_and(mask, cv2.bitwise_not(combined_person_mask))
        else:
            effective_mask = mask

        visible_area = cv2.countNonZero(effective_mask)
        if visible_area < 20:
            return FeltMotionResult(
                has_motion=False,
                motion_energy=0.0,
                active_pixels=0,
                motion_ratio=0.0,
            )

        # Absolute frame differencing
        diff = cv2.absdiff(blurred, prev)
        diff_masked = cv2.bitwise_and(diff, diff, mask=effective_mask)

        # Thresholding
        _, thresh = cv2.threshold(
            diff_masked,
            self.pixel_threshold,
            255,
            cv2.THRESH_BINARY,
        )

        # Noise cleanup
        opened = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, self._morph_kernel)

        active_pixels = int(cv2.countNonZero(opened))
        motion_ratio = active_pixels / float(visible_area)
        motion_energy = float(np.sum(diff_masked) / (float(visible_area) * 255.0))

        if motion_ratio > self.max_ball_motion_ratio:
            return FeltMotionResult(
                has_motion=False,
                motion_energy=motion_energy,
                active_pixels=active_pixels,
                motion_ratio=motion_ratio,
                is_mass_disturbance=True,
            )

        has_motion = (
            (active_pixels >= self.min_active_pixels and motion_ratio >= self.min_motion_ratio)
            or (motion_energy >= self.min_motion_energy and active_pixels >= (self.min_active_pixels // 2))
        )

        return FeltMotionResult(
            has_motion=bool(has_motion),
            motion_energy=motion_energy,
            active_pixels=active_pixels,
            motion_ratio=motion_ratio,
        )
