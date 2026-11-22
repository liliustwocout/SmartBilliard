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

## Camera / AI: tích hợp thử nghiệm, chưa nghiệm thu model

Nhánh hiện tại có nguồn video/camera, ROI editor, overlay, tracker và đường nạp YOLO ONNX qua OpenCV DNN. `CAMERA_ENABLED` mặc định tắt; weights riêng không kèm Git, trạng thái thực tế tùy file trên máy. `GET /api/camera/status` và dashboard trả trạng thái model (`loaded`, `backend`, riêng gậy có `validated`); FPS của vòng đọc hình không chứng minh inference. Khi có weights, code thử CUDA FP16 nếu OpenCV hỗ trợ, còn không dùng CPU. Model gậy một lớp đã nạp có thể chạy để vẽ **gậy thử nghiệm** khi có người; gậy chưa kiểm chứng bị lọc trước bước tổng hợp bàn/FSM và `validated=false` vẫn giữ nguyên. Chưa có kiểm chứng thực địa để bật tính tiền tự động. `configs/zones.example.json` là ROI minh họa; phải vẽ lại trên khung hình thực và bấm **Lưu cấu hình ROI** thì màn Camera trực tiếp mới dùng vùng mới.

**Tiết kiệm tính toán và cảnh báo xác nhận.** Bàn đã có phiên ACTIVE (mở thủ công, xác nhận hoặc tự mở demo) bị tạm dừng nhận diện: runner không phát quan sát cho bàn đó, và khi *mọi* bàn trong ROI đều đang có phiên thì pipeline vẫn đọc khung hình (để xem live) nhưng bỏ qua YOLO và tracker. Thanh toán xong, bàn trống lại và nhận diện chạy lại (tracker được reset). Mô hình chạy trên toàn khung hình nên khi chỉ một phần bàn có phiên, YOLO vẫn chạy cho các bàn còn lại. `GET /api/tables`/snapshot có thêm `ai_paused` theo bàn; `GET /api/camera/status` có thêm `paused_tables` và `inference_paused`. Khi AI thấy đang đánh và bàn chưa mở (`NEEDS_CONFIRMATION`), Tổng quan hiện banner với nút **Xem camera** và **Xác nhận mở**; AI không tự đóng phiên.

Trong **Hiệu chuẩn ROI**, chọn bàn rồi bấm **Xóa ROI Bàn …** cạnh **Thêm bàn**, xác nhận và bấm **Lưu cấu hình ROI**. Thao tác gỡ cả vùng mặt nỉ và vùng đứng; bàn chuyển về **Chưa hiệu chuẩn** và có thể tạo ROI lại. Phiên chơi, hóa đơn và danh sách bàn tính tiền được giữ nguyên.

**Tự nhận diện bàn:** phát video hoặc bật camera, vào **Hiệu chuẩn ROI** và bấm **Tự nhận diện bàn**. Hệ thống phân tích khung hình thật bằng màu mặt nỉ xanh lá/xanh dương và đường biên OpenCV local, tạo đề xuất mặt bàn cùng vùng đứng ước lượng, đồng thời giữ ảnh đã phân tích làm nền để kiểm tra. Đây là xử lý ảnh theo quy tắc, chưa có model AI nhận diện bàn đã huấn luyện. ROI khớp vùng cũ giữ số bàn và trạng thái bật/tắt; vùng chưa tìm lại được giữ nguyên. Kiểm tra số bàn, kéo lại đỉnh/vùng đứng và bấm **Lưu cấu hình ROI** để áp dụng. Bấm **Chụp lại ảnh nền** để trở về khung hình hiện tại.

Ngưỡng tự nhận diện nằm ở `configs/auto_roi.toml` (có thể đổi đường dẫn qua `AUTO_ROI_CONFIG`), được validate khi khởi động. Bàn phủ vải, bị che nhiều, mặt nỉ màu khác, góc quá xiên hoặc ánh sáng xấu có thể bị bỏ sót/nhận nhầm; kết quả không phải đo đạc mặt sàn hay độ chính xác AI đã nghiệm thu. Chức năng không tự lưu ROI, mở/đóng phiên hoặc thay đổi giá tiền.

Mặc định ưu tiên bàn có cạnh dài gần phương ngang trong ảnh để giảm nhầm áo người. Với camera xoay hoặc góc nhìn khác, cần điều chỉnh `max_long_edge_angle_degrees` trong cấu hình hoặc căn ROI thủ công.

**Chế độ nhanh** mặc định tắt model gậy thử nghiệm (`cue_enabled=false` trong `configs/vision.toml`), giữ Pose và tracking. Bật lại bằng `cue_enabled=true` rồi khởi động lại; UI báo rõ gậy bị tắt để ưu tiên FPS, không báo mất weights. Model gậy vẫn chưa được kiểm chứng.

**Tăng tốc video/nhận diện:** Windows có GPU DirectX 12 có thể cài thêm `.venv/Scripts/python -m pip install -r requirements-gpu.txt`. Detector ưu tiên ONNX Runtime DirectML, giữ nguyên weights/input 640; thiếu hoặc lỗi GPU thì quay về CPU và báo đúng backend. Trên máy nhiều GPU, `dml_device_id` là chỉ số adapter DirectML, không suy từ chỉ số CUDA. Xem `configs/vision.toml` / env `VISION_CONFIG`: mục tiêu 30 FPS, OpenCV 1 thread, decoder 2 threads, overlay tối đa 960 px, JPEG 75 và phát quan sát vào FSM/SQLite tối đa 5 Hz. Mỗi khung JPEG được cache dùng chung giữa các cửa sổ xem; nén/vẽ được đưa ra khỏi event loop HTTP.

`GET /api/camera/status` báo `fps` khung xử lý thành công, `inference_fps` khung thực sự chạy Pose, `source_fps` FPS danh nghĩa của nguồn và `target_fps`. HUD tách Video/AI FPS; bỏ qua inference khi mọi bàn có phiên thì AI FPS về 0. Phát file được giới hạn theo FPS gốc để giữ đúng tốc độ; clip 19–20 FPS không trở thành 30 FPS mới. Không đếm khung lặp hoặc lần đọc lỗi vào FPS.

Đo khả năng xử lý không giới hạn tốc độ bằng `scripts/benchmark_vision.py VIDEO --zones ZONES --frames 120 --output data/datasets/benchmark.json`; thêm `--opencv-cpu` để đối chiếu. Benchmark gồm decode, Pose, tracking, mapping, overlay/JPEG; thêm `--with-cue` để chạy cả model gậy khi có người; không gồm SQLite/HTTP/trình duyệt và không đo độ chính xác. Cần đo luồng HTTP riêng để kiểm tra trải nghiệm thực tế.

PERSON_AND_CUE luôn yêu cầu kiểm tra thủ công ở Phase 2 kể cả có confidence gậy từ mô phỏng. COCO person detector không phải cue detector. MINI_TABLE không chứng minh khả năng phát hiện người thật.

## Phòng quản lý (sản phẩm thật, tách biệt với phòng demo)

Đang xây dựng theo [kế hoạch](docs/planning/MANAGEMENT_ROOM_PLAN.md). Mốc M0 mới có khung: `apps/manage_api` (cổng 8100, DB `data/manage.db`) và `apps/manage_web` (cổng 5174). Chưa có đăng nhập, bàn, phiên hay gamification. Không dùng chung code, database hay cấu hình với `apps/api`/`apps/web`.

```powershell
.\.venv\Scripts\python.exe -m uvicorn apps.manage_api.main:create_app --factory --host 127.0.0.1 --port 8100 --env-file .env
cd apps\manage_web; npm run dev
```

## Giới hạn và an toàn dữ liệu

Chưa có login, phân quyền, audit nhân viên hoặc gateway thanh toán. Chỉ bind loopback trên laptop demo, không triển khai mạng công cộng. POST và WebSocket kiểm tra browser Origin; Host chỉ chấp nhận localhost/127.0.0.1. Không có secrets mặc định. Lịch sử là hóa đơn **demo**, không xác nhận tiền đã chuyển ngoài đời. Video do người dùng tải lên trong nhánh thử nghiệm được lưu cục bộ dưới thư mục `recordings` cạnh database; không được dùng làm bằng chứng model đã đạt yêu cầu nếu thiếu nhãn và phép đo.

SQLite/FSM/WebSocket hiện phục vụ một process; scale nhiều worker cần thiết kế lại đồng bộ. Dashboard chỉ nhận 30 detection events mới nhất; lịch sử session có phân trang. Event log tăng theo số tín hiệu; ngừng bộ phát khi không demo, chưa có retention tự động. Backup file `data/smartbilliard.db` **khi đã dừng API** trước khi thay đổi schema; chưa có migration tự động cho database cũ. Không tự xóa DB để sửa lỗi.

Chưa nghiệm thu precision/recall, FPS, độ trễ camera, CPU/RAM hoặc khả năng 4–8 bàn ở quán. Xem [bằng chứng triển khai](docs/competition/MVP_EVIDENCE.md), [kết quả kiểm thử](docs/testing/TEST_RESULTS.md) và [backlog](docs/planning/TASK_BACKLOG.md). Báo cáo Phase 0–2 là mốc MVP local; các phần camera/video và model hiện tại vẫn là thử nghiệm, không thay thế kiểm chứng thực địa.

## Theo dõi phát triển trên GitHub

Repository: [liliustwocout/SmartBilliard](https://github.com/liliustwocout/SmartBilliard). Xem [issue và milestone](docs/planning/GITHUB_ISSUES.md) để nhận việc tiếp theo. Người phụ trách trong issue là đề xuất theo kế hoạch; chưa gán GitHub assignee khi chưa có mapping tài khoản thành viên.

GitHub Actions chạy Pytest, Vitest, production build và HTTP/WS smoke trên Ubuntu và Windows khi mở PR vào main hoặc cập nhật main. CI dùng dữ liệu nhân tạo; không thay thế kiểm chứng camera. Hồ sơ đăng ký có thông tin cá nhân chỉ giữ local, không public trên GitHub.

## Chỉnh cấu hình trực tiếp (trang Hệ thống & camera)

Có hiệu lực ngay, không cần khởi động lại. Giá trị ngưỡng, tự mở bàn và nguồn camera lưu trong `data/runtime_settings.json` (gitignore; có thể chứa URL camera) và được nạp lại khi khởi động; không ghi đè `configs/decision.toml` hay `.env`. Giá giờ từng bàn lưu trong SQLite; phiên đang chạy giữ giá đã chốt.

| Endpoint | Mô tả |
|---|---|
| `GET /api/settings` | Ngưỡng hiện tại, mặc định, tự mở bàn, nguồn camera (mật khẩu được ẩn), danh sách mục đang override |
| `POST /api/settings` | Cập nhật một phần: `decision{...}`, `auto_open` (bật cần `confirm_auto_open: true`), `camera_source`. Ngưỡng sai (ví dụ confidence_exit > confidence_enter) trả 422, không đổi gì |
| `POST /api/settings/reset` | Xóa override, về cấu hình mặc định |
| `POST /api/tables/{id}/rate` | `{hourly_rate}` VND nguyên 0..10.000.000 |

## Gán nhãn hành động (gói offline)

Tạo gói gán nhãn từ video nhiều camera và gộp kết quả của team; hướng dẫn đầy đủ trong [docs/ai/LABELING_GUIDE.md](docs/ai/LABELING_GUIDE.md). Dữ liệu nằm trong `data/label_packs/` (gitignore), không commit clip hay nhãn.

```powershell
.\.venv\Scripts\python.exe scripts/build_label_pack.py --source cam-a=PATH --source cam-b=PATH --members 4 --redundancy 2
.\.venv\Scripts\python.exe scripts/merge_labels.py ket-qua-*.json
```

Thêm `--focus walking` để ưu tiên clip có dịch chuyển theo chiều cao người; đây chỉ là cách lấy mẫu, nhãn vẫn cần xem bằng mắt. Tạo lại gói cho các clip thiếu phiếu hợp lệ bằng `scripts/build_review_pack.py` (xem hướng dẫn). File kết quả của các batch khác nhau bị từ chối gộp vì `clip_id` có thể trùng.

Nhãn hành động `WALKING/AIMING/...` không thay thế bounding box gậy. Huấn luyện gậy dùng dataset YOLO riêng và môi trường riêng theo [models/README.md](models/README.md); [báo cáo thử nghiệm](docs/ai/CUE_AND_LABELING_20261120.md) ghi nguồn nhãn và giới hạn.

[Rà soát đã chốt ngày 21/11](docs/ai/LABEL_REVIEW_20261121.md): 100 clip hành động (23 WALKING), 97 ảnh gậy/ảnh âm sau đối chiếu; nhãn AI được đánh dấu nguồn riêng, không gộp thành phiếu người giả. `scripts/finalize_label_review.py` xuất bộ nhãn đã rà soát mà không ghi đè nhãn đồng thuận cũ.

