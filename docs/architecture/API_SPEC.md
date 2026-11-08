# API Phase 2

Base `http://127.0.0.1:8000`; JSON; OpenAPI máy đọc ở `/openapi.json`. `/docs` dùng Swagger assets từ CDN nên có thể không render khi mất Internet; dashboard không phụ thuộc CDN.

- `GET /api/health`: status=ok, phase=2, camera_ready=false.
- `GET /api/dashboard`: full snapshot với server_time, timezone, mode, capabilities, config, tables, events, active_count, revenue_vnd, running_amount_vnd.
- `GET /api/tables`: danh sách cùng định dạng tables trong snapshot.
- `POST /api/tables/{id}/open`: không cần body; tạo STAFF hoặc STAFF_CONFIRMATION, trả session. Nếu đang ACTIVE trả session cũ. Nhân viên được bypass cooldown vì đây là quyết định thủ công.
- `GET /api/sessions?limit=100&offset=0`: mới nhất trước; limit 1..500. Trả cả ACTIVE/PAID, không có tổng count.
- `GET /api/sessions/{id}/quote`: session và quote tại thời gian backend; phiên PAID dùng thời điểm ended_at nên tiền ổn định.
- `POST /api/sessions/{id}/checkout`: chốt tiền và thời điểm; lặp trả hóa đơn cũ. Đây là ghi nhận thanh toán demo, không kết nối tiền thật.
- `POST /api/simulations/observations`: body dưới đây. Chỉ nhận source SIMULATED cố định; không nhận timestamp hoặc source client. Cờ mô phỏng tắt trả 403.
- `WS /ws`: gửi snapshot ngay sau connect, sau thay đổi và khoảng 1 giây. Client không phải gửi message. Reconnect nhận snapshot mới đầy đủ.

```json
{"event_id":"0b15a1be-e7b6-4aa8-8d7b-bf8af454c828","table_id":1,"present":true,"confidence":0.9,"ambiguous":false}
```

UUID mới cho mỗi observation; cùng UUID/cùng payload trả duplicate=true, không tích lũy thêm thời gian. Cùng UUID/khác payload trả 409. cue_confidence tùy chọn [0,1] chỉ là input test, không khiến detector_ready=true. event_id/table_id bắt buộc. Unknown fields trả 422.

Session trả: id, table_id, started_at/ended_at ISO UTC, status, hourly_rate_snapshot, total_amount (null trước chốt), trigger_source, evidence_source, elapsed_seconds, billable_minutes, amount_vnd. Với ACTIVE, amount_vnd là quote; total_amount chỉ là tiền đã chốt.

Observation response: state, reason, session_id nullable, source=SIMULATED, duplicate. state thuộc FSM; reason enum được định nghĩa trong decision.py. Event snapshot có event_type, confidence, timestamp, provenance và decision result.

Lỗi: 404 không có bàn/phiên; 422 input; 403 browser Origin không hợp lệ hoặc tắt mô phỏng; 409 idempotency conflict; 400 Host không hợp lệ. Chưa có auth; chỉ chạy local. Giữ default port 8000/5173 để khớp danh sách browser Origin.
