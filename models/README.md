# Models directory

Thư mục lưu trữ các file weights ONNX được sử dụng bởi `services/vision`:

- `yolov8n.onnx`: Mô hình YOLOv8 Nano pre-trained trên tập dữ liệu COCO, tối ưu hóa để chạy trực tiếp trên CPU qua `cv2.dnn`.
  - Input: 640x640x3
  - Output: 8400x84 bboxes
  - Class mục tiêu: `0` (person)
  - Kích thước: ~12 MB

- `yolov8n-pose.onnx`: YOLOv8n-pose (COCO, 17 keypoint) cho nhận diện người + tư thế; pipeline ưu tiên file này, thiếu thì dùng `yolov8n.onnx`.
- `yolov8n-cue.onnx`: model gậy riêng, không kèm Git; tự train bằng `scripts/train_cue.py`. Thiếu file thì chạy chế độ Pose-first. Đã nạp chỉ cho phép vẽ gậy thử nghiệm; `validated=false` giữ gậy khỏi bằng chứng quyết định bàn. Không dùng COCO person weights thay cho gậy; adapter chỉ nhận output `(1, 5, N)` của YOLOv8 một lớp.

Xuất ONNX (làm trong venv riêng, không cài ultralytics/torch vào `.venv` của dự án vì sẽ ghi đè opencv): `YOLO("yolov8n.pt").export(format="onnx", imgsz=640, opset=12, simplify=False)`, tương tự cho `yolov8n-pose.pt`. Nạp xong nên xem `GET /api/camera/status` (`models.person.loaded`).

Các file weights `.onnx` và `.pt` được gitignore theo đúng quy định tại `AGENTS.md`.

Huấn luyện trong venv riêng có Ultralytics/PyTorch, không cài vào `.venv` runtime:

```powershell
TRAIN_PYTHON scripts/train_cue.py --data PATH/dataset.yaml --epochs 60 --batch 8 `
  --project data/datasets/cue_runs --name cue-v1 --output-cue models/yolov8n-cue.onnx
```

Thay `TRAIN_PYTHON` bằng Python của venv huấn luyện. Dataset phải có box `cue` trên ảnh thật và chia theo video/phiên; nhãn hành động không dùng để train detector gậy. Script xuất ONNX FP32, input 640 mặc định, opset 12 cho OpenCV DNN, kèm hash và chỉ số validation ở `.meta.json` (dữ liệu riêng, không kèm Git). Thông số `imgsz` của model phải trùng input detector (runtime mặc định 640).

[Tài liệu xuất ONNX của Ultralytics](https://docs.ultralytics.com/modes/export/) mô tả `opset` và `simplify`; kết quả phải được nạp thử bằng OpenCV runtime sau export. Lần thử ngày 20/11/2026 và giới hạn ghi tại [báo cáo gậy/gán nhãn](../docs/ai/CUE_AND_LABELING_20261120.md).
