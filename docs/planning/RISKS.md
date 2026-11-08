# Rủi ro và cách kiểm soát

- **Bàn xa nhỏ/che khuất:** Sơn đo recall theo từng ROI, tăng góc/độ phân giải nếu cần; không nhận tám bàn mặc định. Chưa đo.
- **Người đứng không chơi:** person presence không chứng minh chơi; default staff confirmation, cue gate chưa sẵn sàng. Không đủ bằng chứng để tự tính tiền thực.
- **Bàn mini chỉ có tay:** dùng pipeline riêng khi cần; không báo precision người từ hand detection.
- **Thiếu cue weights/dataset:** interface trước; custom training sau; không dùng COCO như cue detector.
- **Mất camera/FPS thấp:** hiện có max observation gap trong FSM; reader/reconnect sẽ test Phase 3. Không đóng phiên đang active.
- **Restart/duplicate/concurrency:** FSM/session/event cùng SQLite; unique ACTIVE index, server lock và idempotency. Chỉ một worker.
- **Sai giờ hệ thống:** UTC server là nguồn chính; kiểm tra giờ laptop trước demo. UTC không chống được đồng hồ hệ điều hành nhảy; cần monotonic/clock health nếu vận hành thật.
- **Dữ liệu cá nhân:** chưa lưu hình, không copy liên hệ trong hồ sơ vào UI. Dataset thực cần consent và retention.
- **Dependency/network:** cài/build trước, khóa version, chạy local không CDN. npm audit kiểm tra đúng môi trường, không hứa không có lỗ hổng tương lai.
- **Log tăng:** simulator ~mỗi giây; dừng khi không dùng. Retention với idempotency window chưa triển khai.
- **Deploy ngoài laptop:** chưa auth/role/audit và migration; chỉ bind loopback. Không expose port hoặc dùng như hệ thống thu tiền sản xuất.
- **Tiến độ bốn tuần:** ưu tiên bốn bàn + confirmation; bỏ thử nghiệm tám bàn/cue tự động trước khi cắt validation hoặc billing safeguards.
