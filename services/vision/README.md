# Vision service — trạng thái Phase 3 & 4 (Milestones M3 / M4)

Đã có:
- `decision.py`: temporal FSM thuần Python, config và tests.
- `contracts.py`: Detection, VideoSource, CueDetector protocols, SourceStatus.
- `adapters.py` (**SB-09**):
  - `FileVideoSource`: đọc video file (.mp4, .mkv), loop và EOF handling.
  - `USBCameraSource`: đọc USB webcam theo device index, tự phục hồi kết nối.
  - `RTSPCameraSource`: đọc luồng IP RTSP/HTTP, che giấu mật khẩu (`sanitize_uri`), exponential backoff khi mất stream, drop stale frames chống lag.
  - `create_video_source`: factory khởi tạo nguồn tự động từ cấu hình env/tham số.
- `calibration.py` & `preview.py` (**SB-10**):
  - Geometry validation (Shoelace, self-intersection, point-in-polygon, standing zone overlap detection).
  - Snapshot camera preview hoặc ảnh tham chiếu phòng bi-a.
  - Lưu trữ cấu hình `configs/zones.json`.
- `detector.py` & `tracker.py` (**SB-11**):
  - `YoloPersonDetector`: chạy mô hình YOLOv8n ONNX trên CPU thông qua OpenCV DNN, trích xuất bounding box chuẩn hóa và Foot Anchor (tâm đáy).
  - `ByteTracker`: thuật toán ByteTrack 2 tầng (pure Python + NumPy), liên kết ID ổn định khi người chơi di chuyển, cúi người hoặc bị che khuất tạm thời.
- `mapper.py` & `pipeline.py` (**SB-12**):
  - `TableZoneMapper`: chiếu Foot Anchor vào đa giác vùng bàn, xác định trạng thái `ASSIGNED`, `OUTSIDE`, hoặc `AMBIGUOUS`.
  - Phân tích và sinh `TableObservationSummary` tương thích trực tiếp với hợp đồng `Observation` của Decision Engine.
  - `VisionPipeline`: kết nối VideoSource -> Detector -> Tracker -> Mapper -> per-table Observations.

Tiếp theo:
- **SB-13**: Camera Event Ingestion (background task đọc luồng camera/video và đẩy sự kiện nhận diện thật vào Decision Engine của FastAPI).
