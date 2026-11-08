# Kịch bản demo

## Chuẩn bị

Build frontend, cài dependencies/weights cần thiết trước khi tới sân khấu. Kiểm tra giờ laptop, cắm nguồn, tắt update tự động trong lúc demo. Dừng API trước backup SQLite; không xóa lịch sử để làm số liệu đẹp. Mở dashboard local, kiểm tra banner nguồn và các capability.

## Phase 2 hiện có (khoảng 3–5 phút, chưa phải camera AI)

1. Nói rõ: “Đây là mô phỏng sự kiện để chứng minh tích hợp, phần camera chưa được triển khai trong phiên bản này.”
2. Cho xem bốn bàn và tổng doanh thu thực trong SQLite. Chọn bàn chưa có phiên.
3. Phát tín hiệu hiện diện, chờ ngưỡng; giải thích người gần bàn chưa chứng minh chơi. Default chỉ chờ nhân viên xác nhận.
4. Xác nhận mở, xem thời gian/tiền do backend gửi và nguồn STAFF_CONFIRMATION + SIMULATED.
5. Dừng tín hiệu; phiên vẫn ACTIVE. Gửi lại event để minh họa chống trùng.
6. Thanh toán, xác nhận hóa đơn, mở history. Giá/rounding được giải thích rõ.
7. Mở System: camera/cue chưa triển khai; trình bày milestone tiếp theo và không nêu accuracy/FPS chưa đo.

## Demo camera sau M4

Thay bước phát sự kiện bằng USB/RTSP thật hoặc video ghi rõ VIDEO. Hiển thị calibrated ROI/track overlay, ngắt nguồn để kiểm tra lỗi và fallback. Chỉ gọi LIVE khi stream hiện tại thật. Nếu mini chỉ nhận tay, nói rõ MINI_TABLE; không dùng kết quả đó chứng minh person detector quán thật.

## Fallback

Mất camera → cảnh báo và mở bàn thủ công, không tự chốt phiên. Mất mạng Internet không ảnh hưởng local. Mất backend → UI khóa thao tác, restart từ cùng SQLite. Video replay và simulation phải được công bố rõ; không chuyển fallback ngầm rồi tiếp tục gọi LIVE.
