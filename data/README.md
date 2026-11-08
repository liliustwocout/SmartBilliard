# Dữ liệu cục bộ

API tạo `smartbilliard.db` khi khởi động lần đầu. SQLite giữ bàn, sessions, FSM và detection events; file runtime bị ignore. Test và smoke dùng database tạm riêng.

Không đặt ảnh/video người chơi, credentials hoặc hồ sơ cá nhân ở đây để commit. Dataset/recordings riêng bị ignore, chỉ thu sau consent. Chưa có dataset thật.

Dừng API trước khi backup SQLite. Không xóa database để reset demo hoặc né migration; không có DELETE endpoint. Log mô phỏng tăng theo thời gian; tắt bộ phát khi không dùng.
