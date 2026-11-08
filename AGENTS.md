# SmartBilliard — hướng dẫn phát triển

## Phạm vi và tính trung thực

- Ưu tiên MVP chạy local cho PSI2026; thay đổi nhỏ, đọc code và caller trước khi sửa.
- Không gọi mô phỏng là camera AI. Không hardcode detection, session, doanh thu hoặc số liệu đo.
- Camera/YOLO/tracking chưa có trong Phase 2. Không bật tự động tính tiền thực khi chưa kiểm chứng.
- Không tự đóng phiên từ tín hiệu người/gậy biến mất; không mở trùng phiên ACTIVE/bàn.
- Không ghi đè hồ sơ tham khảo, dữ liệu SQLite hoặc .env. Không ghi dữ liệu cá nhân từ hồ sơ vào UI/test.

## Quy ước

- Python 3.11+, snake_case cho module/hàm, PascalCase cho class, type hints cho contract.
- React/TypeScript strict; PascalCase component, camelCase biến/hàm; UI tiếng Việt.
- UTC trong storage/API; VND số nguyên; backend là nguồn thời gian, giá và tiền chính thức.
- Ngưỡng ở config, validate khi khởi động. Code nghiệp vụ không phụ thuộc OpenCV/Ultralytics.
- Dùng thư viện chuẩn hoặc dependency có sẵn trước; không thêm hạ tầng phân tán cho demo.
- Credentials qua env; không commit .env, weights riêng, ảnh người chơi hoặc RTSP chứa mật khẩu.

## Git và kiểm tra

- Chưa khởi tạo Git ở thời điểm assessment; khi dùng Git, nhánh `feat/<topic>` hoặc `fix/<topic>`, commit nhỏ nêu lý do. Không tự push/merge khi chưa được yêu cầu.
- Logic mới không tầm thường phải có test; lỗi billing/FSM/idempotency phải có regression test.
- Trước bàn giao: `.venv/Scripts/python -m pytest`, `npm test`, `npm run build`; khi thay luồng tích hợp chạy `scripts/smoke.py` sau build.
- Test dữ liệu nhân tạo không thay thế kiểm chứng video/camera. Ghi rõ phần chưa test.
- Cập nhật README/API_SPEC khi đổi API; ADR khi đổi kiến trúc; bằng chứng và giới hạn sau milestone.
- Không xóa database để làm test pass; test dùng SQLite tạm.

## Milestone

Hoàn thành và báo cáo Phase 0–2 trước. Camera reader, YOLO, ROI editor và tracking thuộc Phase 3, chỉ triển khai sau yêu cầu tiếp theo.
