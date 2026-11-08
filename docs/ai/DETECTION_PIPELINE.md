# Detection pipeline

Mục tiêu: VideoSource → FrameReader → PersonDetector → optional CueDetector → Tracker → ZoneMapper → TemporalDecisionEngine → EventPublisher. **Phase 2 chỉ có temporal engine, protocol nguồn/video và mô phỏng.**

VideoSource hỗ trợ tương lai USB index, RTSP và video file. Adapter phải báo source type, camera_id, timestamp và health; frame hỏng/mất kết nối không tạo presence. RTSP reconnect cần backoff giới hạn; queue frame nhỏ và bỏ frame cũ thay vì tích lũy latency. Startup đọc env; không log URI có credentials.

Detection contract: kind person/hand/cue, bbox, confidence, camera_id, timestamp và track_id tùy chọn. Chuẩn hóa bbox theo frame trước mapper. ByteTrack/BoT-SORT giữ ID nội bộ, không phải danh tính con người. Không cần face recognition.

Mapper dùng foot anchor cho REAL_CLUB, anchor tay phù hợp cho MINI_TABLE; kết quả một bàn hoặc AMBIGUOUS/OUTSIDE. Đầu vào mơ hồ không được phát cho nhiều bàn như positive.

FSM có EMPTY/CANDIDATE/NEEDS_CONFIRMATION/ACTIVE/CLOSED. Config TOML được Pydantic validate; enter/exit hysteresis, presence duration, grace, maxgap và cooldown. Positive gián đoạn quá maxgap reset candidate; vắng ngắn được làm mượt; absence không bao giờ đóng session. Replay ID không chạy FSM lại. Sau checkout cooldown áp dụng mở tự động; nhân viên có thể mở lại bằng tay.

PERSON_ONLY chỉ là baseline presence, default confirmation. PERSON_AND_CUE yêu cầu validated detector; Phase 2 cố định cue_detector_ready=false. Custom camera adapter chưa có; không gửi “camera” bằng endpoint mô phỏng.
