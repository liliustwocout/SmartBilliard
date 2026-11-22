# ADR 0004 — Phòng quản lý tách biệt khỏi phòng demo

Ngày: 22/11/2026. Trạng thái: đã chấp nhận (MVP).

## Bối cảnh

Phòng demo (`apps/api`, `apps/web`) là bản trình diễn một quán, không đăng nhập, có mô phỏng/camera/lab. Sản phẩm thật cần nhiều quán, tài khoản theo vai trò,
khách có tài khoản, đặt bàn, gamification và báo cáo. Trộn hai thứ vào một ứng dụng sẽ làm lẫn dữ liệu thật với dữ liệu mô phỏng và phá ranh giới tin cậy của demo.

## Quyết định

1. **Hai ứng dụng độc lập:** `apps/manage_api` (FastAPI, cổng 8100, SQLite `data/manage.db`) và `apps/manage_web` (React, cổng 5174). Không import chéo (có test tự quét mã nguồn); cấu hình dùng tiền tố `MANAGE_`; cấu hình từ chối database của demo.
2. **Một server cho nhiều quán (multi-tenant):** mọi bảng nghiệp vụ có `venue_id`; đường dẫn `/api/venues/{id}/...` kiểm tra người dùng thuộc đúng quán, sai quán trả 404.
3. **Xác thực bằng phiên phía máy chủ** (token băm trong DB, cookie HttpOnly + CSRF), không JWT; mật khẩu scrypt (thư viện chuẩn); khoá tài khoản; audit log chỉ thêm.
4. **Tính tiền phía backend:** giá chốt lúc mở bàn, làm tròn lên theo phút, VND nguyên, checkout idempotent bằng UPDATE có điều kiện; tính tiền cũng chốt các món, voucher, cọc trong cùng giao dịch.
5. **Cọc giả lập qua `PaymentProvider`:** chỉ có `mock`; cấu hình khác `mock` bị từ chối khi khởi động. Giao diện nêu rõ "mô phỏng".
6. **Gamification quyết định ở backend:** `secrets` cho vòng quay, kế hoạch thưởng đảm bảo theo ngày, sổ điểm chỉ thêm. Check-in xác minh bằng IP công cộng của quán và/hoặc mã xoay vòng, vì trình duyệt không đọc được tên wifi.
7. **Khoá ghi SQLite làm cơ chế đồng thời:** các thao tác cần tuần tự hoá (đặt bàn, thêm món vs checkout, quay) dùng `UPDATE` rỗng/có điều kiện để chiếm khoá ghi; có test đua.

## Hệ quả và giới hạn

- SQLite một process phù hợp vài quán thử nghiệm. Nhiều quán đồng thời cần PostgreSQL và công cụ migration (chưa có: **đổi cấu trúc bảng cần tạo lại DB**; hiện chưa có dữ liệu thật).
- Giới hạn tốc độ đăng nhập và đếm thử mã check-in nằm trong bộ nhớ một process.
- Chưa có thanh toán thật, nhắc lịch (SMS/thông báo), giờ mở cửa, huy hiệu/bảng xếp hạng, cập nhật realtime (đang hỏi lại mỗi 5 giây).
- Vòng quay có thưởng là hình thức khuyến mại: cần kiểm tra quy định pháp lý trước khi chạy thật (ngoài phạm vi kỹ thuật).
- Camera/AI chưa được nối vào phòng quản lý; nếu nối sau thì chỉ gợi ý cho nhân viên xác nhận, không tự mở/đóng phiên hay tính tiền (theo AGENTS.md).
- Sao lưu bằng `scripts/manage_backup.py` (API sao lưu của SQLite, kiểm tra toàn vẹn, xoay vòng); khôi phục là thao tác thủ công khi đã dừng máy chủ.
