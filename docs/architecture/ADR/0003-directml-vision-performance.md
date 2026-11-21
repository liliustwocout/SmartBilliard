# ADR 0003 — Optional DirectML and shared JPEG cache

Ngày: 21/11/2026. Trạng thái: áp dụng thử local.

OpenCV DNN trên máy thử chạy CPU dù có GPU; runner bị giới hạn 8 FPS, MJPEG 10 FPS và từng cửa sổ tự vẽ/nén lại ảnh. Thay model hoặc giảm kích thước đầu vào sẽ làm khó đối chiếu chất lượng, nhất là người ở bàn xa.

Thêm ONNX Runtime DirectML dưới dạng dependency Windows tùy chọn. Các detector giữ weights, input 640 và bộ giải mã hiện có; mỗi detector sở hữu session chạy tuần tự. Thiếu/lỗi DirectML quay về CPU và cập nhật nhãn backend. Theo [tài liệu DirectML](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html), tắt memory pattern/parallel execution và chọn adapter theo ID DirectML. Không coi cài dependency hay nạp weights là kiểm chứng độ chính xác.

Runner xử lý tối đa 30 FPS, giữ tốc độ file theo FPS gốc, phát quan sát tối đa 5 Hz vào SQLite/FSM. JPEG được cache theo sequence khung và cấu hình ROI; chỉ ảnh preview annotated được thu nhỏ. API vẽ/nén ở worker thread, gửi sequence mới. Báo riêng FPS khung và FPS suy luận, không lấy số gói MJPEG hoặc khung đọc lỗi làm FPS AI. Pause/resume và quy tắc phiên/tính tiền giữ nguyên.

Đánh đổi: dependency GPU tùy chọn, sai adapter có thể chậm hơn CPU; session có thể dùng CPU cho một số toán tử. Cần đo video thật, HTTP và camera riêng. Chưa thay đổi/training model, chưa bật tính tiền tự động.

Chế độ nhanh mặc định tắt gậy thử nghiệm để ưu tiên Pose/tracking, có thể bật lại trong config. Giảm số thread decoder, tái dùng buffer đầu vào cùng chuẩn hóa RGB và tách cache JPEG. Thêm index `(timestamp DESC, id DESC)` cho truy vấn 30 sự kiện mới nhất; startup bổ sung index vào DB cũ theo cách idempotent, không xóa/ghi đè dữ liệu. Dùng bộ đếm thời gian có độ phân giải cao và tránh ghép hai bộ giới hạn FPS ở producer/MJPEG.
