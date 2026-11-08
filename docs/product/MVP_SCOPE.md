# Phạm vi và điểm dừng

## Đã thuộc Phase 0–2

Assessment; tài liệu; FastAPI + SQLAlchemy + SQLite; bốn bàn; FSM thời gian; POST sự kiện mô phỏng idempotent; mở/xác nhận thủ công; auto-open mô phỏng có cờ; tính phí và checkout; WebSocket; dashboard, chi tiết bàn, lịch sử và trang khả năng hệ thống; test.

## Thuộc MVP camera nhưng chưa thuộc Phase 2

Camera USB/RTSP/video reader, reconnect, YOLO person, tracker, mapper nhiều ROI, vẽ/lưu polygon, overlay/preview, adapter tay, benchmark video và demo vật lý. Chỉ interfaces VideoSource/CueDetector và ROI mẫu được chuẩn bị.

## Điều kiện tính năng gậy

COCO không có billiard cue chuyên biệt. PERSON_AND_CUE không tự mở khi detector chưa được kiểm chứng; ở Phase 2 luôn báo CUE_NOT_READY sau đủ hiện diện. Mọi sự kiện mô phỏng giữ nguồn SIMULATED.

## Ngoài MVP

Cloud, POS nâng cao, Loyalty, Redis/Kafka/Kubernetes, thanh toán thật và nhận dạng khuôn mặt. Không thêm các thành phần này chỉ để giống hồ sơ sản phẩm dài hạn.

Kết thúc Phase 2 phải báo cáo và dừng trước khi triển khai camera. Phạm vi acceptance AI không thể xem là đạt chỉ vì unit tests xanh.
