"""Build offline labeling packs (one per team member) from club videos.

Each pack is a folder with an index.html the member opens by double-click. Clips show ONE person
(outlined) for ~3 seconds with every face blurred. Videos can come from several cameras: pass one
--source CAM_ID=path_or_folder per camera, so the camera is recorded for the later train/test split.

Private output stays under data/label_packs/ (gitignored): clips_index.json maps opaque clip ids to
video, camera, time, track and keypoints. It is NOT included in the packs sent to members.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import zlib
from datetime import datetime
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.labeling.sprite import build_sprite, head_box, render_tile
from services.labeling.windows import (CORE_LABELS, EXTRA_LABELS, Sample, Window, assign_clips,
                                       bend_score, build_windows, overlaps_any, pick_even)

VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov"}
TEMPLATE = ROOT / "tools/label_pack/template.html"
LABEL_HELP = {
    "SHOOTING": "Đang đánh: đang thực hiện cú đánh, gậy đẩy về phía bi.",
    "AIMING": "Đang ngắm: cúi người, đặt gậy lên tay cầu để chuẩn bị đánh, chưa đẩy gậy.",
    "WATCHING": "Đứng/ngồi xem: không chuẩn bị đánh. Cầm gậy đứng chờ lượt cũng tính là xem.",
    "WALKING": "Đi lại: đang di chuyển, không đứng yên ở bàn.",
    "UNSURE": "Không chắc: không nhìn rõ hoặc khó quyết định. Dùng nhãn này thay vì đoán.",
    "INVALID": "Clip lỗi: khung hình không đúng một người, hoặc người được đánh dấu liên tục thay đổi.",
}


def parse_sources(items: list[str]) -> dict[str, list[Path]]:
    sources: dict[str, list[Path]] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--source phải có dạng CAM_ID=đường_dẫn, nhận được: {item!r}")
        cam, raw = item.split("=", 1)
        cam, path = cam.strip(), Path(raw.strip())
        if not cam:
            raise SystemExit("CAM_ID không được rỗng")
        if path.is_dir():
            videos = sorted(p for p in path.rglob("*") if p.suffix.lower() in VIDEO_EXTS)
        elif path.is_file():
            videos = [path]
        else:
            raise SystemExit(f"Không tìm thấy: {path}")
        if not videos:
            raise SystemExit(f"Không có video trong: {path}")
        sources.setdefault(cam, []).extend(videos)
    return sources


def track_video(video: Path, detector, tracker_cls, sample_fps: float, start_s: float, end_s: float | None):
    """Pass 1: detect + track on sampled frames. Returns (samples_by_track, heads_by_frame, effective_fps)."""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"Không mở được video: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, round(fps / sample_fps))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    first = int(start_s * fps)
    last = total if end_s is None else min(total, int(end_s * fps))
    if first:
        cap.set(cv2.CAP_PROP_POS_FRAMES, first)
    tracker = tracker_cls()
    by_track: dict[int, list[Sample]] = {}
    heads: dict[int, list[tuple[float, float, float, float]]] = {}
    idx = first
    while idx < last:
        ok = cap.grab()
        if not ok:
            break
        if (idx - first) % step == 0:
            ok, frame = cap.retrieve()
            if ok:
                persons = tracker.update(detector.detect(frame))
                heads[idx] = [head_box(p.bbox, p.keypoints) for p in persons]
                for p in persons:
                    if p.track_id is not None:
                        by_track.setdefault(p.track_id, []).append(
                            Sample(t=idx / fps, frame_index=idx, bbox=tuple(p.bbox),
                                   keypoints=tuple(tuple(k) for k in p.keypoints) if p.keypoints else None))
            if idx and idx % (step * 200) == 0:
                print(f"  {video.name}: {idx}/{last}", flush=True)
        idx += 1
    cap.release()
    return by_track, heads, fps / step


def read_frames(video: Path, indices: list[int]) -> dict[int, object]:
    cap = cv2.VideoCapture(str(video))
    frames = {}
    for index in sorted(set(indices)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = cap.read()
        if ok:
            frames[index] = frame
    cap.release()
    return frames


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", action="append", required=True, metavar="CAM_ID=PATH",
                    help="Camera và video/thư mục video của camera đó. Lặp lại cho nhiều camera.")
    ap.add_argument("--members", type=int, default=4, help="Số thành viên gán nhãn (mặc định 4)")
    ap.add_argument("--redundancy", type=int, default=2, help="Mỗi clip do bao nhiêu người gán (mặc định 2)")
    ap.add_argument("--max-clips", type=int, default=400, help="Tổng số clip, chia đều giữa các camera")
    ap.add_argument("--window", type=float, default=3.0, help="Độ dài clip, giây")
    ap.add_argument("--sample-fps", type=float, default=8.0)
    ap.add_argument("--start", type=float, default=0.0, help="Bỏ qua N giây đầu mỗi video")
    ap.add_argument("--end", type=float, default=None, help="Dừng ở giây thứ N của mỗi video")
    ap.add_argument("--focus", choices=["bent"], default=None,
                    help="Lấy mẫu có chủ đích: 'bent' ưu tiên đoạn người cúi người (ứng viên AIMING/SHOOTING). "
                         "Chỉ là gợi ý xếp hạng, nhãn vẫn do người gán.")
    ap.add_argument("--exclude-index", action="append", type=Path, default=[], metavar="clips_index.json",
                    help="Bỏ các đoạn đã nằm trong batch trước (trùng video + thời gian). Lặp lại được.")
    ap.add_argument("--tile", type=int, default=224)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--pose-model", type=Path, default=ROOT / "models/yolov8n-pose.onnx")
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / "data/label_packs")
    args = ap.parse_args()

    if args.members < 1 or not 1 <= args.redundancy <= args.members:
        raise SystemExit("--redundancy phải từ 1 đến số thành viên")
    if not args.pose_model.exists():
        raise SystemExit(f"Thiếu model pose: {args.pose_model} (xem models/README.md)")

    from services.vision.detector import YoloPoseDetector
    from services.vision.tracker import ByteTracker

    sources = parse_sources(args.source)
    detector = YoloPoseDetector(model_path=args.pose_model, fallback_model_path=None, prefer_gpu=not args.cpu)
    if not detector.is_ready:
        raise SystemExit("Không nạp được model pose; không tạo được gói gán nhãn.")

    candidates: dict[str, list[tuple[Path, Window, float]]] = {}
    heads_by_video: dict[Path, dict[int, list]] = {}
    for cam, videos in sources.items():
        for video in videos:
            print(f"[{cam}] phát hiện + theo dõi: {video.name}")
            by_track, heads, eff_fps = track_video(video, detector, ByteTracker, args.sample_fps, args.start, args.end)
            heads_by_video[video] = heads
            wins = build_windows(by_track, window_s=args.window, stride_s=args.window, sample_fps=eff_fps)
            candidates.setdefault(cam, []).extend((video, w, eff_fps) for w in wins)
            print(f"  -> {len(wins)} clip ứng viên")

    used: list[tuple[str, float, float]] = []
    for path in args.exclude_index:
        for c in json.loads(path.read_text(encoding="utf-8"))["clips"].values():
            used.append((c["video"], c["t_start"], c["t_end"]))
    per_cam = max(1, args.max_clips // len(candidates))
    chosen: list[tuple[str, Path, Window, float]] = []
    for cam, items in candidates.items():
        if used:
            items = [it for it in items if not overlaps_any(it[0].name, it[1].t_start, it[1].t_end, used)]
        if args.focus == "bent":
            scored = [(bend_score(it[1]), it) for it in items]
            scored = sorted((x for x in scored if x[0] is not None), key=lambda x: -x[0])
            picked = [it for _, it in scored[:per_cam]]
            print(f"[{cam}] focus=bent: {len(scored)}/{len(items)} clip có điểm, chọn {len(picked)}")
        else:
            picked = pick_even(items, per_cam, seed=args.seed)
        for video, win, eff in picked:
            chosen.append((cam, video, win, eff))
    if not chosen:
        raise SystemExit("Không tìm thấy clip nào đủ điều kiện (người quá nhỏ hoặc bị đứt đoạn).")

    members = [f"member-{i + 1}" for i in range(args.members)]
    clip_ids = [f"c{i:05d}" for i in range(len(chosen))]
    assignment = assign_clips(clip_ids, members, args.redundancy, seed=args.seed)

    batch = datetime.now().strftime("batch-%Y%m%d-%H%M%S")
    out = args.out / batch
    sprites = out / "_sprites"
    sprites.mkdir(parents=True)
    index: dict[str, dict] = {}
    manifests: dict[str, list[dict]] = {m: [] for m in members}

    # Pass 2: render sprites, one video at a time.
    by_video: dict[Path, list[int]] = {}
    for i, (_, video, win, _) in enumerate(chosen):
        by_video.setdefault(video, []).append(i)
    for video, ids in by_video.items():
        print(f"Tạo clip từ {video.name} ({len(ids)} clip)")
        frames = read_frames(video, [s.frame_index for i in ids for s in chosen[i][2].samples])
        for i in ids:
            cam, _, win, eff = chosen[i]
            tiles = [render_tile(frames[s.frame_index], s.bbox, heads_by_video[video].get(s.frame_index, []), args.tile)
                     for s in win.samples if s.frame_index in frames]
            if len(tiles) < 2:
                continue
            data, cols, rows = build_sprite(tiles)
            cid = clip_ids[i]
            (sprites / f"{cid}.jpg").write_bytes(data)
            index[cid] = {
                "camera_id": cam, "video": video.name, "track_id": win.track_id,
                "t_start": win.t_start, "t_end": win.t_end,
                "frame_indices": [s.frame_index for s in win.samples],
                "bboxes": [list(s.bbox) for s in win.samples],
                "keypoints": [[list(k) for k in s.keypoints] if s.keypoints else None for s in win.samples],
                "assigned_to": list(assignment[cid]),
            }
            entry = {"id": cid, "sprite": f"clips/{cid}.jpg", "cols": cols, "rows": rows,
                     "n": len(tiles), "fps": round(eff, 2), "tile": args.tile}
            for member in assignment[cid]:
                manifests[member].append(entry)
        del frames

    (out / "clips_index.json").write_text(json.dumps(
        {"batch": batch, "labels": list(CORE_LABELS), "window_s": args.window, "clips": index},
        ensure_ascii=False), encoding="utf-8")

    template = TEMPLATE.read_text(encoding="utf-8")
    for member in members:
        clips = manifests[member]
        # Different order per member so duplicated clips are not seen back to back.
        clips = pick_even(clips, len(clips), seed=zlib.crc32(f"{args.seed}:{member}".encode()))
        pack_dir = out / f"pack_{member}"
        (pack_dir / "clips").mkdir(parents=True)
        for entry in clips:
            shutil.copy2(sprites / f"{entry['id']}.jpg", pack_dir / entry["sprite"])
        manifest = {"batch": batch, "member_id": member, "clips": clips,
                    "labels": [{"id": k, "help": LABEL_HELP[k]} for k in CORE_LABELS + EXTRA_LABELS]}
        html = template.replace("/*__PACK_JSON__*/null", json.dumps(manifest, ensure_ascii=False))
        (pack_dir / "index.html").write_text(html, encoding="utf-8")
        shutil.make_archive(str(out / f"pack_{member}"), "zip", pack_dir)
        print(f"{member}: {len(clips)} clip -> {out / f'pack_{member}.zip'}")

    print(f"\nXong. Thư mục: {out}\nKhông gửi clips_index.json hay thư mục _sprites cho thành viên.")
    print("Nhắc: chỉ gửi gói cho người trong nhóm và cần có sự đồng ý của quán/khách về việc dùng hình ảnh.")


if __name__ == "__main__":
    main()
