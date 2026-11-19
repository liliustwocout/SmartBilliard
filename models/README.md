# Models directory

Thư mục lưu trữ các file weights ONNX được sử dụng bởi `services/vision`:

- `yolov8n.onnx`: Mô hình YOLOv8 Nano pre-trained trên tập dữ liệu COCO, tối ưu hóa để chạy trực tiếp trên CPU qua `cv2.dnn`.
  - Input: 640x640x3
  - Output: 8400x84 bboxes
  - Class mục tiêu: `0` (person)
  - Kích thước: ~12 MB

- `yolov8n-pose.onnx`: YOLOv8n-pose (COCO, 17 keypoint) cho nhận diện người + tư thế; pipeline ưu tiên file này, thiếu thì dùng `yolov8n.onnx`.
- `yolov8n-cue.onnx`: model gậy riêng, **không có sẵn**; phải tự train bằng `scripts/train_cue.py` và kiểm chứng. Thiếu file thì chạy chế độ Pose-first.

Xuất ONNX (làm trong venv riêng, không cài ultralytics/torch vào `.venv` của dự án vì sẽ ghi đè opencv): `YOLO("yolov8n.pt").export(format="onnx", imgsz=640, opset=12, simplify=False)`, tương tự cho `yolov8n-pose.pt`. Nạp xong nên xem `GET /api/camera/status` (`models.person.loaded`).

Các file weights `.onnx` và `.pt` được gitignore theo đúng quy định tại `AGENTS.md`.
