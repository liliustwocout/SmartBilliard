# Báo cáo Phase 0–2 — SmartBilliard

## 1. Đã kiểm tra

Repository ban đầu có AGENTS.md rỗng và hồ sơ dự thi dạng text, không có code/manifest/Git. Giữ nguyên hồ sơ, không copy dữ liệu liên hệ cá nhân vào ứng dụng. Kiểm tra Python 3.11.9/Node22.17/npm11.12.1 và tạo môi trường local riêng. Chi tiết: REPOSITORY_ASSESSMENT.md.

## 2. Kiến trúc và lý do

Monorepo React/Vite/TypeScript/Tailwind + một FastAPI process + SQLAlchemy/SQLite. FSM thuần Python tách detection và quyết định mở phiên. WS gửi full snapshot và quote backend mỗi giây, dễ khôi phục sau reconnect và không cần broker. Một ACTIVE/bàn được DB partial unique index bảo vệ; timestamp UTC, integer VND, rate snapshot, checkout theo session ID. Chưa tạo infra rỗng hoặc thêm cloud.

## 3. File tạo/sửa

Sửa AGENTS.md ban đầu rỗng. Tạo mã API/tests, web/tests/config/lockfile, FSM/contracts/tests, configs, README/env/gitignore/Python lock, script simulation/smoke, tài liệu trong bảy nhóm docs bắt buộc và screenshot QA. Danh sách đầy đủ: FILE_MANIFEST.md. Hồ sơ tham khảo giữ nguyên. Runtime .venv/node_modules/dist/SQLite/.env không là source để commit.

## 4. Tính năng chạy thật

Bốn bàn mặc định; config tối đa tám; mở bàn thủ công; tín hiệu mô phỏng qua FSM với presence/hysteresis/grace/gap/cooldown; default NEEDS_CONFIRMATION; auto-open demo tùy env; idempotency payload/UUID; session/event/FSM persisted; chống mở đồng thời; backend tính tiền và checkout; history/revenue; WS/reconnect/stale UI; dashboard tiếng Việt tối, chi tiết bàn, history, trang khả năng hệ thống; production web phục vụ cùng API.

## 5. Mock/chưa triển khai

Chỉ đầu vào observation là **SIMULATED**, không có hardcoded kết quả AI/session/revenue. Camera/RTSP/file capture, YOLO, tracker, mapper, ROI editor/overlay, hand adapter và cue model chưa triển khai. VideoSource/CueDetector chỉ là protocols, ROI JSON là mẫu chưa hiệu chuẩn. PERSON_AND_CUE không auto-open trong API Phase 2. Không có inference metrics hoặc camera evidence.

## 6. Kiểm thử và kết quả

39 Pytest pass; 3 Vitest pass; TypeScript/Vite build pass; real-process HTTP/WS smoke pass, cleanup pass. Vitest đã nâng 5.1.0, npm audit reported 0 vulnerabilities. Browser QA: full simulated confirmation/checkout/history, giữ phiên sau absence, stale controls khi tắt API, tự reconnect không reload và giữ SQLite, layout laptop/mobile. Chi tiết, warning và giới hạn: docs/testing/TEST_RESULTS.md.

## 7. Vấn đề còn lại

Chưa có dataset/camera/weights nên chưa thể tuyên bố full AI MVP. Chỉ local single process, chưa auth/roles/audit nhân viên, migration/retention hoặc tích hợp thanh toán thật. Một deprecation warning Starlette/httpx trong test; không ảnh hưởng kết quả. Chưa đo latency/FPS/CPU/RAM hoặc tám bàn, chưa rút Internet vật lý để kiểm chứng. Runtime source camera env chưa được adapter sử dụng.

## 8. Milestone tiếp theo

SB-09 camera/video adapter + health/reconnect (Sơn), SB-10 ROI calibration/editor (Sơn/An), sau đó person/tracker/mapper và ingestion thật (Sơn/Đạt), dataset/consent (Đức/Sơn), validation bốn bàn. Roadmap bốn tuần và 20 backlog items có owner/priority/dependencies/acceptance/status. Dừng tại Phase 2 theo yêu cầu; không tự triển khai Phase 3.

## 9. Lệnh chạy

Từ root, môi trường đã cài và frontend đã build:

```powershell
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --env-file .env
```

Mở http://127.0.0.1:8000. .env hiện là bản copy mặc định không chứa credentials; không ghi đè nếu đã chỉnh. Server QA được dừng, dữ liệu QA nằm riêng data/browser-qa.db; server mặc định tạo data/smartbilliard.db mới nếu chưa có.

Setup mới và đầy đủ lệnh tests/development/offline: README.md. Không có lệnh chạy AI ở Phase 2 vì thành phần đó chưa được triển khai.
