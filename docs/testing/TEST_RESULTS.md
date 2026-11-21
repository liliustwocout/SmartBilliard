# Kết quả kiểm thử Phase 2

## Tối ưu FPS — DirectML và chế độ nhanh

- Đổi runtime sang ONNX Runtime DirectML tùy chọn, giữ model Pose/input 640; preset nhanh tắt model gậy chưa kiểm chứng (`cue_enabled=false`, backend `DISABLED`). Có thể bật lại trong `configs/vision.toml`; UI phân biệt tắt model với mất weights. Không huấn luyện lại hay cache/hardcode kết quả nhận diện.
- Cache JPEG theo sequence dùng chung giữa các cửa sổ; preview 960 px/JPEG 75; buffer RGB/NCHW được tái dùng nhưng cập nhật từ khung mới, đối chiếu với OpenCV sai số tối đa `1e-7` trong unit test. Decoder 2 threads, OpenCV 1 thread, mục tiêu 30 FPS; file vẫn được phát theo FPS nguồn. MJPEG đưa việc vẽ/nén ra khỏi event loop và không gửi khung lặp khi nguồn đang chạy.
- Giới hạn phát quan sát 5 Hz vào SQLite/FSM. Thêm index cho `ORDER BY timestamp DESC, id DESC LIMIT 30`; startup bổ sung index vào DB cũ, không xóa dữ liệu. DB thử đang có khoảng 93.000 sự kiện. Đo dashboard trước tối ưu index khoảng 2.118 ms, lần đo cuối **13,81 ms**.
- Bài đo tuần tự CPU trước tối ưu, có cả Pose/gậy/overlay/JPEG: **7,07 FPS** trên 120 khung. Các thử nghiệm DirectML có cả gậy biến động theo tải máy, chưa giữ được 30 FPS ổn định. Preset nhanh cuối, 120 khung thật sau 10 khung warmup, gồm decode/Pose/tracking/mapping/overlay/JPEG: **35,26 FPS**, p50 **24,08 ms**, p95 **50,60 ms**. Một lần đo 120 khung khác chỉ đạt khoảng 17 FPS khi tải máy thay đổi; không dùng số peak làm cam kết ổn định. Benchmark không gồm SQLite/HTTP/trình duyệt, chưa đo precision/recall.
- Kiểm tra HTTP cuối trên `cam2_03.mp4`: **233 JPEG, 233 hash khác nhau** trong **11,978 s**, nhận **19,37 FPS**; runner/Pose **19,34 FPS**, nguồn **19,49 FPS**, target **30 FPS**. Model Pose báo `DIRECTML:0`; gậy `DISABLED`, `validated=false`; `auto_open=false`. Nguồn 20 FPS không thể chứng minh 30 khung mới/giây.
- Kiểm thử cuối: **165 pytest passed**, **12 frontend passed**, production build và smoke HTTP/WS/billing/idempotency đều đạt. Một warning Starlette/httpx có sẵn. Test mới gồm fallback GPU/CPU, cache JPEG và độ phân giải raw, cấu hình sai, read lỗi không tăng FPS, pause AI báo 0, throttle quan sát, buffer preprocessing và nâng cấp index idempotent giữ dữ liệu.
- Bằng chứng local (gitignore): `data/datasets/cue_runtime_trial_20261121T121607Z/fps_http_check.json`, `fps_running_frame.jpg`, `fps_fast_final120.json`, `fps_cpu_benchmark.json`, `gpu_probe.json`. Chưa cắm camera 30 FPS, chưa kiểm nghiệm dài hạn/tải nặng; không nghiệm thu độ chính xác hay bật tính tiền tự động.

## Bổ sung ngày 21/11/2026 — tự đề xuất ROI từ khung hình

- Thêm **Tự nhận diện bàn** trong ROI editor và API `POST /api/calibration/auto-detect`. Phân tích màu mặt nỉ/đường biên bằng OpenCV local; không dùng model bàn đã huấn luyện, không tạo detection cố định. Vùng đứng chỉ là ước lượng có thể chỉnh.
- Pytest **151 passed** (một warning Starlette/httpx có sẵn), frontend **11 passed**, production build và smoke HTTP/WS đều đạt. Test mới kiểm tra hình thang có che một phần, áo xanh dính mặt bàn, vùng áo xanh thẳng đứng, giữ ID/trạng thái bật tắt, ROI không nhận diện lại, giới hạn số bàn, khung hình trống, clipping vùng đứng, config sai và hợp đồng API chỉ đề xuất/không tự lưu. Các ảnh test là nhân tạo, không phải bằng chứng độ chính xác camera.
- Kiểm tra API và nút thật trên video quán: đề xuất mặt bàn/vùng đứng cho **Bàn 01–02**, giữ số bàn. Editor hiện đúng JPEG dùng phân tích, thông báo bản nháp chưa lưu; so sánh hash xác nhận file ROI đang dùng vẫn nguyên vẹn. Để bản đề xuất mở cho người dùng kiểm tra, chưa tự áp dụng lên cấu hình đã lưu.
- Bằng chứng cục bộ (gitignore): `data/datasets/cue_runtime_trial_20261121T121607Z/auto_roi_api_check.json`, `auto_roi_api_frame.jpg`, `auto_roi_browser_check.jpg`. Camera/video tiếp tục chạy và `auto_open=false`.
- Giới hạn quan sát: có frame bị che nhiều chỉ tìm lại được một bàn; màu áo xanh từng gây nhận nhầm và đã bổ sung lọc hướng cạnh cùng regression test. Bàn phủ vải, màu khác, ánh sáng xấu và camera khác chưa được nghiệm thu. Chưa có ground truth toàn cảnh để báo precision/recall. Không thay model người/gậy, không bật tự tính tiền.

## Bổ sung ngày 21/11/2026 — nút xóa ROI dễ tìm

- Đưa **Xóa ROI Bàn …** lên cạnh **Thêm bàn** trong thanh chọn bàn; nút tắt khi bàn chưa có ROI hoặc đang lưu. Giữ bước xác nhận và yêu cầu **Lưu cấu hình ROI** để áp dụng.
- Mở rộng test API trên SQLite tạm: xóa ROI của bàn có phiên ACTIVE vẫn giữ phiên, lưu/đọc lại đúng danh sách vùng, và chấp nhận xóa hết ROI.
- Pytest **139 passed** (một warning Starlette/httpx có sẵn), frontend **11 passed**, production build và `scripts/smoke.py` đều đạt.
- Thử qua giao diện tại `127.0.0.1:8000` trên cấu hình riêng của lần chạy thử: thêm/lưu Bàn 03, hủy xóa vẫn giữ vùng, xác nhận xóa rồi lưu thì Bàn 03 chuyển về **Chưa hiệu chuẩn**. API xác nhận chỉ còn hai vùng Bàn 01–02 ban đầu; camera vẫn chạy, `auto_open=false`.
- Ảnh kiểm tra: `data/datasets/cue_runtime_trial_20261121T121607Z/roi_delete_check.jpg` (dữ liệu cục bộ, không commit). Không thay model hay đánh giá lại độ chính xác nhận diện gậy/hành động trong thay đổi này.

## Bổ sung ngày 21/11/2026 — chốt rà soát dữ liệu

Pytest **139 passed** (một warning Starlette/httpx có sẵn), frontend **11 passed**, build và HTTP/WS smoke dùng SQLite tạm sau build đều **PASS**. Các test mới kiểm tra bảo toàn nhãn đồng thuận, phủ đủ clip chưa chốt, loại nhãn/ID sai, cắt đồng bộ frame-box-keypoint và giữ nguồn AI riêng khỏi phiếu người.

Đã kiểm tra hash nguồn không đổi, xuất 100 clip hành động và 97 ảnh gậy/ảnh âm sau rà soát, huấn luyện lại và so sánh công bằng trên validation đã sửa. V3 không hơn V2 nên giữ model cũ; diagnostic video vẫn bỏ sót gậy. [Bằng chứng và giới hạn](../ai/LABEL_REVIEW_20261121.md).

## Bổ sung ngày 20/11/2026 — gậy thử nghiệm và gán nhãn

Pytest **128 passed** (một warning Starlette/httpx), frontend **11 passed**, production build **PASS**, HTTP/WS smoke sau build với SQLite tạm **PASS**. Windows smoke dùng `PYTHONUTF8=1` để process con xuất cùng encoding, tắt camera trong smoke.

ONNX gậy đã được nạp và chạy thật bằng OpenCV, gate kiểm chứng vẫn tắt. Model **chưa đạt**: diagnostic crop có 0 TP / 1 FP / 4 FN; đoạn video toàn cảnh 24 giây có 0 detection trên 94 frame lấy mẫu ở ngưỡng 0,35. Nhãn crop do AI rà soát, chưa phải ground truth được người nghiệm thu. Xem [bằng chứng, gói nhãn và giới hạn](../ai/CUE_AND_LABELING_20261120.md). Những kiểm tra phần mềm trên không thay kết quả model.

## Mốc Phase 2 gốc

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
