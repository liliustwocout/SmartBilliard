# Kết quả kiểm thử Phase 2

Ngày: 08/11/2026 (Asia/Saigon). Môi trường: Windows, Python 3.11.9, Node 22.17.0, npm 11.12.1. Dữ liệu kiểm thử là nhân tạo; **không có video/camera AI được kiểm chứng**.

## Các lệnh đã chạy

- `.venv/Scripts/python -m pytest`: **39 passed**, một deprecation warning từ Starlette TestClient/httpx (khuyến nghị httpx2 của thư viện; không làm test fail). Bao gồm FSM/config, integer billing boundaries, API, duplicate/conflict, concurrent opens, DB unique index, restart, multi-table WS và local Origin/Host guards.
- `npm test` trong apps/web: **3 passed**, Vitest 5.1.0; format duration/timezone/VND và provenance labels.
- `npm run build`: **PASS**, TypeScript strict và Vite 6.4.5 production bundle; assets local. Bản cuối đã build sau cập nhật reconnect watchdog và favicon.
- `.venv/Scripts/python scripts/smoke.py`: **PASS**, API process thật, database tạm, static web, HTTP/WS, simulated FSM, CLI publisher, staff confirmation, server quote, checkout, history, idempotency và cleanup Windows process tree.
- `npm install --save-dev vitest@5.1.0`: npm audit sau cập nhật báo **0 vulnerabilities** ở thời điểm chạy. Bản Vitest 3 ban đầu có ba advisories và đã được thay trước bàn giao. Không có tuyên bố an toàn tuyệt đối hoặc kết quả pip security audit.

## Kiểm tra trình duyệt thực

Dashboard tại 127.0.0.1:8000 phục vụ bằng FastAPI từ production dist, dùng **data/browser-qa.db riêng**.

- Ban đầu bốn bàn trống, doanh thu 0; không có số liệu dựng sẵn.
- Phát presence ~mỗi giây, chờ hơn ngưỡng 8s → NEEDS_CONFIRMATION, chưa có session.
- Nhân viên xác nhận bàn 1 → ACTIVE, source nhân viên xác nhận và evidence mô phỏng.
- Dừng phát → ABSENCE, phiên vẫn ACTIVE. Gửi lại event cũ không nhân session.
- Dialog thanh toán có quote backend và cảnh báo ranh giới phút. Chốt → PAID, hóa đơn demo **1.000đ**, thấy trong lịch sử với thời gian UTC hiển thị +7 và provenance.
- Tắt API → banner stale, nút mở bàn/phát tín hiệu bị khóa.
- Khởi động lại API cùng DB → **tự reconnect không reload**, thao tác được mở khóa, history giữ nguyên. Sau đó cũng kiểm tra reload với bundle mới.
- Kiểm tra layout desktop 1366×900 và mobile 390×844. Mobile không tràn ngang toàn trang (DOM scrollWidth 375, viewport 390 gồm scrollbar); bảng history có vùng scroll riêng.
- Console của bản cuối không có error/warn được ghi nhận trong lần kiểm tra. Dialog native đặt focus vào nút Quay lại khi mở; chưa audit accessibility đầy đủ.
- Ảnh `dashboard-preview.jpg` là screenshot kiểm chứng QA, doanh thu trong ảnh là hóa đơn mô phỏng đã tạo thật, không phải doanh thu kinh doanh.

## Lỗi gặp và đã khắc phục

Sandbox Windows chặn loopback/socketpair làm TestClient treo ở asyncio `_make_self_pipe`; chạy cùng test với quyền loopback thì hoàn tất. Không thay nghiệp vụ để né sandbox.

WebSocket TestClient dùng host mặc định khác HTTP base_url; test đã dùng URL ws://127.0.0.1/ws để giữ Host guard đúng thay vì nới guard.

Windows venv có child interpreter; smoke cleanup ban đầu chưa kết thúc cả cây tiến trình khiến file log còn bị khóa. Đã sửa dọn cây tiến trình do script sở hữu; lần chạy sau exit code 0.

## Chưa kiểm tra

Không có physical camera, RTSP reconnect, YOLO/tracker, dataset/precision/recall, near/far, CPU/RAM/FPS hoặc 8 bàn thật. Chưa thử rút kết nối Internet vật lý; kiểm tra static build và các tài nguyên local, dashboard không dùng CDN. Chưa có automated React component tests, full accessibility audit hoặc load test. Warning TestClient/httpx còn tồn tại, xem xét theo nâng cấp thư viện sau.

Server QA đã được dừng sau kiểm tra; khởi động theo README để dùng tiếp. Database QA được giữ riêng, không seed hóa đơn vào database mặc định.
