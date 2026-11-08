# Điểm trình bày kỹ thuật

- Vấn đề: ghi nhận phiên và đối soát thời gian ở quán bi-a; camera hỗ trợ nhân viên, chưa thay thế quyết định khi tín hiệu yếu.
- Một camera nhiều standing/play zones; assignment và temporal logic tách detector. Đây là thiết kế, chưa phải năng lực camera được chứng minh.
- Phần mềm Phase 2 thật: session và tiền ở backend, chống trùng tại DB, UTC/rate snapshot, WebSocket, history và demo offline.
- AI hiện chưa triển khai: không có số liệu person/cue/8 bàn; không gọi mô phỏng là inference. Baseline person không chứng minh bắt đầu chơi.
- Không tự kết thúc phiên từ mất detection, giảm rủi ro tính thiếu do occlusion.
- Cue model cần custom data/validation vì COCO không có cue; MINI_TABLE/REAL_CLUB đánh giá riêng.
- Roadmap bốn tuần và owner rõ; bốn bàn validation trước, tám bàn/4K là thử nghiệm mở rộng.

Khi hỏi hiệu năng/ROI kinh doanh: trả lời “chưa đo/chưa khảo sát” nếu chưa có evidence. Hồ sơ dài hạn edge/cloud/Loyalty là định hướng, không phải phạm vi đã bàn giao. Trình bày link test/log/artifact thay vì phần trăm không có mẫu số.
