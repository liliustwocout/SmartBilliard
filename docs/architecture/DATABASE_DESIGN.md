# Database SQLite

## tables

`id` PK, `name`, `hourly_rate` INTEGER VND >= 0, `memory` JSON. Trạng thái hiển thị suy ra từ session ACTIVE hoặc memory FSM, tránh một cột status bị lệch với session. Memory lưu state, candidate_since/last_seen/last_positive epoch UTC và cooldown_until.

## play_sessions

UUID `id` PK, `table_id` FK, `started_at`, `ended_at` nullable, `status` ACTIVE/PAID, `hourly_rate_snapshot` INTEGER, `total_amount` nullable INTEGER, `trigger_source`, `evidence_source` nullable.

Unique partial index trên table_id WHERE status='ACTIVE'. Giá snapshot không đổi khi giá bàn đổi. Thời gian DateTime lưu UTC (SQLite không giữ tzinfo; serializer gắn UTC khi đọc). Nguồn Phase 2: STAFF, STAFF_CONFIRMATION, SIMULATED. Chưa có session nguồn AI.

## detection_events

UUID `id` PK chính là idempotency key; `table_id` FK/index, `event_type` PRESENCE/ABSENCE/AMBIGUOUS, confidence FLOAT cho tín hiệu, timestamp UTC, source SIMULATED, payload JSON chuẩn hóa, result JSON. Float không được dùng cho tiền.

Event/session/FSM commit nguyên tử. Foreign keys ON, busy_timeout 5 giây. Checkout lặp theo session_id không ảnh hưởng một phiên mới cùng bàn. Không có DELETE API.

## Thay đổi schema

Create_all chỉ tạo schema mới, không migration database cũ. Dừng API và backup file trước khi đổi schema. Thêm Alembic khi thực sự cần migration; không xóa DB để né migration. Lịch sử có phân trang; retention detection event còn backlog và phải bảo toàn idempotency window.
