"""Fine-tune YOLOv8n for 1-class billiard cue detection (4GB VRAM optimized) and export ONNX models.

Usage:
    # 1. Export pretrained YOLOv8n-pose to models/yolov8n-pose.onnx (no training needed):
    python scripts/train_cue.py --export-pose

    # 2. Train YOLOv8n cue detector from labeled dataset & export models/yolov8n-cue.onnx:
    python scripts/train_cue.py --data data/datasets/cue_v1/dataset.yaml --epochs 60 --batch 8
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_model_meta(onnx_path: Path, *, base_weights: str, imgsz: int, task: str, extra: dict | None = None) -> None:
    meta = {
        "model_file": onnx_path.name,
        "task": task,
        "base_weights": base_weights,
        "imgsz": imgsz,
        "sha256": _sha256(onnx_path),
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        meta.update(extra)
    meta_path = onnx_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def _require_ultralytics():
    try:
        import torch
        from ultralytics import YOLO
    except ImportError as err:
        print(
            "Missing training dependencies ('ultralytics' / 'torch').\n"
            "Install them in a training venv before running train_cue.py:\n"
            "  pip install ultralytics",
            file=sys.stderr,
        )
        raise SystemExit(1) from err
    return YOLO, torch


def export_pose_onnx(pose_weights: str, out_path: Path, imgsz: int = 640) -> Path:
    YOLO, _ = _require_ultralytics()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    model = YOLO(pose_weights)
    exported = Path(model.export(format="onnx", imgsz=imgsz, half=False, opset=12, simplify=False))
    shutil.copy2(exported, out_path)
    _write_model_meta(out_path, base_weights=pose_weights, imgsz=imgsz, task="pose")
    print(f"Exported pose ONNX -> {out_path}")
    return out_path


def train_and_export_cue(
    data_yaml: Path,
    out_path: Path,
    *,
    base_weights: str = "yolov8n.pt",
    epochs: int = 60,
    batch: int = 8,
    imgsz: int = 640,
    workers: int = 2,
    patience: int = 15,
    project_dir: str = "data/datasets/cue_runs",
    name: str = "yolov8n_cue",
    device: str | None = None,
) -> Path:
    if not data_yaml.exists():
        raise FileNotFoundError(f"Dataset YAML not found: {data_yaml}")

    YOLO, torch = _require_ultralytics()
    resolved_device = device or ("0" if torch.cuda.is_available() else "cpu")

    model = YOLO(base_weights)
    results = model.train(
        data=str(data_yaml.resolve()),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        amp=True,
        workers=workers,
        patience=patience,
        device=resolved_device,
        project=str(Path(project_dir).resolve()),
        name=name,
        degrees=15.0,
        scale=0.4,
        hsv_v=0.4,
        close_mosaic=10,
        exist_ok=True,
    )

    save_dir = Path(getattr(results, "save_dir", Path(project_dir) / name))
    best_pt = save_dir / "weights" / "best.pt"
    if not best_pt.exists():
        best_pt = save_dir / "weights" / "last.pt"
    if not best_pt.exists():
        raise FileNotFoundError(f"Trained weights not found under {save_dir / 'weights'}")

    best_model = YOLO(str(best_pt))
    metrics = best_model.val(data=str(data_yaml.resolve()), imgsz=imgsz, device=resolved_device)

    exported = Path(best_model.export(format="onnx", imgsz=imgsz, half=False, opset=12, simplify=False))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exported, out_path)

    box_metrics = getattr(metrics, "box", None)
    eval_summary = {}
    if box_metrics is not None:
        eval_summary = {
            "map50": float(getattr(box_metrics, "map50", 0.0)),
            "map50_95": float(getattr(box_metrics, "map", 0.0)),
            "precision": float(getattr(box_metrics, "mp", 0.0)),
            "recall": float(getattr(box_metrics, "mr", 0.0)),
        }

    _write_model_meta(
        out_path,
        base_weights=base_weights,
        imgsz=imgsz,
        task="cue-detect",
        extra={"dataset_yaml": str(data_yaml), "epochs": epochs, "batch": batch, "val_metrics": eval_summary},
    )
    print(f"Exported cue ONNX -> {out_path}")
    if eval_summary:
        print(f"Validation metrics: {eval_summary}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Train YOLOv8n cue detector (4GB VRAM) & export ONNX")
    parser.add_argument("--data", type=Path, default=Path("data/datasets/cue_v1/dataset.yaml"))
    parser.add_argument("--weights", default="yolov8n.pt", help="Pretrained base weights (default: yolov8n.pt)")
    parser.add_argument("--pose-weights", default="yolov8n-pose.pt", help="Pretrained pose weights")
    parser.add_argument("--export-pose", action="store_true", help="Export yolov8n-pose.onnx to models/")
    parser.add_argument("--skip-train", action="store_true", help="Only run --export-pose without training cue")
    parser.add_argument("--output-cue", type=Path, default=Path("models/yolov8n-cue.onnx"))
    parser.add_argument("--output-pose", type=Path, default=Path("models/yolov8n-pose.onnx"))
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument("--device", default=None, help="CUDA device e.g. '0' or 'cpu'")
    parser.add_argument("--project", default="data/datasets/cue_runs", help="Thư mục lưu lần huấn luyện (dữ liệu riêng)")
    parser.add_argument("--name", default="yolov8n_cue", help="Tên lần huấn luyện")
    args = parser.parse_args()

    if args.export_pose:
        export_pose_onnx(args.pose_weights, args.output_pose, imgsz=args.imgsz)

    if not args.skip_train:
        train_and_export_cue(
            args.data,
            args.output_cue,
            base_weights=args.weights,
            epochs=args.epochs,
            batch=args.batch,
            imgsz=args.imgsz,
            workers=args.workers,
            patience=args.patience,
            device=args.device,
            project_dir=args.project,
            name=args.name,
        )


if __name__ == "__main__":
    main()
