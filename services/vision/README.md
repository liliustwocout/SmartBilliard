# Vision service — trạng thái Phase 3 (Milestone M3)

Đã có:
- `decision.py`: temporal FSM thuần Python, config và tests.
- `contracts.py`: Detection, VideoSource, CueDetector protocols, SourceStatus.
- `adapters.py` (**SB-09**):
  - `FileVideoSource`: đọc video file (.mp4, .mkv), loop và EOF handling.
  - `USBCameraSource`: đọc USB webcam theo device index, tự phục hồi kết nối.
  - `RTSPCameraSource`: đọc luồng IP RTSP/HTTP, che giấu mật khẩu (`sanitize_uri`), exponential backoff khi mất stream, drop stale frames chống lag.
  - `create_video_source`: factory khởi tạo nguồn tự động từ cấu hình env/tham số.

Tiếp theo:
- **SB-10**: ROI Editor và calibration trên web dashboard.
- **SB-11/12**: Person detector (YOLO) + tracker + zone mapper.
