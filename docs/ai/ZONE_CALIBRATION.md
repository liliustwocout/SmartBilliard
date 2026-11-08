# Hiệu chuẩn nhiều bàn

`configs/zones.example.json` chỉ minh họa cấu trúc normalized_xy_0_1 cho bốn bàn, chưa dùng bởi runtime Phase 2. Không coi các polygon đó đúng cho camera thật.

1. Cố định camera, độ phân giải, lens/zoom và mode; chụp frame tham chiếu được phép.
2. Vẽ polygon mặt chơi và polygon vùng đứng quanh bàn riêng cho mỗi table_id; x/W, y/H trong [0,1]. Standing zone không chỉ là mặt nỉ.
3. Validate ≥3 đỉnh phân biệt, diện tích >0, không tự giao; table_id tồn tại, enabled rõ. Lưu camera/setup hash và version để phát hiện thay đổi góc.
4. REAL_CLUB dùng bottom-center bbox hoặc foot keypoint có confidence; tay chế độ mini dùng anchor riêng được kiểm chứng.
5. Điểm ngoài mọi vùng → OUTSIDE. Trong nhiều standing zones hoặc sát biên chưa phân biệt được → AMBIGUOUS; không tùy tiện nhân tín hiệu sang hai bàn. Priority metadata chỉ dùng khi có quy tắc được kiểm thử.
6. Đi thử quanh từng bàn, giữa hai bàn, che khuất, nhiều người và vùng xa; ghi ground truth/assignment theo track và thời gian.
7. Đổi camera/góc/zoom phải hiệu chuẩn lại. Nâng resolution không khôi phục được góc bị che.

ROI editor/preview/overlay và zone mapper là SB-10/SB-12, chưa triển khai. Calibration checklist này không thay bằng chứng test video thực.
