"""Tests for windowing, assignment, merging and sprite rendering of the labeling tool."""
import json
from collections import Counter

import numpy as np
import pytest

from services.labeling.merge import FORMAT, ResultError, cohen_kappa, load_results, merge_results, parse_result
from services.labeling.sprite import build_sprite, head_box, render_tile
from services.labeling.windows import Sample, Window, assign_clips, bend_score, build_windows, overlaps_any, walking_score


def _samples(n, fps=8.0, start=0.0, height=0.4, skip=()):
    return [Sample(t=start + i / fps, frame_index=i, bbox=(0.4, 0.2, 0.5, 0.2 + height))
            for i in range(n) if i not in skip]


def test_windows_cut_run_into_consecutive_clips():
    wins = build_windows({1: _samples(60)}, window_s=3.0, stride_s=3.0, sample_fps=8.0)
    assert len(wins) == 2 and all(len(w.samples) == 24 for w in wins)
    assert wins[0].t_end < wins[1].t_start


def test_windows_split_on_track_gap_and_reject_sparse_or_small_people():
    gap = _samples(24) + _samples(24, start=10.0)           # 7 s hole: not one run
    assert len(build_windows({1: gap}, sample_fps=8.0)) == 2
    sparse = _samples(24, skip=set(range(0, 24, 2)))         # half the samples missing
    assert build_windows({1: sparse}, sample_fps=8.0, max_gap_s=0.6) == []
    tiny = _samples(24, height=0.05)
    assert build_windows({1: tiny}, sample_fps=8.0) == []
    with pytest.raises(ValueError):
        build_windows({}, window_s=0)


def test_assignment_gives_each_clip_distinct_members_and_balances_load():
    members = ["m1", "m2", "m3", "m4"]
    ids = [f"c{i}" for i in range(120)]
    plan = assign_clips(ids, members, redundancy=2, seed=3)
    assert all(len(set(v)) == 2 for v in plan.values())
    load = Counter(m for v in plan.values() for m in v)
    assert max(load.values()) - min(load.values()) <= 2 and sum(load.values()) == 240
    assert plan == assign_clips(ids, members, redundancy=2, seed=3)   # deterministic
    with pytest.raises(ValueError):
        assign_clips(ids, members, redundancy=5)
    with pytest.raises(ValueError):
        assign_clips(ids, ["a", "a"], redundancy=1)


def _result(member, labels, name=""):
    return {"format": FORMAT, "pack_id": "b1", "member_id": member, "annotator_name": name,
            "labels": {c: {"label": lab, "ts": f"2026-11-19T10:00:{i:02d}"} for i, (c, lab) in enumerate(labels.items())}}


def test_merge_statuses_and_extra_labels_never_become_final():
    results = [parse_result(_result("m1", {"a": "SHOOTING", "b": "WATCHING", "c": "AIMING", "d": "UNSURE", "e": "WALKING"})),
              parse_result(_result("m2", {"a": "SHOOTING", "b": "WALKING", "c": "AIMING", "d": "UNSURE", "e": "INVALID"})),
              parse_result(_result("m3", {"b": "WATCHING", "c": "WATCHING"}))]
    d = merge_results(results)["decisions"]
    assert d["a"]["status"] == "AGREED" and d["a"]["label"] == "SHOOTING"
    assert d["b"]["status"] == "MAJORITY" and d["b"]["label"] == "WATCHING"
    assert d["c"]["status"] == "MAJORITY" and d["c"]["label"] == "AIMING"
    assert d["d"]["status"] == "INSUFFICIENT" and d["d"]["label"] is None
    assert d["e"]["status"] == "INSUFFICIENT"
    tie = merge_results([parse_result(_result("m1", {"x": "SHOOTING"})), parse_result(_result("m2", {"x": "AIMING"}))])
    assert tie["decisions"]["x"]["status"] == "REVIEW" and tie["report"]["review_clip_ids"] == ["x"]


def test_cohen_kappa_known_values():
    assert cohen_kappa([]) is None
    assert cohen_kappa([("A", "A")] * 4) is None                      # no variation
    assert cohen_kappa([("A", "A"), ("B", "B")] * 3) == pytest.approx(1.0)
    assert cohen_kappa([("A", "B"), ("B", "A")] * 3) == pytest.approx(-1.0)
    mixed = [("A", "A")] * 20 + [("B", "B")] * 15 + [("A", "B")] * 5 + [("B", "A")] * 10
    assert cohen_kappa(mixed) == pytest.approx(0.4, abs=0.01)


def test_parse_rejects_bad_files_and_load_keeps_latest_per_member(tmp_path):
    with pytest.raises(ResultError):
        parse_result({"format": "other"})
    with pytest.raises(ResultError):
        parse_result({**_result("m1", {"a": "DANCING"})})
    first = _result("m1", {"a": "AIMING"}); second = _result("m1", {"a": "SHOOTING"})
    second["labels"]["a"]["ts"] = "2026-11-19T11:00:00"
    paths = []
    for i, data in enumerate((first, second)):
        p = tmp_path / f"r{i}.json"; p.write_text(json.dumps(data), encoding="utf-8"); paths.append(p)
    loaded = load_results(paths)
    assert len(loaded) == 1 and loaded[0]["labels"]["a"]["label"] == "SHOOTING"


def test_results_from_different_batches_cannot_silently_share_clip_ids(tmp_path):
    paths = []
    for i, batch in enumerate(("batch-a", "batch-b")):
        p = tmp_path / f"{i}.json"
        p.write_text(json.dumps({**_result("m1", {"c00000": "WALKING"}), "pack_id": batch}), encoding="utf-8")
        paths.append(p)
    with pytest.raises(ResultError, match="batch"):
        load_results(paths)


def test_result_globs_work_on_windows_and_missing_files_fail_explicitly(tmp_path):
    for member in ("m1", "m2"):
        (tmp_path / f"result-{member}.json").write_text(
            json.dumps(_result(member, {"c1": "WALKING"})), encoding="utf-8")
    assert len(load_results([tmp_path / "result-*.json"])) == 2
    literal = tmp_path / "result-[review].json"
    literal.write_text(json.dumps(_result("m3", {"c1": "WALKING"})), encoding="utf-8")
    assert load_results([literal])[0]["member_id"] == "m3"
    with pytest.raises(ResultError, match="file"):
        load_results([tmp_path / "missing-*.json"])


def test_review_pack_includes_insufficient_and_unseen_clips_but_not_agreed(tmp_path):
    from scripts.build_review_pack import build_review_pack

    batch = tmp_path / "batch"
    (batch / "_sprites").mkdir(parents=True)
    clips = {cid: {"video": "private-source.mp4", "frame_indices": [0, 1], "t_start": 0, "t_end": 1}
             for cid in ("agreed", "invalid", "unseen")}
    (batch / "clips_index.json").write_text(json.dumps({"batch": "b1", "clips": clips}), encoding="utf-8")
    sprite, _, _ = build_sprite([np.zeros((32, 32, 3), dtype=np.uint8)] * 2)
    for cid in clips:
        (batch / "_sprites" / f"{cid}.jpg").write_bytes(sprite)
    paths = []
    for member in ("m1", "m2"):
        p = tmp_path / f"{member}.json"
        p.write_text(json.dumps(_result(member, {"agreed": "WALKING", "invalid": "INVALID"})), encoding="utf-8")
        paths.append(p)
    out = tmp_path / "review"
    assert build_review_pack(batch, paths, out) == ["invalid", "unseen"]
    assert len(list(out.glob("*.zip"))) == 2
    html = (out / "pack_member-review-1/index.html").read_text(encoding="utf-8")
    assert '"id": "invalid"' in html and '"id": "unseen"' in html
    assert "private-source.mp4" not in html and not (out / "clips_index.json").exists()
    with pytest.raises(FileExistsError):
        build_review_pack(batch, paths, out)
    (batch / "_sprites/unseen.jpg").write_bytes(b"broken JPEG")
    with pytest.raises(ValueError, match="unseen"):
        build_review_pack(batch, paths, tmp_path / "missing-sprite-review")
    assert not (tmp_path / "missing-sprite-review").exists()


def test_head_box_uses_face_keypoints_else_top_of_box():
    kps = [(0.50, 0.25, 0.9), (0.49, 0.24, 0.9), (0.51, 0.24, 0.9), (0.47, 0.25, 0.9), (0.53, 0.25, 0.9)] + [(0, 0, 0)] * 12
    x1, y1, x2, y2 = head_box((0.4, 0.2, 0.6, 0.8), kps)
    assert x1 < 0.47 and x2 > 0.53 and y1 < 0.24 and y2 > 0.25
    fallback = head_box((0.4, 0.2, 0.6, 0.8), None)
    assert fallback[1] == pytest.approx(0.2) and fallback[3] == pytest.approx(0.2 + 0.6 * 0.22)


def test_render_tile_blurs_heads_outlines_target_and_handles_frame_edge():
    rng = np.random.default_rng(0)
    frame = rng.integers(0, 255, (360, 640, 3), dtype=np.uint8)       # noisy: blur must reduce detail
    target = (0.40, 0.20, 0.55, 0.80)
    head = (0.43, 0.20, 0.52, 0.32)
    plain = render_tile(frame, target, [], tile=128)
    blurred = render_tile(frame, target, [head], tile=128)
    assert plain.shape == (128, 128, 3)
    assert blurred[23:36, 54:73].std() < plain[23:36, 54:73].std() * 0.5
    assert not np.array_equal(frame, np.zeros_like(frame))             # input untouched
    edge = render_tile(frame, (0.0, 0.0, 0.1, 0.3), [], tile=64)       # crop runs off the frame
    assert edge.shape == (64, 64, 3)


def test_build_sprite_grid_dimensions():
    tiles = [np.full((32, 32, 3), i * 10, dtype=np.uint8) for i in range(10)]
    data, cols, rows = build_sprite(tiles, cols=6)
    assert (cols, rows) == (6, 2) and data[:2] == b"\xff\xd8"
    with pytest.raises(ValueError):
        build_sprite([])


def _kp(torso_len: float):
    kp = [(0.5, 0.5, 0.9)] * 17
    kp = list(kp)
    kp[5] = kp[6] = (0.5, 0.2, 0.9)
    kp[11] = kp[12] = (0.5, 0.2 + torso_len, 0.9)
    return tuple(kp)


def _window(torso_len: float, shift: float = 0.0, n: int = 10) -> Window:
    samples = tuple(Sample(t=i / 8, frame_index=i, bbox=(0.4 + shift * i, 0.1, 0.6 + shift * i, 0.9),
                           keypoints=_kp(torso_len)) for i in range(n))
    return Window(1, samples)


def test_bend_score_ranks_bent_over_standing_and_skips_walking_or_missing_keypoints():
    bent, standing = bend_score(_window(0.15)), bend_score(_window(0.35))
    assert bent is not None and standing is not None and bent > standing
    assert bend_score(_window(0.15, shift=0.05)) is None  # travelling = walking
    no_kp = Window(1, tuple(Sample(t=i / 8, frame_index=i, bbox=(0.4, 0.1, 0.6, 0.9)) for i in range(10)))
    assert bend_score(no_kp) is None


def test_walking_score_rejects_static_jitter_and_id_switches():
    assert walking_score(_window(0.15)) is None
    assert walking_score(_window(0.15, shift=0.001)) is None
    moving = _window(0.15, shift=0.05)
    assert walking_score(moving) is not None
    assert walking_score(_window(0.15, shift=0.1)) > walking_score(moving)
    assert walking_score(_window(0.15, n=3)) is None
    assert walking_score(_window(0.15, shift=0.9)) is None


def test_overlaps_any_matches_same_video_and_overlapping_span_only():
    used = [("a.mp4", 10.0, 13.0)]
    assert overlaps_any("a.mp4", 12.0, 15.0, used)
    assert not overlaps_any("a.mp4", 13.0, 16.0, used)
    assert not overlaps_any("b.mp4", 10.0, 13.0, used)


def test_skeleton_dataset_split_by_camera_and_shape():
    import numpy as np
    from services.labeling.dataset import build_dataset, clip_to_array

    def entry(cam, video, n=5, none_at=None):
        kp = [[0.5 + 0.01 * j, 0.1 * j, 0.9] for j in range(17)]
        kps = [None if i == none_at else kp for i in range(n)]
        return {"camera_id": cam, "video": video, "keypoints": kps, "bboxes": [[0.4, 0.1, 0.6, 0.9]] * n}

    index = {"c1": entry("a", "a1.mp4"), "c2": entry("b", "b1.mp4", none_at=0), "c3": entry("b", "b2.mp4"),
             "c4": {"camera_id": "b", "video": "b2.mp4", "keypoints": [None] * 3, "bboxes": [[0, 0, 1, 1]] * 3}}
    labels = {"c1": "AIMING", "c2": "SHOOTING", "c3": "WATCHING", "c4": "WALKING", "c9": "AIMING"}
    data = build_dataset(index, labels, test_camera="a", val_video="b2.mp4", length=8)
    assert data["x"].shape == (3, 8, 17, 3)  # c4 has no keypoints, c9 not in index
    assert dict(zip(data["clip_id"], data["split"])) == {"c1": "test", "c2": "train", "c3": "val"}
    assert np.isfinite(data["x"]).all()
    assert clip_to_array(index["c4"]) is None


def test_balance_train_oversamples_only_minority_and_keeps_originals():
    import numpy as np
    from services.labeling.dataset import balance_train, class_weights

    rng = np.random.default_rng(1)
    x = rng.normal(size=(7, 6, 17, 3)).astype(np.float32)
    x[:, :, :, 2] = 0.9
    y = np.array([0, 0, 0, 0, 1, 1, 2])
    xb, yb, aug = balance_train(x, y, seed=3)
    assert np.bincount(yb).tolist() == [4, 4, 4]
    assert (~aug).sum() == 7 and np.array_equal(xb[:7], x) and np.isfinite(xb).all()
    w = class_weights(y, 4)
    assert w[2] > w[1] > w[0] and w[3] == 0
