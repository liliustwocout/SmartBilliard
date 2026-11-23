"""Visual annotation engine for live camera frames (Detections, Foot Anchors, Zones, Track IDs).

Renders transparent table ROI polygons, player bounding boxes, foot anchor points,
and status HUD overlays for live streaming (MJPEG) and debugging.
"""
from __future__ import annotations

import cv2
import numpy as np

from services.vision.calibration import CalibrationConfig, TableZone
from services.vision.contracts import Detection, Keypoint
from services.vision.mapper import TableObservationSummary

_POSE_EDGES = (
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
)


def _draw_skeleton(
    annotated: np.ndarray,
    keypoints: tuple[Keypoint, ...] | None,
    width: int,
    height: int,
    color: tuple[int, int, int],
    min_conf: float = 0.35,
) -> None:
    if not keypoints or len(keypoints) < 17:
        return
    pts: dict[int, tuple[int, int]] = {}
    for idx, (kx, ky, kconf) in enumerate(keypoints):
        if kconf >= min_conf:
            pts[idx] = (
                max(0, min(width - 1, int(kx * width))),
                max(0, min(height - 1, int(ky * height))),
            )
    for a, b in _POSE_EDGES:
        if a in pts and b in pts:
            cv2.line(annotated, pts[a], pts[b], color, 2, cv2.LINE_AA)
    for idx, pt in pts.items():
        joint_color = (0, 230, 255) if idx in (9, 10) else (255, 255, 255)
        cv2.circle(annotated, pt, 4 if idx in (9, 10) else 3, joint_color, -1, cv2.LINE_AA)


def draw_frame_annotations(
    frame: np.ndarray,
    detections: list[Detection] | None = None,
    summaries: dict[int, TableObservationSummary] | None = None,
    config: CalibrationConfig | None = None,
    fps: float = 0.0,
    inference_fps: float | None = None,
    source_type: str = "CAMERA",
    camera_id: str = "cam-01",
) -> np.ndarray:
    """Annotate a BGR frame with ROI zones, detections, and a status HUD.

    Args:
        frame: Original BGR image as a numpy ndarray.
        detections: List of current frame detections with normalized coordinates.
        summaries: Mapping of table_id -> TableObservationSummary for zone state.
        config: CalibrationConfig containing table and standing polygon definitions.
        fps: Measured processing frame rate.
        source_type: 'CAMERA' or 'VIDEO'.
        camera_id: Identifier for camera display.

    Returns:
        New annotated BGR frame.
    """
    if frame is None or frame.size == 0:
        return frame

    annotated = frame.copy()
    height, width = annotated.shape[:2]

    # Create an overlay copy for semi-transparent polygons
    overlay = annotated.copy()

    # Determine which tables currently have active players
    active_tables: set[int] = set()
    table_to_tracks: dict[int, list[int]] = {}
    if summaries:
        for tid, summary in summaries.items():
            if summary.people_count > 0 or summary.present:
                active_tables.add(tid)
                table_to_tracks[tid] = summary.track_ids

    # 1. Draw Table Zones (Play & Standing polygons)
    if config and config.tables:
        for table in config.tables:
            is_active = table.enabled and table.table_id in active_tables

            # 1a. Standing zone (Amber / Orange, muted gray when disabled)
            if len(table.standing_polygon) >= 3:
                stand_pts = np.array(
                    [[int(x * width), int(y * height)] for x, y in table.standing_polygon],
                    dtype=np.int32,
                )
                if not table.enabled:
                    stand_color = (120, 125, 130)
                else:
                    stand_color = (15, 175, 245) if is_active else (25, 130, 190)  # BGR
                cv2.fillPoly(overlay, [stand_pts], stand_color)
                cv2.polylines(annotated, [stand_pts], isClosed=True, color=stand_color, thickness=1, lineType=cv2.LINE_AA)

            # 1b. Play zone (Emerald Green, muted gray when disabled)
            if len(table.play_polygon) >= 3:
                play_pts = np.array(
                    [[int(x * width), int(y * height)] for x, y in table.play_polygon],
                    dtype=np.int32,
                )
                table_summary = summaries.get(table.table_id) if summaries else None
                has_felt = bool(table_summary and getattr(table_summary, "felt_motion", False))
                if not table.enabled:
                    play_fill = (95, 100, 105)
                    play_border = (135, 140, 145)
                elif has_felt:
                    play_fill = (35, 195, 80)
                    play_border = (0, 255, 230)  # Cyan glowing border for rolling balls
                else:
                    play_fill = (45, 180, 50) if is_active else (35, 120, 35)  # BGR
                    play_border = (80, 230, 90) if is_active else (55, 170, 60)
                cv2.fillPoly(overlay, [play_pts], play_fill)
                cv2.polylines(annotated, [play_pts], isClosed=True, color=play_border, thickness=2, lineType=cv2.LINE_AA)

                # Center label for the table
                cx = int(np.mean(play_pts[:, 0]))
                cy = int(np.mean(play_pts[:, 1]))
                status_text = f"BAN {table.table_id:02}"
                if not table.enabled:
                    sub_text = "TAM TAT"
                    label_color = (170, 175, 180)
                elif table_summary and table_summary.activity_state == "PLAYING":
                    if has_felt:
                        sub_text = "CHOI (BONG LAN)"
                    elif table_summary.activity_reason == "PLAYER_NAVIGATING":
                        sub_text = "CHOI (DI CHUYEN)"
                    else:
                        sub_text = "DANG CHOI"
                    label_color = (100, 255, 120)
                elif table_summary and table_summary.present and table_summary.activity_state == "NOT_PLAYING":
                    if "CLEANING" in table_summary.activity_reason:
                        sub_text = "DANG DON BAN"
                        label_color = (190, 190, 190)
                    else:
                        sub_text = "DUNG XEM"
                        label_color = (255, 210, 120)
                elif is_active:
                    sub_text = "CHUA RO"
                    label_color = (240, 200, 100)
                else:
                    sub_text = "TRONG"
                    label_color = (220, 220, 220)

                # Background badge for table label
                (tw, th), _ = cv2.getTextSize(status_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                badge_x1 = max(0, cx - tw // 2 - 6)
                badge_y1 = max(0, cy - th - 12)
                badge_x2 = min(width - 1, cx + tw // 2 + 6)
                badge_y2 = min(height - 1, cy + 14)
                cv2.rectangle(overlay, (badge_x1, badge_y1), (badge_x2, badge_y2), (18, 18, 22), -1)

                cv2.putText(annotated, status_text, (cx - tw // 2, cy - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.48, label_color, 1, cv2.LINE_AA)
                (stw, sth), _ = cv2.getTextSize(sub_text, cv2.FONT_HERSHEY_SIMPLEX, 0.35, 1)
                cv2.putText(annotated, sub_text, (cx - stw // 2, cy + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 210, 205), 1, cv2.LINE_AA)

        # Blend semi-transparent polygon fills (alpha = 0.22)
        cv2.addWeighted(overlay, 0.22, annotated, 0.78, 0, annotated)

    # 2. Draw Detections & Foot Anchors
    track_to_table: dict[int, int] = {}
    if summaries:
        for tid, summary in summaries.items():
            for trk in summary.track_ids:
                track_to_table[trk] = tid

    person_count = 0
    cue_count = 0
    if detections:
        for det in detections:
            x1 = max(0, min(width - 1, int(det.bbox[0] * width)))
            y1 = max(0, min(height - 1, int(det.bbox[1] * height)))
            x2 = max(0, min(width - 1, int(det.bbox[2] * width)))
            y2 = max(0, min(height - 1, int(det.bbox[3] * height)))

            if det.kind == "cue":
                cue_count += 1
                cue_color = (0, 215, 255)
                cv2.rectangle(annotated, (x1, y1), (x2, y2), cue_color, 2, cv2.LINE_AA)
                cue_label = f"Gay thu nghiem [{int(det.confidence * 100)}%]"
                (lw, lh), _ = cv2.getTextSize(cue_label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
                lbl_y1 = max(0, y1 - lh - 6)
                cv2.rectangle(annotated, (x1, lbl_y1), (min(width - 1, x1 + lw + 8), y1), (15, 15, 20), -1)
                cv2.putText(annotated, cue_label, (x1 + 4, max(lh + 2, y1 - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, cue_color, 1, cv2.LINE_AA)
                continue

            person_count += 1
            tid = track_to_table.get(det.track_id) if det.track_id is not None else None

            # Color coding: Green for assigned table, Orange for ambiguous/outside
            summary = summaries.get(tid) if (tid is not None and summaries) else None
            act_suffix = ""
            if tid is not None:
                if summary and summary.activity_state == "PLAYING":
                    box_color = (0, 230, 100)  # Green
                    if getattr(summary, "felt_motion", False):
                        act_suffix = " [BONG LAN]"
                    elif summary.activity_reason == "PLAYER_NAVIGATING":
                        act_suffix = " [DI CHUYEN]"
                    else:
                        act_suffix = " [CHOI]"
                elif summary and summary.activity_state == "NOT_PLAYING":
                    if "CLEANING" in summary.activity_reason:
                        box_color = (180, 180, 180)  # Silver/gray
                        act_suffix = " [DON BAN]"
                    else:
                        box_color = (200, 200, 160)  # Slate
                        act_suffix = " [XEM]"
                else:
                    box_color = (0, 230, 100)  # Green
                tag_label = f"ID #{det.track_id} -> Ban {tid:02}{act_suffix}"
            else:
                box_color = (60, 180, 245)  # Amber / outside
                trk_label = f"ID #{det.track_id}" if det.track_id is not None else "Person"
                tag_label = f"{trk_label} (Ngoai)"

            # Bounding box & Pose Skeleton
            cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 2, cv2.LINE_AA)
            _draw_skeleton(annotated, getattr(det, "keypoints", None), width, height, box_color)

            # Foot Anchor point (cx, y2)
            if det.foot_anchor:
                fx = max(0, min(width - 1, int(det.foot_anchor[0] * width)))
                fy = max(0, min(height - 1, int(det.foot_anchor[1] * height)))
            else:
                fx = (x1 + x2) // 2
                fy = y2

            # Glowing foot anchor: Outer white ring + solid red center
            cv2.circle(annotated, (fx, fy), 6, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.circle(annotated, (fx, fy), 4, (0, 0, 255), -1, cv2.LINE_AA)

            # Label banner
            conf_str = f"{int(det.confidence * 100)}%"
            label_full = f"{tag_label} [{conf_str}]"
            (lw, lh), _ = cv2.getTextSize(label_full, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)

            lbl_y1 = max(0, y1 - lh - 8)
            lbl_y2 = y1
            lbl_x1 = x1
            lbl_x2 = min(width - 1, x1 + lw + 8)

            cv2.rectangle(annotated, (lbl_x1, lbl_y1), (lbl_x2, lbl_y2), (15, 15, 20), -1)
            cv2.rectangle(annotated, (lbl_x1, lbl_y1), (lbl_x2, lbl_y2), box_color, 1)
            cv2.putText(annotated, label_full, (lbl_x1 + 4, lbl_y2 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)

    # 3. Status HUD Bar on top
    hud_height = 28
    hud_overlay = annotated[:hud_height, :].copy()
    cv2.rectangle(hud_overlay, (0, 0), (width, hud_height), (12, 16, 22), -1)
    cv2.addWeighted(hud_overlay, 0.85, annotated[:hud_height, :], 0.15, 0, annotated[:hud_height, :])
    cv2.line(annotated, (0, hud_height), (width, hud_height), (40, 50, 65), 1)

    # Status indicator dot: Green if processing, Blue if video
    dot_color = (0, 240, 100) if source_type == "CAMERA" else (240, 180, 40)
    cv2.circle(annotated, (16, 14), 5, dot_color, -1, cv2.LINE_AA)

    act_count = len(active_tables)
    ai_text = f" | AI FPS: {inference_fps:.1f}" if inference_fps is not None else ""
    hud_text = f"LIVE {source_type} ({camera_id}) | Video FPS: {fps:.1f}{ai_text} | Nguoi: {person_count} | Gay: {cue_count} | Ban hoat dong: {act_count}"
    cv2.putText(annotated, hud_text, (28, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (230, 235, 240), 1, cv2.LINE_AA)

    # Right HUD clock hint
    time_text = "SMARTBILLIARD AI VISION"
    (rw, _), _ = cv2.getTextSize(time_text, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
    cv2.putText(annotated, time_text, (width - rw - 14, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (140, 150, 165), 1, cv2.LINE_AA)

    return annotated


def create_standby_frame_jpeg(
    message: str = "CAMERA CHUA KHOI DONG",
    sub_message: str = "Nhan 'Bat Camera AI' de xem luong video truc tiep",
    width: int = 960,
    height: int = 540,
) -> bytes:
    """Generate a clean standby placeholder frame as JPEG when camera is stopped."""
    img = np.full((height, width, 3), fill_value=18, dtype=np.uint8)

    # Grid pattern
    grid = 40
    for x in range(0, width, grid):
        cv2.line(img, (x, 0), (x, height), (26, 28, 34), 1)
    for y in range(0, height, grid):
        cv2.line(img, (0, y), (width, y), (26, 28, 34), 1)

    # Center card
    card_w, card_h = 440, 140
    cx1 = (width - card_w) // 2
    cy1 = (height - card_h) // 2
    cx2 = cx1 + card_w
    cy2 = cy1 + card_h

    cv2.rectangle(img, (cx1, cy1), (cx2, cy2), (28, 32, 42), -1)
    cv2.rectangle(img, (cx1, cy1), (cx2, cy2), (50, 60, 75), 1)

    # Text
    (tw, th), _ = cv2.getTextSize(message, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
    cv2.putText(img, message, ((width - tw) // 2, cy1 + 50), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (220, 230, 240), 2, cv2.LINE_AA)

    (sw, _), _ = cv2.getTextSize(sub_message, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
    cv2.putText(img, sub_message, ((width - sw) // 2, cy1 + 90), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (130, 140, 155), 1, cv2.LINE_AA)

    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    return buf.tobytes() if ok else b""
