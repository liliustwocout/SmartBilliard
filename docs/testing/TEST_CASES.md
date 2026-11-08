# Các tình huống chấp nhận

Các mục “logic” dùng Observation nhân tạo; camera/AI thật **chưa kiểm chứng** ở tất cả các mục.

1. **Bàn trống:** absence/low confidence không tạo phiên. Unit logic có.
2. **Người đi ngang:** hiện diện dưới duration rồi vắng không mở. Unit logic có; cần video đi ngang.
3. **Đứng cạnh nhưng không chơi:** mặc định NEEDS_CONFIRMATION, không tự tính phí. API/unit có; cần người thật.
4. **Người cầm gậy:** cue policy chưa ready không auto-open dù confidence test cao. Guard test có; cue detector thật chưa có.
5. **Nhiều người một bàn:** nghiệp vụ không mở trùng qua retry/concurrent open; chưa có multi-person mapper.
6. **Giữa hai bàn:** ambiguous input không mở; chưa kiểm chứng suy ra ambiguity từ geometry/video.
7. **Nhiều bàn đồng thời:** bốn bàn mở độc lập và WS snapshot đầy đủ; API test có. Chưa camera bốn bàn.
8. **Che khuất:** brief absence grace giữ candidate; gap dài reset; ACTIVE vẫn giữ. Unit có; chưa occlusion video.
9. **Mất camera:** chưa có reader. Backend/FSM không đóng ACTIVE từ absence; chưa test RTSP reconnect.
10. **FPS thấp:** khoảng cách observation vượt config reset candidate. Unit có; chưa đo processing FPS.
11. **Bàn gần:** cần video/gán nhãn, chưa có.
12. **Bàn xa:** cần video/gán nhãn riêng, chưa có.
13. **AI/event trùng:** UUID lặp không cộng thời gian hoặc tạo thêm phiên; khác payload trả 409. API có, nguồn test SIMULATED.
14. **Nhân viên checkout:** UTC server, rate snapshot, rounding, idempotent theo session ID, history/revenue. API/billing có.
15. **Người rời bàn:** absence/timeout không chốt session. Unit/API có; camera thật chưa test.

Bổ sung: restart SQLite giữ phiên/FSM; foreign key và unique ACTIVE; host/origin chặn trình duyệt ngoài; simulation disabled; invalid UUID/confidence/timestamp; boundary billing; offline static build và WS integration.
