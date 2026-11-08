# Milestones và gates

- **M0 · Assessment:** inventory, dependency baseline, reuse/risk report. Hoàn tất; hồ sơ gốc giữ nguyên.
- **M1 · Architecture:** PRD, scope, ADR, database/API, backlog, owner, test/demo plan. Hoàn tất tài liệu ban đầu; thông số AI vẫn cần validation.
- **M2 · Simulated vertical slice:** API/SQLite/FSM/WS/dashboard, manual/confirmed/simulated opening, billing và test. Trạng thái theo `docs/testing/TEST_RESULTS.md`; chỉ hoàn tất khi checks đã chạy xanh.
- **M3 · Camera foundation:** 1 USB/RTSP/video source, reconnect, normalized ROI editor/preview. Chưa triển khai; Sơn owner, Đạt review. Acceptance: đọc nguồn thật, che credentials, loss/reconnect không sinh event mở nhầm.
- **M4 · Detection integration:** person + tracker + table mapper, ambiguity; xác nhận thủ công mặc định. Chưa triển khai. Evidence phải có video fixture được đồng ý dùng.
- **M5 · Validated demo:** 4 bàn, offline, near/far metrics, 15 scenarios, recording và handoff. Chưa đạt; không đưa “độ chính xác cao” vào pitch trước khi đo.

Mở rộng 8 bàn, 4K và cue model không phải điều kiện mặc định cho M2; là thử nghiệm sau M4, báo cáo giới hạn nếu không đạt.
