# Demo acceptance

## Gate A — Phase 2 phần mềm

- Bốn bàn khởi tạo thật từ SQLite, chưa có doanh thu hoặc phiên dựng sẵn.
- UI luôn ghi rõ mode; source SIMULATED không thành AI sau auto-open hoặc nhân viên xác nhận.
- Default phát ≥8s → NEEDS_CONFIRMATION, chưa có tiền; confirm tạo một session.
- Dừng phát không đóng phiên; duplicate event/manual retry không nhân session.
- Backend quote/checkout chính thức, VND số nguyên, snapshot đơn giá, UTC và history bền vững.
- WS cập nhật, full snapshot khi reconnect; offline data bị báo stale và khóa thao tác.
- Có hướng dẫn cài/build/chạy/test; dựng trước và ngắt Internet vẫn có dashboard local.
- Pytest/Vitest/build/smoke được chạy và kết quả ghi TEST_RESULTS. Browser checks chỉ pass khi quan sát thực tế.

## Gate B — MVP camera thật (chưa đạt)

- Camera/webcam hoặc video test có nguồn hiển thị đúng LIVE/VIDEO, không dùng SIMULATED thay detection.
- Bốn bàn có calibration, standing/play polygons, tracking và ambiguity.
- Loss/reconnect/FPS thấp/near-far được thử; không mở nhầm vì frame cũ, không tự kết phiên.
- Dataset/evaluation có ground truth, counts và điều kiện chạy; không đưa accuracy/FPS chưa đo.
- REAL_CLUB/MINI_TABLE phân biệt rõ, cue readiness có evidence riêng.
- Kịch bản sân khấu, manual fallback, recording và offline weights đủ.

Người sign-off đề xuất: Đạt kỹ thuật, Sơn camera, An nghiệp vụ/UI, Đức demo. Không tự ghi chữ ký hoặc xác nhận nghiệm thu thay nhóm.
