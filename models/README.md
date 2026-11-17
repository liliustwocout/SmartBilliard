# Models directory

Thư mục lưu trữ các file weights ONNX được sử dụng bởi `services/vision`:

- `yolov8n.onnx`: Mô hình YOLOv8 Nano pre-trained trên tập dữ liệu COCO, tối ưu hóa để chạy trực tiếp trên CPU qua `cv2.dnn`.
  - Input: 640x640x3
  - Output: 8400x84 bboxes
  - Class mục tiêu: `0` (person)
  - Kích thước: ~12 MB

Các file weights `.onnx` và `.pt` được gitignore theo đúng quy định tại `AGENTS.md`.
