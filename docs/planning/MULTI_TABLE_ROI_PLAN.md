# Kế hoạch hỗ trợ nhiều bàn trong hiệu chuẩn ROI

Phạm vi: một camera, nhiều bàn (tối đa `TABLE_COUNT`, hiện 4, giới hạn 8). Nhiều camera nằm ngoài phạm vi.

## 1. Hiện trạng

| Phần | Hỗ trợ nhiều bàn? |
|---|---|
| Mapper (`services/vision/mapper.py`) | Có: duyệt danh sách bàn, bỏ qua bàn `enabled: false`, đánh dấu AMBIGUOUS khi vùng đứng giao nhau. |
| File ROI và API lưu | Có: `tables` là danh sách; `zones.example.json` có 2 bàn. |
| Số bàn | Có: `TABLE_COUNT` 1..8. |
| Trình chỉnh ROI (`apps/web/src/RoiEditor.tsx`) | **Không thêm được bàn.** Thanh chọn bàn chỉ lấy từ bàn đã có trong file; không có nút Thêm bàn, Xóa bàn, hay bật/tắt `enabled`. |

Hệ quả: `configs/zones.json` chỉ có Bàn 1 trong khi Tổng quan hiện 4 bàn. Bàn 2–4 không nhận tín hiệu AI và luôn "Chưa có phiên", không có cảnh báo nào cho biết lý do.

Chiếc bàn phủ vải đen phía trước trong video là **Bàn 2, có tính tiền**, nên cần ROI riêng.

## 2. Các bước

### 2.1 Quản lý bàn trong tab Hiệu chuẩn ROI (frontend)
- Nút **+ Thêm bàn**: tạo vùng mặc định cho số bàn tiếp theo, tối đa `TABLE_COUNT` lấy từ snapshot.
- Nút **Xóa vùng bàn**, có hộp xác nhận.
- Công tắc **Bật/tắt theo dõi** từng bàn (`enabled`), cho bàn đang phủ vải hoặc không dùng.
- Bàn có trong danh sách tính tiền nhưng chưa có ROI hiện nhãn **"Chưa hiệu chuẩn"** trong thanh chọn bàn.

### 2.2 Cảnh báo ở Tổng quan và Camera
- Thẻ bàn hiện "Chưa có vùng AI" khi bàn chưa hiệu chuẩn hoặc đang tắt.
- Thông tin bàn nào có ROI lấy từ `GET /api/calibration/zones`; thêm trường nhỏ vào snapshot hoặc API nếu cần.

### 2.3 Nhiều bàn gần nhau
- Hiện đầy đủ cảnh báo chồng lấn (`overlaps` do API trả) ngay trong editor.
- Giải thích: người đứng ở vùng giao bị AMBIGUOUS và không tự mở bàn.
- "Tạo vùng đứng tự động" phải tránh vùng của bàn đã có.

### 2.4 Vẽ ROI Bàn 2 trên video thực
- Sau khi editor hỗ trợ, đề xuất tọa độ Bàn 2 từ video, như đã làm cho Bàn 1.
- Chạy `evalroi.py` để đối chiếu điểm chân của người với hai bàn và vùng AMBIGUOUS.
- Sao lưu `configs/zones.json` trước khi ghi đè.

### 2.5 Kiểm tra
- Test frontend: thêm, xóa, bật/tắt bàn; giới hạn tối đa `TABLE_COUNT`; nhãn "Chưa hiệu chuẩn".
- Test backend: lưu config nhiều bàn; bàn `enabled: false` không phát quan sát; chồng lấn cho AMBIGUOUS.
- Trước bàn giao: `pytest`, `npm test`, `npm run build`, và `scripts/smoke.py` sau build.

## 3. Rủi ro và lưu ý
- Bàn 2 nằm sát camera và che khuất một phần bàn 1 (người đứng xem ngồi/đứng ở giữa). Điểm chân của họ có thể rơi vào vùng đứng của cả hai bàn; cần xem kết quả đo trước khi chốt.
- Phân biệt người chơi và người đứng xem không chỉ dựa vào ROI mà cần phân tích tư thế và gậy.
- Khi bàn đã mở, AI tạm dừng cho bàn đó. Khi mọi bàn đã hiệu chuẩn đều đã mở, pipeline bỏ qua YOLO; bàn chưa hiệu chuẩn không được tính vào điều kiện này.
- Dữ liệu ROI chỉ kiểm chứng trên video ghi sẵn; chưa kiểm chứng trên camera thực.

## 4. Ngoài phạm vi
- Nhiều camera, mỗi camera một bộ ROI.
- Thay đổi luồng tính tiền hoặc FSM.
