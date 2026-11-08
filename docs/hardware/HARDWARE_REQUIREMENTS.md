# Yêu cầu phần cứng

Phase 2 chỉ cần laptop chạy Python 3.11/Node22 và trình duyệt, dung lượng để dependencies/build/SQLite. Không có yêu cầu GPU vì chưa inference; chưa đo RAM/CPU nên không công bố minimum benchmark.

Camera MVP: một USB webcam hoặc IP RTSP có thể cấu hình exposure/focus, chân gắn cố định, nguồn điện, dây đủ dài và mạng local nếu RTSP. Ưu tiên góc nhìn đủ vùng đứng quanh 3–4 bàn, tránh người che nhau và ánh đèn phản chiếu. Bàn mini cần góc nhìn tay/gậy, mode MINI_TABLE.

Laptop inference: đánh giá CPU trước với model nhỏ, GPU tùy khả năng; ghi model/input size/resolution và measured FPS. 4K có thể tăng dữ liệu vùng xa nhưng tăng tải; không giả định 4K hoặc một camera nhìn tốt tám bàn.

Edge box/NPU và nhiều luồng trong hồ sơ dự thi là định hướng dài hạn, chưa phải BOM mua ngay hoặc năng lực đã chứng minh. Dùng phần cứng có sẵn để giảm rủi ro demo.
