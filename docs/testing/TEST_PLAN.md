# Kế hoạch kiểm thử

## Lớp 1 — logic nhân tạo (Phase 2)

Pytest kiểm tra FSM/config/billing; API integration test bằng TestClient và SQLite tạm. Inject clock để thử duration/boundary nhanh, runtime vẫn dùng clock UTC thật. Kiểm tra duplicate payload conflict, concurrent opens, restart persistence, price snapshot, checkout theo session ID, ambiguity/gap/cooldown và cue readiness guard.

Vitest kiểm tra định dạng thời gian/tiền và source label. TypeScript strict + Vite build kiểm tra cấu trúc frontend. Chưa có component tests riêng; UI hành vi cần kiểm tra trình duyệt.

## Lớp 2 — tích hợp process thật (Phase 2)

Sau web build chạy `scripts/smoke.py`: API thật trên loopback 8001, database tạm, HTTP và WS handshake/full snapshots, chuỗi mô phỏng đủ thời gian, staff confirmation, quote/checkout/history. Tiến trình tự dừng và xóa tài nguyên tạm. Đây không phải test camera.

Browser QA: desktop/mobile, đầu vào sim, trạng thái confirm, checkout, history, mất server/reconnect và keyboard focus. Các thao tác không dùng data cá nhân. Mỗi check ghi thật vào TEST_RESULTS; không đánh dấu pass khi chưa chạy.

## Lớp 3 — thị giác và hardware (chưa có)

Clip được gán nhãn cho 15 scenarios ở TEST_CASES; camera/video source loss/reconnect, multi-track/ROI ambiguity, near/far, 4 bàn, sau đó 8 bàn nếu khả thi. Ground truth chưa có nên chưa chạy. REAL_CLUB/MINI_TABLE báo cáo riêng.

## Gate bàn giao

Phase 2: checks xanh, không sessions/metrics điền sẵn, default không auto-charge, simulation label, docs/runbook đủ. Full camera MVP: DEMO_ACCEPTANCE và evidence video/hardware bắt buộc; unit xanh không đủ.

Trên môi trường Windows bị sandbox mạng, TestClient cần socketpair loopback của asyncio. Nếu test treo ở `_make_self_pipe`, chạy cùng lệnh trong terminal có quyền loopback; không sửa logic nghiệp vụ để né giới hạn môi trường.
