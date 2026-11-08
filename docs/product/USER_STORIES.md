# User stories

- **US01 · Nhân viên:** xem toàn bộ bàn và trạng thái realtime để không bỏ sót bàn. Đạt khi cùng một snapshot chứa tất cả bàn; mất WS hiển thị stale và khóa thao tác.
- **US02 · Nhân viên:** xác nhận tín hiệu đủ lâu trước khi bắt đầu tính phí. Đạt khi mặc định NEEDS_CONFIRMATION chưa có session; bấm xác nhận tạo đúng một phiên, có provenance.
- **US03 · Nhân viên:** mở bàn thủ công lúc AI thất bại. Đạt khi không cần detection vẫn mở được và trigger_source=STAFF.
- **US04 · Nhân viên:** thanh toán và đối soát. Đạt khi tiền theo server, snapshot giá không đổi, checkout retry cùng ID trả hóa đơn cũ.
- **US05 · Chủ quán:** người rời bàn không khiến hệ thống mất phiên. Đạt khi absence không kết thúc ACTIVE.
- **US06 · Nhóm demo:** gửi mô phỏng và sự kiện trùng minh bạch. Đạt khi UI ghi MÔ PHỎNG, retry không nhân phiên và không cộng thời gian hiện diện.
- **US07 · Sơn:** cấu hình nhiều vùng cho một camera. Chưa đạt Phase 2; cần polygon chuẩn hóa có standing zone, overlap xuất AMBIGUOUS.
- **US08 · Đức:** trình diễn offline và giải thích giới hạn. Đạt ở lớp phần mềm khi build local hoạt động không Internet; phần camera còn chờ kiểm chứng vật lý.
