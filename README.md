# SmartBilliard · PSI2026

MVP quản lý bàn bi-a bằng camera AI trong tương lai. **Bản hiện tại hoàn thành phạm vi Phase 0–2: tích hợp bằng sự kiện mô phỏng, chưa nhận diện camera thật.**

Chạy được: 4 bàn mặc định (cấu hình 1–8), quyết định theo thời gian, yêu cầu xác nhận, mở bàn thủ công, một phiên ACTIVE/bàn, tính phí backend, checkout và lịch sử SQLite, dashboard tiếng Việt tối và WebSocket. Không tự đóng phiên khi mất tín hiệu. Không có dịch vụ Internet trong luồng vận hành.

## Kiến trúc

`Bộ phát mô phỏng → Temporal Decision Engine → FastAPI → SQLite → WebSocket → React`

Frontend chỉ hiển thị tiền/thời gian do server gửi. Tiền là số nguyên VND; mỗi phút bắt đầu được tính trọn phút; tiền lẻ được làm tròn lên 1 đồng. Ví dụ 60.000đ/giờ: đúng 60 giây = 1.000đ; 60 giây + 1µs = 2.000đ. Chốt giá lúc mở phiên, chốt tiền lúc checkout. Dữ liệu thời gian UTC, hiển thị Asia/Ho_Chi_Minh.

- `apps/api/`: API, models, billing và integration tests.
- `apps/web/`: React + TypeScript + Vite + Tailwind, Vitest.
- `services/vision/`: FSM thuần Python và contracts; chưa có detector/camera reader.
- `configs/`: ngưỡng TOML và ROI mẫu để chuẩn bị hiệu chuẩn.
- `docs/`: sản phẩm, kiến trúc, kế hoạch, AI, kiểm thử, phần cứng, demo.
- `scripts/`: bộ phát tín hiệu và smoke test HTTP/WebSocket thật.
- `data/`: SQLite runtime (gitignore); không chứa dữ liệu người chơi.

## Cài đặt (PowerShell, từ thư mục gốc repository)

Yêu cầu Python **3.11+**, Node **22.17+**, npm, trình duyệt hiện đại. Chưa cần GPU, webcam hoặc Docker ở Phase 2. Cài dependencies lần đầu cần Internet; demo sau khi cài và build có thể ngắt Internet.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
cd apps/web
npm ci
npm run build
cd ../..
```

`requirements.lock.txt` khóa môi trường kiểm thử Python; `requirements.txt` là dependency đầu vào. `package-lock.json` khóa frontend. Không ghi đè `.env` nếu đã cấu hình. Tất cả lệnh API/test chạy tại thư mục gốc để đường dẫn SQLite và config nhất quán.

## Chạy demo offline (một tiến trình)

```powershell
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --env-file .env
```

Mở [dashboard cục bộ](http://127.0.0.1:8000). Build web **trước** khi khởi động API để API phục vụ được thư mục `dist`. Dùng **một worker**, không dùng `--workers` nhiều hơn 1. Các session và FSM tồn tại qua restart, không có nút xóa database trong ứng dụng.

Demo: chọn bàn 1 → bắt đầu tín hiệu hiện diện → chờ ít nhất 8 giây → thấy “Chờ xác nhận” → xác nhận mở → dừng tín hiệu (phiên vẫn ACTIVE) → thanh toán → xem lịch sử. Mọi tín hiệu hiển thị “MÔ PHỎNG”. Dùng “Gửi lại sự kiện gần nhất” để kiểm tra idempotency.

Tự mở trong **demo được kiểm soát**: đổi `AUTO_OPEN_ENABLED=true` trong `.env`, khởi động lại API. Phiên tự mở ghi nguồn `SIMULATED`, không ghi AI. Mặc định tắt. Đổi `SIMULATION_ENABLED=false` để chỉ vận hành thủ công.

## Chạy phát triển (hai terminal)

```powershell
# Terminal 1, thư mục gốc
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --env-file .env --reload
# Terminal 2
cd apps/web
npm run dev
```

Mở [Vite](http://127.0.0.1:5173); Vite proxy `/api` và `/ws` tới API, không cần mở CORS tùy ý. Frontend hiển thị lỗi và khóa thao tác khi mất realtime, rồi tự kết nối lại với snapshot đầy đủ.

## Chạy kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest
cd apps/web
npm test
npm run build
cd ../..
.\.venv\Scripts\python.exe scripts/smoke.py
```

Smoke test tự chạy API trên `127.0.0.1:8001` bằng **database tạm**, kiểm tra tài nguyên web đã build, HTTP, WebSocket, mô phỏng, xác nhận, checkout, rồi dừng tiến trình. Không đụng database demo.

Phát tín hiệu bằng CLI (API phải đang chạy):

```powershell
.\.venv\Scripts\python.exe scripts/simulate.py --table 1 --seconds 12
```

## Camera / AI: chưa chạy trong Phase 2

`CAMERA_ID`, `CAMERA_SOURCE`, `VISION_MODE` trong `.env.example` là hợp đồng chuẩn bị, **chưa được đọc bởi camera adapter**. Chưa có lệnh chạy AI vì reader, YOLO, tracker, zone mapper và hand adapter chưa triển khai. Không cần cài Ultralytics/OpenCV trước Phase 3. `configs/zones.example.json` chỉ là ROI minh họa; phải vẽ lại trên khung hình thực.

PERSON_AND_CUE luôn yêu cầu kiểm tra thủ công ở Phase 2 kể cả có confidence gậy từ mô phỏng. COCO person detector không phải cue detector. MINI_TABLE không chứng minh khả năng phát hiện người thật.

## Giới hạn và an toàn dữ liệu

Chưa có login, phân quyền, audit nhân viên hoặc gateway thanh toán. Chỉ bind loopback trên laptop demo, không triển khai mạng công cộng. POST và WebSocket kiểm tra browser Origin; Host chỉ chấp nhận localhost/127.0.0.1. Không có secrets mặc định. Lịch sử là hóa đơn **demo**, không xác nhận tiền đã chuyển ngoài đời. Không có video/ảnh được lưu.

SQLite/FSM/WebSocket hiện phục vụ một process; scale nhiều worker cần thiết kế lại đồng bộ. Dashboard chỉ nhận 30 detection events mới nhất; lịch sử session có phân trang. Event log tăng theo số tín hiệu; ngừng bộ phát khi không demo, chưa có retention tự động. Backup file `data/smartbilliard.db` **khi đã dừng API** trước khi thay đổi schema; chưa có migration tự động cho database cũ. Không tự xóa DB để sửa lỗi.

Chưa đo precision/recall, FPS, độ trễ camera, CPU/RAM hoặc khả năng 4–8 bàn. Xem [bằng chứng triển khai](docs/competition/MVP_EVIDENCE.md), [kết quả kiểm thử](docs/testing/TEST_RESULTS.md) và [backlog](docs/planning/TASK_BACKLOG.md). Dừng ở Phase 2 trước khi triển khai camera.

## Theo dõi phát triển trên GitHub

Repository: [liliustwocout/SmartBilliard](https://github.com/liliustwocout/SmartBilliard). Xem [issue và milestone](docs/planning/GITHUB_ISSUES.md) để nhận việc tiếp theo. Người phụ trách trong issue là đề xuất theo kế hoạch; chưa gán GitHub assignee khi chưa có mapping tài khoản thành viên.

GitHub Actions chạy Pytest, Vitest, production build và HTTP/WS smoke trên Ubuntu và Windows khi mở PR vào main hoặc cập nhật main. CI dùng dữ liệu nhân tạo; không thay thế kiểm chứng camera. Hồ sơ đăng ký có thông tin cá nhân chỉ giữ local, không public trên GitHub.
