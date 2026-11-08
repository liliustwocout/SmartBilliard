# ADR 0001 — một backend local với SQLite

Trạng thái: chấp nhận cho Phase 2. Ngày: 08/11/2026.

Bối cảnh: nhóm bốn người, laptop demo, chưa có inference/dataset. Cần end-to-end có persistence trước khi đầu tư camera.

Quyết định: FastAPI/SQLAlchemy/SQLite một process; FSM thuần Python; React/Vite build static; full WS snapshots. Test dùng temporary SQLite và clock injection, runtime dùng UTC server clock thật.

Lợi ích: khởi động offline một tiến trình, dễ tái hiện/test, không có broker/cloud và không cần đồng bộ distributed state. Price snapshot và unique index là invariants ở lớp DB/nghiệp vụ.

Hệ quả: không nhiều workers; chưa có auth/network deployment, schema migrations hoặc retention. Tách vision I/O khỏi backend khi thêm camera để inference không chặn WS. Đánh giá lại khi nhiều camera/máy hoặc có nhu cầu vận hành thật.

Không chọn Redis/Kafka/PostgreSQL ngay vì chưa có yêu cầu tải và chi phí vận hành không phục vụ demo.
