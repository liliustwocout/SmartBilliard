"""Merge labeling results from several team members and measure agreement. Pure Python."""
from __future__ import annotations

import itertools
import json
from glob import glob
from collections import Counter
from pathlib import Path
from typing import Any

from services.labeling.windows import ALL_LABELS, CORE_LABELS

FORMAT = "smartbilliard-labels-v1"


class ResultError(ValueError):
    pass


def parse_result(raw: Any, source: str = "?") -> dict[str, Any]:
    """Validate one result file produced by the labeling page."""
    if not isinstance(raw, dict) or raw.get("format") != FORMAT:
        raise ResultError(f"{source}: không phải file kết quả gán nhãn ({FORMAT})")
    member, pack = raw.get("member_id"), raw.get("pack_id")
    labels = raw.get("labels")
    if not isinstance(member, str) or not member or not isinstance(pack, str) or not isinstance(labels, dict):
        raise ResultError(f"{source}: thiếu member_id, pack_id hoặc labels")
    clean: dict[str, dict[str, str]] = {}
    for clip_id, item in labels.items():
        label = item.get("label") if isinstance(item, dict) else None
        if label not in ALL_LABELS:
            raise ResultError(f"{source}: nhãn không hợp lệ cho clip {clip_id}: {label!r}")
        clean[str(clip_id)] = {"label": label, "ts": str(item.get("ts", ""))}
    return {"member_id": member, "pack_id": pack, "annotator_name": str(raw.get("annotator_name", "")),
            "labels": clean}


def load_results(paths: list[Path]) -> list[dict[str, Any]]:
    """Load files; several files from one member are combined, a later ``ts`` wins."""
    by_member: dict[str, dict[str, Any]] = {}
    pack_id: str | None = None
    expanded: list[Path] = []
    for path in paths:
        matches = [str(path)] if path.is_file() else sorted(glob(str(path)))
        if not matches:
            raise ResultError(f"Không tìm thấy file kết quả: {path}")
        expanded.extend(Path(p) for p in matches)
    for path in expanded:
        result = parse_result(json.loads(path.read_text(encoding="utf-8")), str(path))
        if pack_id is not None and result["pack_id"] != pack_id:
            raise ResultError("Không gộp kết quả từ các batch khác nhau: clip_id có thể trùng nhau")
        pack_id = result["pack_id"]
        current = by_member.setdefault(result["member_id"], {**result, "labels": {}})
        for clip_id, item in result["labels"].items():
            old = current["labels"].get(clip_id)
            if old is None or item["ts"] >= old["ts"]:
                current["labels"][clip_id] = item
        if result["annotator_name"]:
            current["annotator_name"] = result["annotator_name"]
    return list(by_member.values())


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Cohen's kappa for two raters; None when it is undefined (no pairs or no variation)."""
    n = len(pairs)
    if n == 0:
        return None
    observed = sum(1 for a, b in pairs if a == b) / n
    a_counts, b_counts = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum((a_counts[k] / n) * (b_counts[k] / n) for k in set(a_counts) | set(b_counts))
    if expected >= 1.0:
        return None
    return (observed - expected) / (1 - expected)


def merge_results(results: list[dict[str, Any]], min_votes: int = 2) -> dict[str, Any]:
    """Decide a label per clip and report agreement.

    Only the four core labels are votes. UNSURE and INVALID never become a final label.
    status: AGREED (all valid votes equal), MAJORITY (>50% of valid votes), REVIEW (no majority),
    INSUFFICIENT (fewer than ``min_votes`` valid votes).
    """
    clips: dict[str, dict[str, str]] = {}
    for result in results:
        for clip_id, item in result["labels"].items():
            clips.setdefault(clip_id, {})[result["member_id"]] = item["label"]

    decisions: dict[str, dict[str, Any]] = {}
    for clip_id, votes in clips.items():
        valid = [v for v in votes.values() if v in CORE_LABELS]
        if len(valid) < min_votes:
            status, label = "INSUFFICIENT", None
        else:
            (top, count), = Counter(valid).most_common(1)
            if count == len(valid):
                status, label = "AGREED", top
            elif count / len(valid) > 0.5:
                status, label = "MAJORITY", top
            else:
                status, label = "REVIEW", None
        decisions[clip_id] = {"label": label, "status": status, "votes": votes}

    members = sorted({r["member_id"] for r in results})
    pairwise = []
    for a, b in itertools.combinations(members, 2):
        shared = [(clips[c][a], clips[c][b]) for c in clips
                  if a in clips[c] and b in clips[c] and clips[c][a] in CORE_LABELS and clips[c][b] in CORE_LABELS]
        agree = sum(1 for x, y in shared if x == y)
        pairwise.append({"members": [a, b], "shared_clips": len(shared),
                         "percent_agreement": round(agree / len(shared), 4) if shared else None,
                         "kappa": None if (k := cohen_kappa(shared)) is None else round(k, 4)})

    status_counts = Counter(d["status"] for d in decisions.values())
    report = {
        "members": {r["member_id"]: {"name": r["annotator_name"], "labeled": len(r["labels"]),
                                     "by_label": dict(Counter(i["label"] for i in r["labels"].values()))}
                    for r in results},
        "clips_total": len(decisions),
        "status": dict(status_counts),
        "final_label_distribution": dict(Counter(d["label"] for d in decisions.values() if d["label"])),
        "pairwise": pairwise,
        "review_clip_ids": sorted(c for c, d in decisions.items() if d["status"] == "REVIEW"),
        "insufficient_clip_ids": sorted(c for c, d in decisions.items() if d["status"] == "INSUFFICIENT"),
    }
    return {"decisions": decisions, "report": report}
