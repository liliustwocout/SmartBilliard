"""Fine-tuning & Export Script for YOLOv8-seg Table Felt Model.

Can be run locally if GPU/Ultralytics is installed, or executed directly on
Google Colab (free T4 GPU) to export the final ONNX model to `models/yolov8n-table-seg.onnx`.

Usage:
    python scripts/train_table_seg.py --data data/datasets/table_seg/data.yaml --epochs 50
"""
from __future__ import annotations

import argparse
from pathlib import Path


def train_and_export_yolov8_seg(
    data_yaml: Path | str = "data/datasets/table_seg/data.yaml",
    epochs: int = 50,
    batch_size: int = 8,
    img_size: int = 640,
    output_onnx: Path | str = "models/yolov8n-table-seg.onnx",
) -> None:
    """Train YOLOv8n-seg model and export directly to ONNX format."""
    try:
        from ultralytics import YOLO
    except ImportError:
        print("Ultralytics chua duoc cai dat tren moi truong hien tai.")
        print("Hay cai dat: pip install ultralytics")
        print("Hoac chay tren Google Colab T4 GPU mien phi (xem huong dan tai docs/ai/YOLO_SEG_TABLE_TRAINING.md)")
        return

    data_path = Path(data_yaml)
    if not data_path.is_file():
        print(f"Khong tim thay file {data_path}. Hay chay scripts/prepare_table_dataset.py truoc.")
        return

    out_onnx_path = Path(output_onnx)
    out_onnx_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"=== BAT DAU HUAN LUYEN YOLOV8-SEG VOI DATASET: {data_path} ===")
    print(f"So epochs: {epochs} | Batch size: {batch_size} | Kich thuoc anh: {img_size}")

    # 1. Load pretrained lightweight model
    model = YOLO("yolov8n-seg.pt")

    # 2. Fine-tune on table dataset
    model.train(
        data=str(data_path),
        epochs=epochs,
        batch=batch_size,
        imgsz=img_size,
        workers=2,
        augment=True,
        hsv_h=0.03,  # Slight hue augmentation for various cloth colors
        hsv_s=0.2,   # Saturation variation for lighting
        hsv_v=0.3,   # Brightness variation for table lamps
        project="runs/table_seg",
        name="yolov8n_table",
    )

    # 3. Export to ONNX format compatible with OpenCV DNN
    print(f"=== XUAT MO HINH SANG DINH DANG ONNX CHO OPENCV DNN ===")
    exported_file = model.export(
        format="onnx",
        imgsz=img_size,
        simplify=True,
        opset=12,
    )

    if exported_file and Path(exported_file).is_file():
        # Copy to destination models/ directory
        import shutil
        shutil.copy(exported_file, str(out_onnx_path))
        print(f"XUAT THANH CONG! File model da duoc luu tai: {out_onnx_path}")
        print(f"Kich thuoc file: {out_onnx_path.stat().st_size / (1024 * 1024):.2f} MB")
        print("He thong SmartBilliard se tu dong kich hoat nhan dien bang YOLOv8-seg!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train and export YOLOv8-seg model for billiard table detection")
    parser.add_argument("--data", default="data/datasets/table_seg/data.yaml", help="Path to data.yaml")
    parser.add_argument("--epochs", type=int, default=50, help="Number of training epochs")
    parser.add_argument("--batch", type=int, default=8, help="Batch size")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size")
    parser.add_argument("--output", default="models/yolov8n-table-seg.onnx", help="Destination ONNX path")
    args = parser.parse_args()

    train_and_export_yolov8_seg(
        data_yaml=args.data,
        epochs=args.epochs,
        batch_size=args.batch,
        img_size=args.imgsz,
        output_onnx=args.output,
    )
