"""Apply explicit clip adjudications without manufacturing extra annotator votes."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.labeling.windows import CORE_LABELS, EXTRA_LABELS

REVIEW_FORMAT = "smartbilliard-adjudication-v1"


def apply_review(index: dict[str, Any], existing: list[dict[str, Any]],
                 review: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return a reviewed index, accepted labels and exclusions; leave inputs untouched.

    Review rows must cover exactly the clips without an existing agreed/majority label.
    A sample span can retain a clear part of a mixed-action clip. AI decisions remain
    AI_ADJUDICATED and never enter human agreement/kappa calculations.
    """
    if not isinstance(review, dict) or review.get("format") != REVIEW_FORMAT or review.get("pack_id") != index["batch"]:
        raise ValueError("Review format or batch does not match the clip index")
    if review.get("reviewer_type") != "AI" or not review.get("reviewer"):
        raise ValueError("An identified AI reviewer is required")
    clips = index["clips"]
    accepted: dict[str, dict[str, Any]] = {}
    for row in existing:
        cid = row["clip_id"]
        if cid not in clips or cid in accepted or row.get("label") not in CORE_LABELS:
            raise ValueError(f"Invalid or duplicate existing label: {cid}")
        if row.get("status") not in {"AGREED", "MAJORITY"}:
            raise ValueError(f"Existing label is not consensus: {cid}")
        accepted[cid] = deepcopy(row)
    rows = review.get("clips")
    if not isinstance(rows, list):
        raise ValueError("Review clips must be a list")
    decisions: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each review row must be an object")
        cid = row.get("clip_id")
        if not isinstance(cid, str) or cid not in clips or cid in decisions:
            raise ValueError(f"Unknown or duplicate reviewed clip: {cid}")
        if cid in accepted:
            raise ValueError(f"Review cannot overwrite existing consensus: {cid}")
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            raise ValueError(f"A reason is required: {cid}")
        outcome, label = row.get("outcome"), row.get("label")
        if not ((outcome == "ACCEPT" and label in CORE_LABELS)
                or (outcome == "EXCLUDE" and label in EXTRA_LABELS)):
            raise ValueError(f"Invalid review outcome/label: {cid}")
        decisions[cid] = row
    if set(decisions) != set(clips) - set(accepted):
        raise ValueError("Review must cover every non-consensus clip exactly once")

    reviewed_clips = {cid: deepcopy(clips[cid]) for cid in accepted}
    excluded = []
    for cid, row in decisions.items():
        decision = {**deepcopy(row), "annotation_source": "AI_ADJUDICATION",
                    "reviewer": review["reviewer"], "reviewer_type": "AI", "human_reviewed": False}
        if row["outcome"] == "EXCLUDE":
            excluded.append(decision)
            continue
        entry = deepcopy(clips[cid])
        n = len(entry["frame_indices"])
        start, stop = row.get("sample_start", 0), row.get("sample_stop", n)
        if type(start) is not int or type(stop) is not int or not 0 <= start < stop <= n or stop - start < 2:
            raise ValueError(f"Invalid sample span: {cid}")
        for field in ("frame_indices", "bboxes", "keypoints"):
            if len(entry[field]) != n:
                raise ValueError(f"Unaligned sample arrays: {cid}")
        frames = entry["frame_indices"]
        if any(b <= a for a, b in zip(frames, frames[1:])) or entry["t_end"] <= entry["t_start"]:
            raise ValueError(f"Invalid clip timeline: {cid}")
        seconds_per_frame = (entry["t_end"] - entry["t_start"]) / (frames[-1] - frames[0])
        begin = entry["t_start"]
        entry["t_start"] = begin + (frames[start] - frames[0]) * seconds_per_frame
        entry["t_end"] = begin + (frames[stop - 1] - frames[0]) * seconds_per_frame
        if entry["t_end"] - entry["t_start"] < 2.0 - 1e-6:
            raise ValueError(f"Accepted action span must last at least two seconds: {cid}")
        for field in ("frame_indices", "bboxes", "keypoints"):
            entry[field] = entry[field][start:stop]
        entry["review_span"] = {"sample_start": start, "sample_stop": stop,
                                "parent_t_start": clips[cid]["t_start"], "parent_t_end": clips[cid]["t_end"]}
        reviewed_clips[cid] = entry
        accepted[cid] = {**decision, "status": "AI_ADJUDICATED", "sample_start": start, "sample_stop": stop}
    return ({**deepcopy(index), "clips": reviewed_clips},
            [accepted[cid] for cid in sorted(accepted)], sorted(excluded, key=lambda r: r["clip_id"]))
