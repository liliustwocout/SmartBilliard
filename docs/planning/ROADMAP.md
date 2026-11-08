# Roadmap bốn tuần

Tuần tính từ kickoff được nhóm thống nhất, không giả định ngày thi hoặc cam kết thời hạn đã được xác minh.

## Tuần 1 — Foundation (Đạt, An, Sơn, Đức)

Assessment, monorepo, PRD/ADR/API, schema, dashboard skeleton, khảo sát camera, reader cơ bản và cấu trúc ROI. Gate: cài/chạy local được, chưa claim AI. Phase 2 hiện đã đi trước một phần tích hợp để kiểm chứng nghiệp vụ.

## Tuần 2 — Computer Vision (Sơn + Đạt)

USB/RTSP/file adapter, reconnect, YOLO person, ByteTrack hoặc BoT-SORT, anchor/standing zones, ambiguity, FSM test video, CueDetector/custom weights contract. Nhánh MINI_TABLE tách hand detector, không dùng làm bằng chứng REAL_CLUB. Gate: có video gán nhãn và event source CAMERA/VIDEO thật, chưa cần cue tự động.

## Tuần 3 — Integration (An + Đạt)

Tích hợp camera adapter vào nghiệp vụ, authenticated event ingestion, ROI editor, overlay, WebSocket, billing/history và khôi phục mất kết nối. Gate: camera/video → decision → session → dashboard; duplicate và checkout đúng. Nghiệp vụ mô phỏng của tuần này đã có ở Phase 2.

## Tuần 4 — Validation (cả nhóm)

Kiểm thử 15 tình huống, bốn bàn gần/xa, benchmark FPS/CPU/RAM/latency, phân tích mở nhầm/bỏ sót, tập demo offline, quay bằng chứng. Chỉ thử tám bàn khi bốn bàn đạt gate. Gate: demo acceptance có evidence, số liệu thật kèm điều kiện đo.

Điểm dừng hiện tại: báo cáo Phase 2. Milestone kế tiếp là camera/video reader và ROI, không tự triển khai tiếp từ roadmap.
