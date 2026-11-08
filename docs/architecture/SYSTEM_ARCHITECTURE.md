# Kiến trúc hệ thống

## Lựa chọn

Một FastAPI process + SQLite file + React static build. Không cần broker; process quản lý các WS queue kích thước 1 và đẩy snapshot khi có mutation hoặc mỗi giây. Khi reconnect, client nhận đầy đủ state, không phải tự nối event bị mất. Vite chỉ dùng khi phát triển.

FSM thuần Python ở `services/vision/decision.py` nhận Observation, thời gian và config; không biết DB/HTTP/UI. Backend thực thi decision trong transaction cùng detection event và session. Cue và video source là protocol chuẩn bị; chưa có inference.

SQLite lưu session/FSM/event nên restart không mất phiên hoặc candidate. Async lock tuần tự hóa mutation trong một process; unique partial index bảo vệ một ACTIVE/bàn ở database. Không dùng nhiều worker. Giao dịch nhỏ, không chạy inference/blocking capture trong event loop.

## Luồng tương lai

Camera/video adapter → detector/tracker → mapper → Observation → FSM → session API. Đầu vào detection và quyền mở phiên tách rời. Tích hợp camera cần endpoint có xác thực service hoặc IPC phù hợp; không tái sử dụng endpoint SIMULATED rồi đổi nhãn.

## Ranh giới tin cậy

Phase 2 local laptop, không auth người dùng. Host và browser Origin kiểm tra; API chỉ bind loopback. Endpoint mô phỏng có thể tắt bằng env. Server tự cấp thời gian nhận; không cho client backdate và tính phí. Bản deploy mạng cần auth, authorization, CSRF/session và audit riêng trước khi mở mạng.

## Trade-offs

Snapshot mỗi giây đơn giản cho tối đa tám bàn, chưa tối ưu cho fleet lớn. Không có job retention hay migration vì chưa có dữ liệu sản xuất; backup và version schema trước khi mở rộng. Chưa có hạ tầng `infra/` vì không dùng cloud/Docker.

Tham khảo triển khai: [FastAPI WebSocket](https://fastapi.tiangolo.com/advanced/websockets/), [SQLAlchemy SQLite partial index](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#partial-indexes), [Tailwind Vite](https://tailwindcss.com/docs/installation/using-vite).
