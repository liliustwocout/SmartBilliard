"""Adjudication preserves consensus, exclusions, timelines and truthful provenance."""
from copy import deepcopy

import pytest

from services.labeling.review import REVIEW_FORMAT, apply_review


def _inputs():
    entry = {"frame_indices": list(range(0, 100, 10)), "t_start": 5.0, "t_end": 9.5,
             "bboxes": [[.1, .1, .4, .8]] * 10, "keypoints": [None] * 10}
    index = {"batch": "batch-x", "clips": {cid: deepcopy(entry) for cid in ("human", "walk", "bad")}}
    existing = [{"clip_id": "human", "label": "WATCHING", "status": "AGREED",
                 "votes": {"a": "WATCHING", "b": "WATCHING"}}]
    review = {"format": REVIEW_FORMAT, "pack_id": "batch-x", "reviewer_type": "AI", "reviewer": "AI reviewer",
              "clips": [{"clip_id": "walk", "outcome": "ACCEPT", "label": "WALKING", "reason": "clear walk",
                         "sample_start": 2, "sample_stop": 9},
                        {"clip_id": "bad", "outcome": "EXCLUDE", "label": "INVALID", "reason": "ID switch"}]}
    return index, existing, review


def test_review_trims_all_arrays_without_changing_consensus_or_counting_ai_votes():
    index, existing, review = _inputs()
    before = deepcopy((index, existing, review))
    result, labels, excluded = apply_review(index, existing, review)
    assert (index, existing, review) == before
    assert set(result["clips"]) == {"human", "walk"}
    walk = result["clips"]["walk"]
    assert walk["frame_indices"] == [20, 30, 40, 50, 60, 70, 80]
    assert len(walk["bboxes"]) == len(walk["keypoints"]) == 7
    assert (walk["t_start"], walk["t_end"]) == (6.0, 9.0)
    assert labels[0] == existing[0]
    assert labels[1]["status"] == "AI_ADJUDICATED" and "votes" not in labels[1]
    assert labels[1]["human_reviewed"] is False and excluded[0]["clip_id"] == "bad"


@pytest.mark.parametrize("change", ["batch", "missing", "duplicate", "unknown", "overwrite", "label", "span", "short", "unaligned", "row_type"])
def test_review_rejects_invalid_or_incomplete_decisions(change):
    index, existing, review = _inputs()
    if change == "batch": review["pack_id"] = "other"
    if change == "missing": review["clips"].pop()
    if change == "duplicate": review["clips"].append(deepcopy(review["clips"][0]))
    if change == "unknown": review["clips"][0]["clip_id"] = "unknown"
    if change == "overwrite": review["clips"][0]["clip_id"] = "human"
    if change == "label": review["clips"][0]["label"] = "INVALID"
    if change == "span": review["clips"][0]["sample_stop"] = 99
    if change == "short": review["clips"][0].update(sample_start=2, sample_stop=5)
    if change == "unaligned": index["clips"]["walk"]["bboxes"].pop()
    if change == "row_type": review["clips"][0] = "not a row"
    with pytest.raises(ValueError):
        apply_review(index, existing, review)
