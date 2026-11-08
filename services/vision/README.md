# Vision service — trạng thái Phase 2

Đã có `decision.py`: temporal FSM thuần Python, config và tests; `contracts.py`: Detection, VideoSource, CueDetector protocols. API gọi FSM với observation nhân tạo; inference/capture không chạy trong backend.

Chưa có OpenCV, Ultralytics, tracker, zone mapper, video reader, hand detector hoặc cue weights. Không có lệnh chạy camera ở milestone này. Việc chưa thêm dependency AI giúp Phase 2 nhẹ và không phải tải weights khi demo.

Tiếp theo SB-09: USB/RTSP/file adapters, health/reconnect và normalized ROI calibration; sau đó person/tracker/mapper. Xem `docs/ai/` để biết pipeline và evaluation plan. Không tạo model giả để lấp capability.
