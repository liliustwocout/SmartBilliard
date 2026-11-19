# API Phase 2

Base `http://127.0.0.1:8000`; JSON; OpenAPI máy đọc ở `/openapi.json`. `/docs` dùng Swagger assets từ CDN nên có thể không render khi mất Internet; dashboard không phụ thuộc CDN.

- `GET /api/health`: status=ok, phase=2, camera_ready=false.
- `GET /api/dashboard`: full snapshot với server_time, timezone, mode, capabilities, config, tables, events, active_count, revenue_vnd, running_amount_vnd.
- `GET /api/tables`: danh sách cùng định dạng tables trong snapshot (kèm `roi_calibrated`, `roi_enabled` từ cấu hình ROI hiện hành).
- `POST /api/tables/{id}/open`: không cần body; tạo STAFF hoặc STAFF_CONFIRMATION, trả session. Nếu đang ACTIVE trả session cũ. Nhân viên được bypass cooldown vì đây là quyết định thủ công.
- `GET /api/sessions?limit=100&offset=0`: mới nhất trước; limit 1..500. Trả cả ACTIVE/PAID, không có tổng count.
- `GET /api/sessions/{id}/quote`: session và quote tại thời gian backend; phiên PAID dùng thời điểm ended_at nên tiền ổn định.
- `POST /api/sessions/{id}/checkout`: chốt tiền và thời điểm; lặp trả hóa đơn cũ. Đây là ghi nhận thanh toán demo, không kết nối tiền thật.
- `POST /api/simulations/observations`: body dưới đây. Chỉ nhận source SIMULATED cố định; không nhận timestamp hoặc source client. Cờ mô phỏng tắt trả 403.
- `WS /ws`: gửi snapshot ngay sau connect, sau thay đổi và khoảng 1 giây. Client không phải gửi message. Reconnect nhận snapshot mới đầy đủ.

### Camera và hiệu chuẩn (nhánh tích hợp thử nghiệm)

- `GET /api/camera/status`: trạng thái nguồn, FPS vòng xử lý, `paused_tables` (bàn đang có phiên nên AI bỏ qua), `inference_paused` (true khi mọi bàn đã hiệu chuẩn đều đang có phiên và YOLO/tracker không chạy) và `models.person`/`models.cue` với `name`, `loaded`, `backend`; cue có thêm `validated`. `loaded=true` chỉ xác nhận ONNX đã nạp, không chứng minh model chính xác trên camera. `fps` không phải FPS suy luận khi thiếu weights.
- `GET /api/dashboard` và `WS /ws`: thêm `model_status` cùng cấu trúc để UI không nhầm nguồn hình đã kết nối với nhận diện AI đang hoạt động.
- `GET /api/camera/stream`: MJPEG có ROI/detection/HUD; `?annotated=false` trả khung hình gốc cho ROI editor. `GET /api/camera/frame?annotated=false` trả một JPEG gốc.
- `GET /api/calibration/preview`: khung hình gốc để hiệu chỉnh. `GET/POST /api/calibration/zones`: đọc/lưu đa giác normalized `[0,1]`; POST nạp lại ROI cho runner đang chạy. Editor chỉ cập nhật màn trực tiếp sau khi lưu thành công.
- `GET /api/videos`, `POST /api/videos/upload`, `POST /api/videos/activate`, `POST /api/videos/evaluate`, `POST /api/videos/generate-demo`, `POST /api/videos/extract-dataset`, `POST /api/videos/delete`: quản lý thư viện video cục bộ dưới `recordings`. `POST /api/videos/delete` nhận `{"filename": "..."}`, tự dừng runner và trả về nguồn camera mặc định nếu video đang phát Live rồi xoá file (trả 404 nếu không tìm thấy).

### Cấu hình chỉnh trực tiếp (trang Hệ thống & camera)

Có hiệu lực ngay, không cần khởi động lại. Giá trị ngưỡng, `auto_open` và `camera_source` lưu trong `data/runtime_settings.json` (gitignore, có thể chứa URL camera), nạp lại khi khởi động; không ghi đè `configs/decision.toml` hay `.env`. Với DB `:memory:` thì không lưu.

- `GET /api/settings`: `decision`, `decision_defaults`, `auto_open`, `camera_source` (mật khẩu trong URL được che `***`), `camera_source_default`, `overridden` (các mục đang override), `persisted`.
- `POST /api/settings`: cập nhật một phần `{"decision": {...}, "auto_open": bool, "confirm_auto_open": bool, "camera_source": str}`. Ngưỡng được kiểm tra bằng `DecisionConfig` (ví dụ `confidence_exit` > `confidence_enter` trả 422 và không đổi gì). Bật `auto_open` (chế độ **AI tự động mở bàn**, AI không bao giờ tự đóng phiên) bắt buộc `confirm_auto_open: true`, nếu không trả 422. Đổi `camera_source` khi runner đang chạy sẽ khởi động lại luồng.
- `POST /api/settings/reset`: xóa override, về cấu hình từ file/env (kể cả nguồn camera).
- `POST /api/tables/{id}/rate`: `{"hourly_rate": int}` VND 0..10.000.000. Phiên ACTIVE giữ `hourly_rate_snapshot` đã chốt lúc mở bàn. Bàn ngoài `TABLE_COUNT` trả 404.
- Snapshot/`GET /api/tables` thêm `ai_paused` theo bàn: true khi bàn có phiên ACTIVE nên AI không phát quan sát cho bàn đó; thanh toán xong thì chạy lại.

```json
{"event_id":"0b15a1be-e7b6-4aa8-8d7b-bf8af454c828","table_id":1,"present":true,"confidence":0.9,"ambiguous":false}
```

UUID mới cho mỗi observation; cùng UUID/cùng payload trả duplicate=true, không tích lũy thêm thời gian. Cùng UUID/khác payload trả 409. cue_confidence tùy chọn [0,1] chỉ là input test, không khiến detector_ready=true. event_id/table_id bắt buộc. Unknown fields trả 422.

Session trả: id, table_id, started_at/ended_at ISO UTC, status, hourly_rate_snapshot, total_amount (null trước chốt), trigger_source, evidence_source, elapsed_seconds, billable_minutes, amount_vnd. Với ACTIVE, amount_vnd là quote; total_amount chỉ là tiền đã chốt.

Observation response: state, reason, session_id nullable, source=SIMULATED, duplicate. state thuộc FSM; reason enum được định nghĩa trong decision.py. Event snapshot có event_type, confidence, timestamp, provenance và decision result.

Lỗi: 404 không có bàn/phiên; 422 input; 403 browser Origin không hợp lệ hoặc tắt mô phỏng; 409 idempotency conflict; 400 Host không hợp lệ. Chưa có auth; chỉ chạy local. Giữ default port 8000/5173 để khớp danh sách browser Origin.
