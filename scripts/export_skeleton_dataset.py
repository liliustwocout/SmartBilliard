"""Export labeled clips to a skeleton dataset (.npz) for training. Split by camera/video.

Usage: python scripts/export_skeleton_dataset.py data/label_packs/batch-X --test-camera cam1 [--val-video cam2_03.mp4]
Reads clips_index.json and merged/labels_final.jsonl; writes skeleton_dataset.npz in the batch folder.
Output stays under data/ (gitignored).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.labeling.dataset import balance_train, build_dataset, class_weights


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("batch", type=Path)
    ap.add_argument("--test-camera", required=True, help="Camera dành riêng cho tập test")
    ap.add_argument("--val-video", default=None, help="Một video (của camera khác) làm tập val")
    ap.add_argument("--length", type=int, default=24, help="Số khung mỗi clip sau khi lấy mẫu lại")
    ap.add_argument("--balance", action="store_true",
                    help="Thêm x_train_bal/y_train_bal (tăng mẫu lớp ít bằng augmentation, chỉ tập train) và class_weights")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    index = json.loads((args.batch / "clips_index.json").read_text(encoding="utf-8"))["clips"]
    labels = {}
    with (args.batch / "merged/labels_final.jsonl").open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            labels[d["clip_id"]] = d["label"]
    if not any(e["camera_id"] == args.test_camera for e in index.values()):
        raise SystemExit(f"Không có camera {args.test_camera!r} trong batch")
    data = build_dataset(index, labels, args.test_camera, args.val_video, args.length)
    if args.balance:
        train = data["split"] == "train"
        xb, yb, aug = balance_train(data["x"][train], data["y"][train], args.seed)
        data.update(x_train_bal=xb, y_train_bal=yb, train_is_augmented=aug,
                    class_weights=class_weights(data["y"][train], len(data["label_names"])))
    out = args.out or args.batch / "skeleton_dataset.npz"
    np.savez_compressed(out, **data)
    names = list(data["label_names"])
    print(f"x {data['x'].shape} -> {out}")
    for split in ("train", "val", "test"):
        mask = data["split"] == split
        counts = Counter(str(names[i]) for i in data["y"][mask])
        print(f"  {split}: {int(mask.sum())} clip {dict(counts)}")
    if args.balance:
        print(f"  train cân bằng: {len(yb)} mẫu, {int(aug.sum())} là bản augment; "
              f"class_weights {dict(zip(map(str, names), data['class_weights'].round(2).tolist()))}")


if __name__ == "__main__":
    main()
