# Luồng dữ liệu

```mermaid
flowchart LR
    S[UI hoặc CLI: SIMULATED] --> V[Validate UUID / bàn / confidence]
    V --> I{event_id đã tồn tại?}
    I -->|Cùng payload| R[Trả kết quả đã lưu: duplicate]
    I -->|Khác payload| X[409 Conflict]
    I -->|Chưa tồn tại| F[Temporal Decision Engine]
    F --> C[NEEDS_CONFIRMATION mặc định]
    F -->|Tự mở demo được bật| A[Session nguồn SIMULATED]
    C -->|Nhân viên xác nhận| M[Session STAFF_CONFIRMATION]
    A --> D[(SQLite transaction)]
    M --> D
    D --> W[WS snapshot + server quote mỗi giây]
    W --> U[Dashboard tiếng Việt]
    U -->|Checkout session_id| B[Backend chốt UTC + tiền nguyên]
    B --> D
    P[Camera / detector / tracker / ROI: chưa triển khai] -.-> F
```

Server gắn timestamp nhận cho tín hiệu mô phỏng. UUID lặp cùng payload trả kết quả cũ, không chạy FSM lại. Candidate chỉ đủ khi nhận chuỗi tín hiệu theo thời gian thật; timeout/gap phá chuỗi. Tín hiệu vắng hoặc mơ hồ không mở bàn và không đóng phiên.

Snapshot có `server_time`, tables/session/quotes, config, nguồn và 30 events mới nhất. Lịch sử session lấy riêng bằng REST có limit/offset. Client không tính tiền và không tự mở phiên khi reload/reconnect.

Sơ đồ tương lai không có nghĩa đã nối camera. Dữ liệu khung hình sẽ chỉ ở memory trừ khi có đồng ý thu dataset.
