"""Dataset Preparation Helper for YOLOv8-seg Billiard Table Segmentation.

Extracts representative frames from video recordings and optionally generates
pre-annotated pseudo-labels using Classical CV to build a ready-to-train dataset.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import zipfile

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2

from services.vision.auto_calibration import auto_detect_table_zones


def extract_frames_for_segmentation(
    video_dir: Path | str = "data/recordings",
    output_dir: Path | str = "data/datasets/table_seg",
    max_frames_per_video: int = 50,
    target_total: int = 100,
    auto_label: bool = True,
    create_zip: bool = True,
) -> int:
    """Extract key frames from recordings to build training dataset for table segmentation."""
    video_path = Path(video_dir)
    out_path = Path(output_dir)
    images_train = out_path / "images" / "train"
    images_val = out_path / "images" / "val"
    labels_train = out_path / "labels" / "train"
    labels_val = out_path / "labels" / "val"

    for d in [images_train, images_val, labels_train, labels_val]:
        d.mkdir(parents=True, exist_ok=True)

    video_files = sorted(list(video_path.glob("*.mp4")) + list(video_path.glob("*.avi")))
    if not video_files:
        print(f"Khong tim thay video trong {video_dir}. Hay dat video quay quan bi-a vao thu muc nay.")
        return 0

    saved_count = 0
    total_labels_count = 0
    val_interval = 5  # 1 in 5 frames go to validation set (20%)

    # Calculate frames per video dynamically
    frames_per_video = max(10, min(max_frames_per_video, (target_total // len(video_files)) + 15))

    for v_file in video_files:
        if saved_count >= target_total:
            break

        cap = cv2.VideoCapture(str(v_file))
        if not cap.isOpened():
            continue

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            cap.release()
            continue

        step = max(1, total_frames // frames_per_video)
        frame_idx = 0
        video_saved = 0

        while cap.isOpened() and saved_count < target_total and video_saved < frames_per_video:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % step == 0:
                is_val = (saved_count % val_interval) == 0
                target_img_folder = images_val if is_val else images_train
                target_lbl_folder = labels_val if is_val else labels_train

                base_name = f"{v_file.stem}_frame_{frame_idx:05d}"
                img_name = f"{base_name}.jpg"
                save_img_path = target_img_folder / img_name
                save_lbl_path = target_lbl_folder / f"{base_name}.txt"

                # Resize to standard 1280x720 if very high res to optimize size
                h, w = frame.shape[:2]
                if w > 1280:
                    scale = 1280.0 / w
                    frame = cv2.resize(frame, (1280, int(h * scale)))

                cv2.imwrite(str(save_img_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
                saved_count += 1
                video_saved += 1

                # Generate pseudo-label in YOLO segmentation polygon format: 0 x1 y1 x2 y2 ...
                if auto_label:
                    detected_tables = auto_detect_table_zones(frame)
                    label_lines: list[str] = []
                    for t in detected_tables:
                        if len(t.play_polygon) >= 3:
                            coords_str = " ".join(f"{p[0]:.5f} {p[1]:.5f}" for p in t.play_polygon)
                            label_lines.append(f"0 {coords_str}")
                            total_labels_count += 1

                    if label_lines:
                        save_lbl_path.write_text("\n".join(label_lines) + "\n", encoding="utf-8")
                    else:
                        save_lbl_path.write_text("", encoding="utf-8")

            frame_idx += 1

        cap.release()

    # Generate data.yaml config file
    data_yaml_content = f"""# YOLOv8-seg Table Felt Segmentation Dataset
path: {out_path.resolve().as_posix()}
train: images/train
val: images/val

# Single class for billiard table play felt
names:
  0: table_felt
"""
    (out_path / "data.yaml").write_text(data_yaml_content, encoding="utf-8")
    print(f"-> Da trich xuat thanh cong {saved_count} anh vao {out_path}")
    print(f"-> Da tao san {total_labels_count} da giac nhan tu dong (pseudo-labels) trong labels/")
    print(f"-> File cau hinh dataset da luu tai: {out_path / 'data.yaml'}")

    if create_zip:
        zip_path = out_path.parent / f"{out_path.name}.zip"
        print(f"-> Dang tao file nen dataset: {zip_path}...")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file in out_path.rglob("*"):
                if file.is_file():
                    zipf.write(file, file.relative_to(out_path))
        print(f"-> Tao file zip thanh cong ({zip_path.stat().st_size / (1024 * 1024):.1f} MB)! San sang upload Colab/Roboflow.")

    return saved_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract frames for YOLOv8-seg table dataset")
    parser.add_argument("--videos", default="data/recordings", help="Folder containing recordings")
    parser.add_argument("--output", default="data/datasets/table_seg", help="Output dataset directory")
    parser.add_argument("--target", type=int, default=100, help="Target total frames")
    parser.add_argument("--no-auto-label", action="store_true", help="Disable automatic pseudo-label generation")
    parser.add_argument("--no-zip", action="store_true", help="Disable creating table_seg.zip")
    args = parser.parse_args()

    extract_frames_for_segmentation(
        args.videos,
        args.output,
        target_total=args.target,
        auto_label=not args.no_auto_label,
        create_zip=not args.no_zip,
    )
